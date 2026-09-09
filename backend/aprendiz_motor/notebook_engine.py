"""
23/Marzo/2026 inicio
Aprendiz Mileforum - Motor de IA Local
=====================================
Nota de lo que se esta realizando: Se reemplaza el stub original con el conector real al bundle multiceph.

Nota:
Prioridad de ejecución:
  1. Bundle real (.zip del repo) con GRU PyTorch + cabezas
  2. Fallback geométrico si PyTorch no está instalado
  3. Simulado si el bundle no está en disco

Coloca los bundles en:
  Backend/aprendiz_motor/modelos/abogado_unipersonal_multiceph_bundle_v1.zip
  Backend/aprendiz_motor/modelos/contador_multiceph_bundle_v1.zip
  ... etc
"""

import json
import math
import zipfile
import logging
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from runtime_paths import get_base_dir

logger = logging.getLogger(__name__)

MODELOS_DIR = get_base_dir() / "aprendiz_motor" / "modelos"

# Mapa bundle por dominio_id
BUNDLE_NAMES = {
    "abogado":           "abogado_unipersonal_multiceph_bundle_v1",
    "arquitecto":        "arquitectura_unipersonal_multiceph_bundle_v1",
    "contador":          "contador_multiceph_bundle_v1",
    "consultor_pyme":    "consultor_pyme_multiceph_bundle_v1",
    "diseno_producto":   "diseno_produccion_unipersonal_multiceph_bundle_v1",
    "operaciones":       "logistica_multiceph_bundle_v1",
}

# Fases del backbone GRU
FASES_BACKBONE = {
    0: "Estabilidad (baja energía)",
    1: "Tensión acumulada (peligro de latigazo)",
    2: "Ruptura en curso (brinco ocurriendo)",
    3: "Fase invariante (nueva norma / cresta sostenida)",
}

# Features que espera el backbone
FEATURE_COLS = [
    "TensionElastica_TE",
    "Persistencia_P",
    "RuidoInstitucional_R",
    "MomentoInercia_MI",
]


# ─────────────────────────────────────────────────────────────────
# CARGADOR DE BUNDLE
# ─────────────────────────────────────────────────────────────────

class BundleLoader:
    def __init__(self, dominio_id: str):
        self.dominio_id  = dominio_id
        self.bundle_name = BUNDLE_NAMES.get(dominio_id)
        self.manifest    = None
        self.meta        = None
        self.mu          = None
        self.sigma       = None
        self.heads       = {}
        self._state_dict = None
        self._cargado    = False

        if self.bundle_name:
            self._cargar()

    def _cargar(self):
        zip_path = MODELOS_DIR / f"{self.bundle_name}.zip"
        if not zip_path.exists():
            logger.warning(
                f"Bundle no encontrado: {zip_path} · modo simulado activo")
            return

        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                nombres = z.namelist()

                def leer_json(sufijo):
                    for n in nombres:
                        if n.endswith(sufijo):
                            return json.loads(z.read(n))
                    return None

                def leer_npy(sufijo):
                    import io
                    for n in nombres:
                        if n.endswith(sufijo):
                            return np.load(
                                io.BytesIO(z.read(n)), allow_pickle=False)
                    return None

                self.manifest = leer_json("manifest.json")
                self.meta     = leer_json("backbone/meta.json")
                self.mu       = leer_npy("backbone/mu.npy")
                self.sigma    = leer_npy("backbone/sigma.npy")

                for n in nombres:
                    if n.endswith("head_spec.json"):
                        spec = json.loads(z.read(n))
                        self.heads[spec.get("name", n)] = spec

                # Cargar pesos PyTorch
                for n in nombres:
                    if n.endswith("phase_rnn_state_dict.pt"):
                        try:
                            import torch, io
                            buf = io.BytesIO(z.read(n))
                            self._state_dict = torch.load(
                                buf, map_location="cpu", weights_only=True)
                            logger.info(f"[BUNDLE] PyTorch cargado: {self.dominio_id}")
                        except ImportError:
                            logger.info("[BUNDLE] PyTorch no disponible · fallback geométrico")
                        except Exception as e:
                            logger.warning(f"[BUNDLE] Error cargando .pt: {e}")
                        break

            self._cargado = True
            logger.info(
                f"[BUNDLE] {self.bundle_name} · {len(self.heads)} cabezas")

        except Exception as e:
            logger.error(f"[BUNDLE] Error cargando {zip_path}: {e}")

    # ── Normalización ────────────────────────────────────────────
    def _normalizar(self, features: dict) -> "np.ndarray":
        cols = (self.meta or {}).get("feature_cols", FEATURE_COLS)
        # Mapear trigo/cobre/petroleo a features del backbone
        mapping = {
            "TensionElastica_TE": features.get("trigo", 0.5),
            "Persistencia_P":     features.get("petroleo", 0.5),
            "RuidoInstitucional_R": features.get("cobre", 0.5),
            "MomentoInercia_MI":  features.get(
                "MomentoInercia_MI",
                (features.get("trigo", 0.5) + features.get("cobre", 0.5)) / 2
            ),
        }
        vec = np.array([mapping.get(c, 0.5) for c in cols], dtype=np.float32)
        if self.mu is not None and self.sigma is not None:
            sigma_safe = np.where(self.sigma == 0, 1.0, self.sigma)
            vec = (vec - self.mu) / sigma_safe
        return vec

    # ── Inferencia de fase ────────────────────────────────────────
    def _inferir_fase(self, features: dict) -> dict:
        if self._state_dict is not None:
            return self._inferir_pytorch(features)
        return self._inferir_geometrico(features)

    def _inferir_pytorch(self, features: dict) -> dict:
        try:
            import torch, torch.nn as nn
            vec = self._normalizar(features)
            k   = (self.meta or {}).get("k", 10)
            n_f = len((self.meta or {}).get("feature_cols", FEATURE_COLS))
            n_l = len((self.meta or {}).get("labels", {0:"",1:"",2:"",3:""}))

            class GRU(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.gru = nn.GRU(n_f, 64, batch_first=True)
                    self.fc  = nn.Linear(64, n_l)
                def forward(self, x):
                    o, _ = self.gru(x)
                    return self.fc(o[:, -1, :])

            m = GRU()
            m.load_state_dict(self._state_dict, strict=False)
            m.eval()

            seq = torch.tensor(vec).unsqueeze(0).unsqueeze(0).repeat(1, k, 1)
            with torch.no_grad():
                probs = torch.softmax(m(seq), dim=-1).squeeze().tolist()

            if isinstance(probs, float):
                probs = [probs]
            fase_id = int(np.argmax(probs))
            return {"fase_id": fase_id,
                    "fase_label": FASES_BACKBONE[fase_id],
                    "probs": probs,
                    "confianza": round(max(probs), 3),
                    "modo": "pytorch"}
        except Exception as e:
            logger.warning(f"[BUNDLE] PyTorch inference error: {e}")
            return self._inferir_geometrico(features)

    def _inferir_geometrico(self, features: dict) -> dict:
        t = features.get("trigo", 0.5)
        c = features.get("cobre", 0.5)
        p = features.get("petroleo", 0.5)
        tension = math.sqrt((t**2 + p**2) / 2)
        resil   = max(0.0, c - max(0.0, tension - 0.65) * 0.5)
        m       = (t + c + p) / 3
        coher   = 1.0 - math.sqrt(
            ((t-m)**2 + (c-m)**2 + (p-m)**2) / 3)

        if tension >= 0.70 and resil < 0.55:
            fase_id = 1
        elif tension >= 0.70:
            fase_id = 2
        elif coher >= 0.75 and tension < 0.45:
            fase_id = 0
        else:
            fase_id = 3

        probs = [0.1, 0.1, 0.1, 0.1]
        probs[fase_id] = 0.7
        return {"fase_id": fase_id,
                "fase_label": FASES_BACKBONE[fase_id],
                "probs": probs, "confianza": 0.72,
                "modo": "geometrico"}

    # ── Ejecutar cabezas ──────────────────────────────────────────
    def _ejecutar_cabezas(self, fase_label: str, features: dict) -> str:
        t, c = features.get("trigo", 0.5), features.get("cobre", 0.5)
        mejor_score  = -1
        mejor_accion = "revisar_situacion"

        for nombre, spec in self.heads.items():
            fases_ok = (spec.get("phase_conditioning", {})
                            .get("active_in_phases", []))
            if fase_label not in fases_ok:
                continue
            tipo  = spec.get("type", "")
            score = t if "Trigo" in tipo else c
            if score > mejor_score:
                mejor_score  = score
                mejor_accion = nombre.replace("_head", "")

        return mejor_accion

    # ── Episodio completo ─────────────────────────────────────────
    def ejecutar_episodio(self, documentos_texto: str,
                          tipo_consulta: str,
                          features_externos: dict = None) -> dict:
        # Extraer features del texto si no vienen
        if features_externos:
            features = features_externos
        else:
            features = _extraer_features_texto(documentos_texto)

        if not self._cargado:
            return _episodio_simulado(self.dominio_id, features, tipo_consulta)

        fase_res = self._inferir_fase(features)
        fase_id  = fase_res["fase_id"]
        fase_lbl = fase_res["fase_label"]
        accion   = self._ejecutar_cabezas(fase_lbl, features)

        t, c, p = (features.get("trigo", 0.5),
                   features.get("cobre", 0.5),
                   features.get("petroleo", 0.5))
        tension  = round(math.sqrt((t**2 + p**2) / 2), 4)
        resil    = round(max(0.0, c - max(0.0, tension-0.65)*0.5), 4)
        mm       = (t+c+p)/3
        coher    = round(1.0 - math.sqrt(
            ((t-mm)**2+(c-mm)**2+(p-mm)**2)/3), 4)

        return {
            "heads":   {"trigo": t, "cobre": c, "petroleo": p},
            "estados": {
                "campos":       round(mm, 4),
                "tension":      tension,
                "coherencia":   coher,
                "resiliencia":  resil,
                "indice_telos": round(coher * resil, 4),
            },
            "sugerencia_tcl":  _generar_tcl(fase_lbl, accion,
                                             tension, tipo_consulta),
            "accion_sugerida": accion,
            "fase_backbone":   {"id": fase_id, "label": fase_lbl},
            "confianza":       fase_res["confianza"],
            "modo_motor":      f"bundle_{fase_res['modo']}",
        }


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def _extraer_features_texto(texto: str) -> dict:
    """Extrae Trigo/Cobre/Petróleo del texto via keywords."""
    palabras = texto.lower().split()
    total    = max(len(palabras), 1)

    KEYWORDS = {
        "trigo": ["urgente","conflicto","deuda","riesgo","sanción","mora",
                  "tensión","crítico","alerta","penalidad","queja","litigio",
                  "incumplimiento","demanda","vencimiento"],
        "cobre": ["recurso","capacidad","equipo","disponible","reserva",
                  "presupuesto","inventario","personal","habilidad","activo",
                  "garantía","financiamiento","proveedor","infraestructura"],
        "petroleo": ["proceso","flujo","continuidad","operación","estabilidad",
                     "protocolo","contrato","plan","seguimiento","eficiencia",
                     "sistema","rutina","cumplimiento","cronograma","balance"],
    }

    def sigmoid(n):
        freq = n / total * 100
        val  = 1 / (1 + math.exp(-(freq - 2) * 0.8))
        return round(max(0.05, min(0.95, val)), 4)

    conteos = {k: sum(1 for p in palabras if p in v)
               for k, v in KEYWORDS.items()}
    return {k: sigmoid(v) for k, v in conteos.items()}


def _episodio_simulado(dominio_id: str, features: dict,
                       tipo_consulta: str) -> dict:
    """Respuesta simulada cuando no hay bundle disponible."""
    t = features.get("trigo", 0.72)
    c = features.get("cobre", 0.65)
    p = features.get("petroleo", 0.81)
    return {
        "heads":   {"trigo": t, "cobre": c, "petroleo": p},
        "estados": {
            "campos":       round((t+c+p)/3, 4),
            "tension":      round(math.sqrt((t**2+p**2)/2), 4),
            "coherencia":   0.79,
            "resiliencia":  0.67,
            "indice_telos": 0.76,
        },
        "sugerencia_tcl": (
            f"[Simulado · {dominio_id}] Análisis de {tipo_consulta}: "
            "Coloca el bundle .zip en Backend/aprendiz_motor/modelos/ "
            "para activar el modelo real."
        ),
        "accion_sugerida": "instalar_bundle",
        "confianza":       0.60,
        "modo_motor":      "simulado_sin_bundle",
    }


def _generar_tcl(fase_label: str, accion: str,
                 tension: float, tipo: str) -> str:
    plantillas = {
        "Estabilidad (baja energía)":
            f"Sistema estable. Tensión baja ({tension:.2f}). "
            f"Acción recomendada: {accion.replace('_',' ')}.",
        "Tensión acumulada (peligro de latigazo)":
            f"Tensión acumulada ({tension:.2f}). Riesgo de latigazo. "
            f"Ejecutar: {accion.replace('_',' ')}.",
        "Ruptura en curso (brinco ocurriendo)":
            f"Ruptura activa ({tension:.2f}). Intervención inmediata: "
            f"{accion.replace('_',' ')}.",
        "Fase invariante (nueva norma / cresta sostenida)":
            f"Nueva norma establecida. Consolidar con: "
            f"{accion.replace('_',' ')}.",
    }
    return plantillas.get(fase_label,
                          f"Estado: {fase_label}. Acción: {accion}.")


# ─────────────────────────────────────────────────────────────────
# API PÚBLICA — compatible con server.py existente
# ─────────────────────────────────────────────────────────────────

_motor_instancia: Optional[BundleLoader] = None


def inicializar_motor(config: Dict[str, Any]) -> bool:
    global _motor_instancia
    dominio_id = config.get("dominio_id")
    if not dominio_id:
        logger.error("dominio_id no especificado")
        return False
    try:
        _motor_instancia = BundleLoader(dominio_id)
        logger.info(f"Motor inicializado: {dominio_id} · "
                    f"bundle={'OK' if _motor_instancia._cargado else 'simulado'}")
        return True
    except Exception as e:
        logger.error(f"Error inicializando motor: {e}")
        return False


def ejecutar_episodio(documentos_texto: str,
                      tipo_consulta: str,
                      features_externos: dict = None) -> Dict[str, Any]:
    global _motor_instancia
    if _motor_instancia is None:
        raise RuntimeError(
            "Motor no inicializado. Llamar inicializar_motor() primero.")
    return _motor_instancia.ejecutar_episodio(
        documentos_texto, tipo_consulta, features_externos)


def obtener_estado_motor() -> Dict[str, Any]:
    global _motor_instancia
    if _motor_instancia is None:
        return {"inicializado": False}
    return {
        "inicializado":    True,
        "dominio_id":      _motor_instancia.dominio_id,
        "bundle_cargado":  _motor_instancia._cargado,
        "bundle_nombre":   _motor_instancia.bundle_name,
        "cabezas":         len(_motor_instancia.heads),
        "pytorch_activo":  _motor_instancia._state_dict is not None,
        "modelo_status":   "bundle_real" if _motor_instancia._cargado
                           else "simulado",
    }

