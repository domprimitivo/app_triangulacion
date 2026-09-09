"""
MILEFORUM · Bundle Loader
Carga los bundles multiceph reales del repositorio.

Estructura de un bundle:
  bundle_nombre/
  ├── manifest.json              ← índice de archivos + hashes
  ├── inference_snapshot.json    ← último snapshot de inferencia
  ├── run_receipt.json           ← recibo de ejecución
  ├── backbone/
  │   ├── phase_rnn_state_dict.pt  ← modelo GRU real (PyTorch)
  │   ├── meta.json               ← feature_cols, labels, k, rnn_type
  │   ├── mu.npy                  ← media de normalización
  │   └── sigma.npy               ← desviación estándar
  └── heads/
      └── {nombre}_head/
          └── head_spec.json      ← tipo, fase activa, params

Fases del backbone:
  0 → Estabilidad (baja energía)
  1 → Tensión acumulada (peligro de latigazo)
  2 → Ruptura en curso (brinco ocurriendo)
  3 → Fase invariante (nueva norma / cresta sostenida)
"""

import json
import zipfile
import numpy as np
from pathlib import Path
from typing import Optional
from datetime import datetime

from runtime_paths import get_base_dir

BUNDLES_DIR = get_base_dir() / "data" / "modelos"
BUNDLES_DIR.mkdir(parents=True, exist_ok=True)

# Mapa de nombres de bundle por dominio
BUNDLE_NAMES = {
    "abogado":              "abogado_unipersonal_multiceph_bundle_v1",
    "arquitecto":           "arquitectura_unipersonal_multiceph_bundle_v1",
    "contador_finanzas":    "contador_multiceph_bundle_v1",
    "consultor_pyme":       "consultor_pyme_multiceph_bundle_v1",
    "diseno_producto":      "diseno_produccion_unipersonal_multiceph_bundle_v1",
    "operaciones_logistica": "logistica_multiceph_bundle_v1",
}

# Fases del backbone — igual para todos los dominios unipersonales
FASES_BACKBONE = {
    0: "Estabilidad (baja energía)",
    1: "Tensión acumulada (peligro de latigazo)",
    2: "Ruptura en curso (brinco ocurriendo)",
    3: "Fase invariante (nueva norma / cresta sostenida)",
}

# Mapeo a los nombres del sistema Mileforum
FASE_A_MILEFORUM = {
    0: {"numero": 1, "nombre": "INICIO"},
    1: {"numero": 3, "nombre": "TENSIÓN ALTA"},
    2: {"numero": 3, "nombre": "TENSIÓN ALTA"},
    3: {"numero": 4, "nombre": "RESOLUCIÓN"},
}


class BundleLoader:
    """
    Carga un bundle multiceph desde disco (zip o carpeta descomprimida).
    Expone el backbone y las cabezas para inferencia.
    """

    def __init__(self, dominio: str):
        self.dominio      = dominio
        self.bundle_name  = BUNDLE_NAMES.get(dominio)
        self.manifest     = None
        self.meta         = None
        self.mu           = None
        self.sigma        = None
        self.heads        = {}
        self.modelo_torch = None
        self._cargado     = False
        self._error       = None

        if self.bundle_name:
            self._cargar()

    # ── Carga ──────────────────────────────────────────────────────
    def _cargar(self):
        """Intenta cargar desde zip o carpeta."""
        zip_path    = BUNDLES_DIR / f"{self.bundle_name}.zip"
        folder_path = BUNDLES_DIR / self.bundle_name

        if zip_path.exists():
            self._cargar_desde_zip(zip_path)
        elif folder_path.exists():
            self._cargar_desde_carpeta(folder_path)
        else:
            self._error = (
                f"Bundle '{self.bundle_name}' no encontrado en {BUNDLES_DIR}. "
                f"Coloca el zip en esa carpeta."
            )

    def _cargar_desde_zip(self, zip_path: Path):
        """Lee el bundle directamente desde el zip sin descomprimir."""
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                nombres = z.namelist()
                prefix  = self.bundle_name + "/"

                def leer_json(rel):
                    for n in nombres:
                        if n.endswith(rel):
                            return json.loads(z.read(n))
                    return None

                def leer_npy(rel):
                    for n in nombres:
                        if n.endswith(rel):
                            import io
                            return np.load(io.BytesIO(z.read(n)), allow_pickle=False)
                    return None

                self.manifest = leer_json("manifest.json")
                self.meta     = leer_json("backbone/meta.json")
                self.mu       = leer_npy("backbone/mu.npy")
                self.sigma    = leer_npy("backbone/sigma.npy")

                # Cargar todas las cabezas
                for n in nombres:
                    if "head_spec.json" in n:
                        spec      = json.loads(z.read(n))
                        head_name = spec.get("name", n.split("/")[-2])
                        self.heads[head_name] = spec

                # Cargar modelo PyTorch si está disponible
                self._intentar_cargar_pytorch(z)

            self._cargado = True
            print(f"[BUNDLE] {self.bundle_name} cargado desde zip · "
                  f"{len(self.heads)} cabezas")

        except Exception as e:
            self._error   = str(e)
            self._cargado = False

    def _cargar_desde_carpeta(self, folder: Path):
        """Carga bundle desde carpeta descomprimida."""
        try:
            self.manifest = json.loads((folder / "manifest.json").read_text())
            self.meta     = json.loads((folder / "backbone/meta.json").read_text())
            self.mu       = np.load(folder / "backbone/mu.npy", allow_pickle=False)
            self.sigma    = np.load(folder / "backbone/sigma.npy", allow_pickle=False)

            for spec_path in folder.rglob("head_spec.json"):
                spec      = json.loads(spec_path.read_text())
                head_name = spec.get("name", spec_path.parent.name)
                self.heads[head_name] = spec

            self._intentar_cargar_pytorch_carpeta(folder)
            self._cargado = True
            print(f"[BUNDLE] {self.bundle_name} cargado desde carpeta · "
                  f"{len(self.heads)} cabezas")

        except Exception as e:
            self._error   = str(e)
            self._cargado = False

    def _intentar_cargar_pytorch(self, zip_file):
        """Carga el modelo GRU desde el zip si PyTorch está disponible."""
        try:
            import torch
            import io
            for n in zip_file.namelist():
                if "phase_rnn_state_dict.pt" in n:
                    buffer = io.BytesIO(zip_file.read(n))
                    state  = torch.load(buffer, map_location="cpu",
                                        weights_only=True)
                    self._state_dict  = state
                    self.modelo_torch = True  # marca que hay modelo
                    print(f"[BUNDLE] Modelo PyTorch cargado")
                    return
        except ImportError:
            print("[BUNDLE] PyTorch no disponible · usando inferencia geométrica")
        except Exception as e:
            print(f"[BUNDLE] Error cargando PyTorch: {e}")

    def _intentar_cargar_pytorch_carpeta(self, folder: Path):
        pt_path = folder / "backbone/phase_rnn_state_dict.pt"
        if pt_path.exists():
            try:
                import torch
                self._state_dict  = torch.load(pt_path, map_location="cpu",
                                               weights_only=True)
                self.modelo_torch = True
            except ImportError:
                pass

    # ── Normalización ────────────────────────────────────────────
    def normalizar_features(self, features_raw: dict) -> np.ndarray:
        """
        Convierte features en vector normalizado usando mu/sigma del bundle.
        features_raw debe tener las claves de meta['feature_cols']:
          TensionElastica_TE, Persistencia_P,
          RuidoInstitucional_R, MomentoInercia_MI
        """
        cols = self.meta.get("feature_cols", [
            "TensionElastica_TE", "Persistencia_P",
            "RuidoInstitucional_R", "MomentoInercia_MI"
        ])
        vec = np.array([features_raw.get(c, 0.5) for c in cols],
                       dtype=np.float32)
        if self.mu is not None and self.sigma is not None:
            sigma_safe = np.where(self.sigma == 0, 1.0, self.sigma)
            vec        = (vec - self.mu) / sigma_safe
        return vec

    # ── Inferencia de fase ────────────────────────────────────────
    def inferir_fase(self, features_raw: dict) -> dict:
        """
        Determina la fase usando el backbone real (si PyTorch disponible)
        o la lógica geométrica de respaldo.
        """
        if self.modelo_torch and hasattr(self, "_state_dict"):
            return self._inferir_con_pytorch(features_raw)
        else:
            return self._inferir_geometrico(features_raw)

    def _inferir_con_pytorch(self, features_raw: dict) -> dict:
        """Inferencia real con el modelo GRU."""
        try:
            import torch
            import torch.nn as nn

            vec = self.normalizar_features(features_raw)
            k   = self.meta.get("k", 10)

            # Construir secuencia de longitud k repitiendo el vector actual
            # (en producción real esto sería la trayectoria histórica)
            seq = torch.tensor(vec).unsqueeze(0).unsqueeze(0)
            seq = seq.repeat(1, k, 1)  # (1, k, features)

            # Reconstruir modelo GRU
            n_features = len(self.meta.get("feature_cols", [4]))
            n_labels   = len(self.meta.get("labels", {4: ""}))
            hidden_size = 64

            class GRUModel(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.gru = nn.GRU(n_features, hidden_size,
                                      batch_first=True)
                    self.fc  = nn.Linear(hidden_size, n_labels)

                def forward(self, x):
                    out, _ = self.gru(x)
                    return self.fc(out[:, -1, :])

            model = GRUModel()
            model.load_state_dict(self._state_dict, strict=False)
            model.eval()

            with torch.no_grad():
                logits = model(seq)
                probs  = torch.softmax(logits, dim=-1).squeeze().tolist()

            if isinstance(probs, float):
                probs = [probs]

            fase_id = int(np.argmax(probs))
            return {
                "fase_backbone":  fase_id,
                "fase_label":     FASES_BACKBONE.get(fase_id, "Desconocida"),
                "probs":          probs,
                "confianza":      round(max(probs), 3),
                "modo":           "pytorch_real",
            }

        except Exception as e:
            print(f"[BUNDLE] Error en inferencia PyTorch: {e} · fallback geométrico")
            return self._inferir_geometrico(features_raw)

    def _inferir_geometrico(self, features_raw: dict) -> dict:
        """
        Fallback geométrico cuando PyTorch no está disponible.
        Mapea Trigo/Cobre/Petróleo a los features del backbone.
        """
        import math
        t = features_raw.get("trigo",    features_raw.get("TensionElastica_TE", 0.5))
        c = features_raw.get("cobre",    features_raw.get("Persistencia_P",     0.5))
        p = features_raw.get("petroleo", features_raw.get("RuidoInstitucional_R", 0.5))

        tension    = math.sqrt((t**2 + p**2) / 2)
        resilencia = max(0.0, c - max(0.0, tension - 0.65) * 0.5)
        coherencia = 1.0 - math.sqrt(
            ((t-0.5)**2 + (c-0.5)**2 + (p-0.5)**2) / 3)

        if tension >= 0.70 and resilencia < 0.55:
            fase_id = 1   # Tensión acumulada
        elif tension >= 0.70:
            fase_id = 2   # Ruptura en curso
        elif coherencia >= 0.75 and tension < 0.45:
            fase_id = 0   # Estabilidad
        else:
            fase_id = 3   # Fase invariante

        probs = [0.1, 0.1, 0.1, 0.1]
        probs[fase_id] = 0.7

        return {
            "fase_backbone": fase_id,
            "fase_label":    FASES_BACKBONE.get(fase_id, "Desconocida"),
            "probs":         probs,
            "confianza":     0.72,
            "modo":          "geometrico",
        }

    # ── Ejecutar cabezas ──────────────────────────────────────────
    def ejecutar_cabezas(self, fase_label: str,
                         features_raw: dict,
                         umbral_gating: float = 0.65) -> dict:
        """
        Activa las cabezas correspondientes a la fase detectada.
        Solo activa cabezas cuya phase_conditioning incluye la fase.
        """
        cabezas_activas   = {}
        cabezas_inactivas = []

        for nombre, spec in self.heads.items():
            fases_activas = (spec.get("phase_conditioning", {})
                                 .get("active_in_phases", []))
            if fase_label in fases_activas:
                resultado = self._evaluar_cabeza(spec, features_raw)
                if resultado.get("activada"):
                    cabezas_activas[nombre] = resultado
            else:
                cabezas_inactivas.append(nombre)

        return {
            "cabezas_activadas": cabezas_activas,
            "total_activadas":   len(cabezas_activas),
            "total_inactivas":   len(cabezas_inactivas),
            "accion_principal":  self._seleccionar_accion_principal(
                cabezas_activas),
        }

    def _evaluar_cabeza(self, spec: dict, features: dict) -> dict:
        """Evalúa si una cabeza se activa según su tipo y los features."""
        tipo   = spec.get("type", "")
        nombre = spec.get("name", "")

        t = features.get("trigo",    0.5)
        c = features.get("cobre",    0.5)
        p = features.get("petroleo", 0.5)

        activada = False
        score    = 0.0

        if tipo == "TrigoBandHead":
            # Se activa cuando Trigo está en una banda de tensión media-alta
            activada = 0.35 <= t <= 0.85
            score    = t

        elif tipo == "CobreRangeCeilingHead":
            # Se activa cuando Cobre supera el techo (recursos bajo presión)
            activada = c >= 0.55
            score    = c

        elif tipo == "PetroleoFlowHead":
            # Se activa cuando Petróleo indica flujo coherente
            activada = p >= 0.60
            score    = p

        return {
            "nombre":   nombre,
            "tipo":     tipo,
            "activada": activada,
            "score":    round(score, 3),
        }

    def _seleccionar_accion_principal(self, cabezas_activas: dict) -> str:
        """Selecciona la acción principal entre las cabezas activadas."""
        if not cabezas_activas:
            return "sin_accion_sugerida"
        # La cabeza con mayor score es la acción principal
        mejor = max(cabezas_activas.items(),
                    key=lambda x: x[1].get("score", 0))
        return mejor[0].replace("_head", "")

    # ── Episodio completo ─────────────────────────────────────────
    def ejecutar_episodio(self, features_input: dict,
                          tipo_consulta: str = "general") -> dict:
        """
        Ejecuta el episodio completo:
        features → fase → cabezas → resultado
        """
        if not self._cargado:
            return self._episodio_sin_bundle(features_input, tipo_consulta)

        # 1. Inferir fase con el backbone
        fase_resultado = self.inferir_fase(features_input)
        fase_id    = fase_resultado["fase_backbone"]
        fase_label = fase_resultado["fase_label"]
        confianza  = fase_resultado["confianza"]

        # 2. Ejecutar cabezas
        cabezas    = self.ejecutar_cabezas(fase_label, features_input)
        accion     = cabezas["accion_principal"]

        # 3. Mapear a formato Mileforum
        fase_mf    = FASE_A_MILEFORUM.get(fase_id,
                                          {"numero": 2, "nombre": "EQUILIBRIO"})

        import math
        t = features_input.get("trigo",    0.5)
        c = features_input.get("cobre",    0.5)
        p = features_input.get("petroleo", 0.5)
        tension    = round(math.sqrt((t**2 + p**2) / 2), 4)
        resilencia = round(max(0.0, c - max(0.0, tension-0.65)*0.5), 4)
        m          = (t+c+p)/3
        coherencia = round(1.0 - math.sqrt(
            ((t-m)**2+(c-m)**2+(p-m)**2)/3), 4)

        return {
            "heads":     {"trigo": t, "cobre": c, "petroleo": p},
            "estados": {
                "campos":       round((t+c+p)/3, 4),
                "tension":      tension,
                "coherencia":   coherencia,
                "resiliencia":  resilencia,
                "indice_telos": round(coherencia * resilencia, 4),
            },
            "fase":           fase_mf,
            "fase_backbone":  {"id": fase_id, "label": fase_label},
            "accion_sugerida": accion,
            "sugerencia_tcl":  self._generar_tcl(fase_label, accion,
                                                  tension, tipo_consulta),
            "confianza":       confianza,
            "cabezas_activas": cabezas["total_activadas"],
            "cabezas_detalle": cabezas["cabezas_activadas"],
            "modo_motor":      f"bundle_real_{fase_resultado['modo']}",
        }

    def _episodio_sin_bundle(self, features: dict, tipo: str) -> dict:
        """Fallback cuando el bundle no está disponible."""
        from .notebook_engine import AprendizMileforum
        motor  = AprendizMileforum(self.dominio)
        result = motor._ejecutar_simulado("", tipo, features)
        result["modo_motor"] = "simulado_sin_bundle"
        result["advertencia"] = (
            f"Bundle '{self.bundle_name}' no encontrado. "
            f"Coloca el zip en data/modelos/ para usar el modelo real."
        )
        return result

    def _generar_tcl(self, fase_label: str, accion: str,
                     tension: float, tipo: str) -> str:
        plantillas = {
            "Estabilidad (baja energía)":
                f"Sistema estable. Tensión baja ({tension:.2f}). "
                f"Acción recomendada: {accion.replace('_', ' ')}.",
            "Tensión acumulada (peligro de latigazo)":
                f"Tensión acumulada detectada ({tension:.2f}). "
                f"Riesgo de latigazo inminente. "
                f"Acción urgente: {accion.replace('_', ' ')}.",
            "Ruptura en curso (brinco ocurriendo)":
                f"Ruptura activa ({tension:.2f}). El sistema está en transición. "
                f"Ejecutar inmediatamente: {accion.replace('_', ' ')}.",
            "Fase invariante (nueva norma / cresta sostenida)":
                f"Nueva norma establecida. El sistema se ha reconfigurado. "
                f"Consolidar con: {accion.replace('_', ' ')}.",
        }
        return plantillas.get(fase_label,
                              f"Estado: {fase_label}. Acción: {accion}.")

    @property
    def disponible(self) -> bool:
        return self._cargado

    @property
    def info(self) -> dict:
        return {
            "bundle":    self.bundle_name,
            "dominio":   self.dominio,
            "cargado":   self._cargado,
            "cabezas":   len(self.heads),
            "pytorch":   bool(self.modelo_torch),
            "error":     self._error,
        }


# ── Cache de bundles ─────────────────────────────────────────────
_CACHE: dict[str, BundleLoader] = {}

def obtener_bundle(dominio: str) -> BundleLoader:
    if dominio not in _CACHE:
        _CACHE[dominio] = BundleLoader(dominio)
    return _CACHE[dominio]

def ejecutar_bundle(dominio: str, features: dict,
                    tipo: str = "general") -> dict:
    """Función de acceso principal desde los routers."""
    bundle = obtener_bundle(dominio)
    return bundle.ejecutar_episodio(features, tipo)

def estado_bundles() -> dict:
    """Devuelve el estado de todos los bundles cargados."""
    return {d: obtener_bundle(d).info for d in BUNDLE_NAMES}
