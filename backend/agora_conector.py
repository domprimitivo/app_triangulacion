"""
El Ágora Unificado — Retícula de Triangulación (nuevo elemento de habitabilidad).

Puerto FIEL de `conector.py` (motor ciego al dominio) + los 3 primitivos operativos
de fábrica (saturacion, deuda_backlog, deficit_acoplado), fórmulas validadas por el usuario.

Un solo motor. El conocimiento del dominio vive en el JSON + los primitivos.
Ingesta de coordenadas CONOCIDas → el primitivo aporta la coordenada DESCONOCIDA (la
disonancia x) → paquete por nodo, para graficar el plano (x vs y). 100% local/soberano.

Salida = las disonancias. Sin KPIs, sin Cantor Inverso, sin geodésicas.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from runtime_paths import get_base_dir

BASE = get_base_dir()
AGORA_DIR = BASE / "flujo" / "agora"

# id corto (archivo) → etiqueta legible
DOMINIOS = {
    "hotel": "Hotel (lado costo)",
    "restaurante": "Restaurante",
    "clinica": "Clínica",
    "logistica": "Logística",
    "retail": "Retail",
    "fabrica": "Fábrica (integridad operativa)",
    "gobierno": "Gobierno (fraude de dinero público)",
}


# ── Librería de primitivos de ancla ─────────────────────────────────────────
PRIMITIVOS: dict[str, Callable[[dict, dict], dict]] = {}


def primitivo(nombre: str):
    def reg(fn):
        PRIMITIVOS[nombre] = fn
        return fn
    return reg


@primitivo("disonancia_vs_fisico")
def disonancia_vs_fisico(obs: dict, params: dict) -> dict:
    reportado = obs[params["reportado"]]
    fisico = obs[params["fisico_obs"]] * params.get("fisico_factor", 1.0)
    if params.get("orientacion", "reportado_excede") == "fisico_excede":
        dison = (fisico - reportado) / fisico if fisico else 0.0
    else:
        dison = (reportado - fisico) / reportado if reportado else 0.0
    x = params.get("peso", 1.0) * max(dison, 0.0) / params.get("div", 0.25)
    detalle = {"disonancia": round(dison, 3), "reportado": round(reportado, 1),
               "fisico_justificado": round(fisico, 1)}
    if "sec_obs" in params:
        sec = obs[params["sec_obs"]]
        x += params.get("sec_peso", 0.0) * sec
        detalle["secundario"] = round(sec, 3)
    return {"x": float(np.clip(x, 0.0, 1.0)), "detalle": detalle}


@primitivo("coherencia_stock")
def coherencia_stock(obs: dict, params: dict) -> dict:
    activo = obs[params["activo"]]
    just = obs[params["justificacion"]]
    dison = (activo - just) / activo if activo else 0.0
    x = params.get("peso", 1.0) * max(dison, 0.0) / params.get("div", 0.8)
    return {"x": float(np.clip(x, 0.0, 1.0)),
            "detalle": {"disonancia": round(dison, 3), "activo": activo, "justificacion": just}}


# ── Primitivos operativos de fábrica (fórmulas confirmadas por el usuario) ────
@primitivo("saturacion")
def saturacion(obs: dict, params: dict) -> dict:
    """x = cuánto por encima de su capacidad corre la línea. carga/capacidad, recortado por div."""
    carga = obs[params["carga"]]
    cap = obs[params["capacidad"]]
    dison = max(carga / cap - 1.0, 0.0) if cap else 0.0
    x = params.get("peso", 1.0) * dison / params.get("div", 0.25)
    return {"x": float(np.clip(x, 0.0, 1.0)),
            "detalle": {"disonancia": round(dison, 3), "carga": carga, "capacidad": cap}}


@primitivo("deuda_backlog")
def deuda_backlog(obs: dict, params: dict) -> dict:
    """x = backlog/(backlog+cierre) + término secundario opcional (estado_maquina)."""
    backlog = obs[params["backlog"]]
    cierre = obs[params["cierre"]]
    dison = backlog / (backlog + cierre) if (backlog + cierre) else 0.0
    x = params.get("peso", 1.0) * max(dison, 0.0) / params.get("div", 0.5)
    detalle = {"disonancia": round(dison, 3), "backlog": backlog, "cierre": cierre}
    if "sec_obs" in params:
        sec = obs[params["sec_obs"]]
        x += params.get("sec_peso", 0.0) * sec
        detalle["secundario"] = round(sec, 3)
    return {"x": float(np.clip(x, 0.0, 1.0)), "detalle": detalle}


def deficit_acoplado(obs: dict, params: dict) -> dict:
    """y interna de conservación: déficit medio de señales acopladas respecto a su esperado."""
    esperado = params.get("esperado", 1.0)
    senales = params["senales"]
    deficits = [max(esperado - obs[s], 0.0) for s in senales]
    deficit = sum(deficits) / len(deficits) if deficits else 0.0
    y = float(np.clip(deficit / params.get("div", 0.25), 0.0, 1.0))
    return {"y": y, "detalle": {"deficit": round(deficit, 3), "senales": senales}}


PRIMITIVOS["deficit_acoplado"] = deficit_acoplado  # usado como coordenada y interna


def avance_throughput(obs: dict, params: Optional[dict]) -> Optional[float]:
    if not params or not params.get("numerador") or not params.get("denominador"):
        return None
    num, den = obs[params["numerador"]], obs[params["denominador"]]
    return round(num / den, 3) if den else None


# ── El motor conector (ciego al dominio) ─────────────────────────────────────
class Conector:
    def __init__(self, dominio_json: dict, dominio_id: str):
        self.dom = dominio_json
        self.dominio_id = dominio_id
        self.dominio = dominio_json["dominio"]

    def _ingesta(self, entrada: dict, nodo_cfg: dict) -> dict:
        campos = nodo_cfg["observables"]
        faltan = [c for c in campos if c not in entrada]
        if faltan:
            raise ValueError(f"Faltan observables {faltan} para el nodo '{nodo_cfg.get('nodo','?')}'")
        return {c: entrada[c] for c in campos}

    def _coordenada_y(self, entrada: dict, obs: dict, nodo_cfg: dict) -> dict:
        cy = nodo_cfg.get("coordenada_y")
        if not cy:
            return {"tipo": "ninguna", "valor": None, "gamma": None}
        # y interna calculada por un primitivo (fábrica: deficit_acoplado)
        if "primitivo" in cy:
            prim = PRIMITIVOS[cy["primitivo"]]
            r = prim({**entrada, **obs}, cy["params"])
            return {"tipo": "interna", "valor": r["y"], "gamma": cy.get("gamma", 0.5),
                    "detalle": r["detalle"]}
        # y externa importada (dinero, marcador 69-B)
        senal = entrada.get(cy["senal_campo"])
        gamma = entrada.get(cy["gamma_campo"], cy.get("gamma_default", 0.5))
        return {"tipo": "externa", "valor": senal, "gamma": gamma}

    def paquete_para(self, nodo: str, entrada: dict) -> dict:
        cfg = dict(self.dom["nodos"][nodo])
        cfg["nodo"] = nodo
        # Nodo blando/orientador: sin ancla, solo dinámica de coherencia (orienta, no triangula)
        if cfg.get("tipo") == "blanda" or "ancla" not in cfg:
            obs = self._ingesta(entrada, cfg)
            return {"nodo": nodo, "dominio": self.dominio, "tipo": "blanda",
                    "orienta": True, "x": None, "avance": None,
                    "coherencia": obs.get("coherencia"),
                    "lectura": cfg.get("lectura", "dinamica_coherencia"),
                    "y": {"tipo": "ninguna", "valor": None, "gamma": None},
                    "rol": cfg.get("rol", "")}
        obs = self._ingesta(entrada, cfg)
        prim = PRIMITIVOS[cfg["ancla"]["primitivo"]]
        anc = prim({**entrada, **obs}, cfg["ancla"]["params"])
        avance = avance_throughput(obs, cfg.get("avance"))
        y = self._coordenada_y(entrada, obs, cfg)
        return {
            "nodo": nodo, "dominio": self.dominio, "tipo": cfg.get("tipo", "flujo"),
            "rol": cfg.get("rol", ""),
            "primitivo": cfg["ancla"]["primitivo"],
            "x": anc["x"], "x_detalle": anc["detalle"],
            "avance": avance, "y": y,
            "token": entrada.get("token"), "timestamp_fase": entrada.get("timestamp_fase"),
        }

    def generar_todos(self, entradas: dict[str, dict]) -> dict[str, dict]:
        return {n: self.paquete_para(n, e) for n, e in entradas.items()}


# ── Carga de dominios ────────────────────────────────────────────────────────
def cargar_dominio(dominio_id: str) -> dict:
    p = AGORA_DIR / f"dominio_{dominio_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Dominio del Ágora no encontrado: {dominio_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def listar_dominios() -> list[dict]:
    out = []
    for did, label in DOMINIOS.items():
        try:
            dom = cargar_dominio(did)
        except FileNotFoundError:
            continue
        out.append({
            "id": did, "etiqueta": label, "dominio": dom.get("dominio"),
            "triangulacion": dom.get("triangulacion", ""),
            "primaria": dom.get("primaria", ""),
            "n_nodos": len(dom.get("nodos", {})),
        })
    return out


def info_dominio(dominio_id: str) -> dict:
    dom = cargar_dominio(dominio_id)
    nodos = []
    for nombre, cfg in dom.get("nodos", {}).items():
        cy = cfg.get("coordenada_y", {})
        nodos.append({
            "nodo": nombre, "tipo": cfg.get("tipo", "flujo"), "rol": cfg.get("rol", ""),
            "descripcion": cfg.get("_descripcion", ""),
            "observables": cfg.get("observables", []),
            "primitivo": cfg.get("ancla", {}).get("primitivo") if "ancla" in cfg else None,
            "tiene_avance": bool(cfg.get("avance") and cfg["avance"].get("numerador")),
            "y_tipo": "interna" if "primitivo" in cy else ("externa" if cy else "ninguna"),
        })
    return {
        "id": dominio_id, "etiqueta": DOMINIOS.get(dominio_id, dominio_id),
        "dominio": dom.get("dominio"), "descripcion": dom.get("_descripcion", ""),
        "triangulacion": dom.get("triangulacion", ""), "primaria": dom.get("primaria", ""),
        "nodos": nodos,
    }


# ── Generador de valores demo (coordenadas conocidas plausibles) ─────────────
_SMALL = ("concentracion", "coherencia", "gamma", "senal", "yield", "buffer",
          "estado", "tasa", "carga_relativa", "patron")


def _demo_valor(nombre: str) -> float:
    n = nombre.lower()
    if any(k in n for k in _SMALL):
        return 0.6
    return 100.0


def demo_entradas(dominio_id: str) -> dict[str, dict]:
    dom = cargar_dominio(dominio_id)
    entradas = {}
    for nombre, cfg in dom.get("nodos", {}).items():
        e = {"token": "TOK-DEMO", "timestamp_fase": 0.42}
        for obs in cfg.get("observables", []):
            e[obs] = _demo_valor(obs)
        anc = cfg.get("ancla", {})
        p = anc.get("params", {})
        prim = anc.get("primitivo")
        if prim == "disonancia_vs_fisico":
            fisico_obs = 1000.0
            factor = p.get("fisico_factor", 1.0)
            fisico = fisico_obs * factor
            if p.get("orientacion", "reportado_excede") == "fisico_excede":
                e[p["reportado"]] = round(fisico * 0.88, 1)
            else:
                e[p["reportado"]] = round(fisico * 1.15, 1)
            e[p["fisico_obs"]] = fisico_obs
            if "sec_obs" in p:
                e[p["sec_obs"]] = 0.5
        elif prim == "coherencia_stock":
            e[p["activo"]] = 1000.0
            e[p["justificacion"]] = 700.0
        elif prim == "saturacion":
            e[p["capacidad"]] = 1000.0
            e[p["carga"]] = 1200.0
        elif prim == "deuda_backlog":
            e[p["backlog"]] = 120.0
            e[p["cierre"]] = 60.0
            if "sec_obs" in p:
                e[p["sec_obs"]] = 0.4
        av = cfg.get("avance")
        if av and av.get("numerador"):
            e.setdefault(av["numerador"], 300.0)
            e.setdefault(av["denominador"], 120.0)
        cy = cfg.get("coordenada_y", {})
        if "primitivo" in cy:
            for s in cy.get("params", {}).get("senales", []):
                e.setdefault(s, 0.6)
        else:
            e.setdefault(cy.get("senal_campo", "y_senal"), 0.6)
            e.setdefault(cy.get("gamma_campo", "y_gamma"), 0.5)
        if cfg.get("tipo") == "blanda":
            e["coherencia"] = 0.55
        entradas[nombre] = e
    return entradas


def triangular(dominio_id: str, entradas: Optional[dict] = None,
               umbral: Optional[float] = None, origen_label: Optional[str] = None,
               guardar: bool = True) -> dict:
    dom = cargar_dominio(dominio_id)
    con = Conector(dom, dominio_id)
    if not entradas:
        entradas = demo_entradas(dominio_id)
        origen = "Operación demo (coordenadas conocidas plausibles)"
    else:
        origen = origen_label or "Ingesta de coordenadas conocidas"
    if umbral is None:
        umbral = obtener_umbral(dominio_id)
    paquetes = con.generar_todos(entradas)
    # Puntos del plano (x = disonancia, y = coordenada dinero/interna)
    plano = []
    for nodo, paq in paquetes.items():
        if paq.get("x") is None:
            continue
        x = round(paq["x"], 3)
        alerta = x >= umbral
        paq["alerta"] = alerta
        plano.append({"nodo": nodo, "x": x, "alerta": alerta,
                      "y": paq["y"].get("valor"), "y_tipo": paq["y"].get("tipo"),
                      "tipo": paq["tipo"], "avance": paq["avance"]})
    n_alertas = sum(1 for p in plano if p["alerta"])
    resultado = {
        "dominio_id": dominio_id, "etiqueta": DOMINIOS.get(dominio_id, dominio_id),
        "dominio": dom.get("dominio"), "triangulacion": dom.get("triangulacion", ""),
        "origen": origen, "umbral": umbral, "n_alertas": n_alertas,
        "paquetes": paquetes, "plano": plano,
    }
    if guardar and plano:
        guardar_corrida(dominio_id, resultado)
    return resultado


# ── Umbral de alerta por dominio ─────────────────────────────────────────────
UMBRALES_PATH = AGORA_DIR / "umbrales.json"
UMBRAL_DEFAULT = 0.5


def _leer_umbrales() -> dict:
    if UMBRALES_PATH.exists():
        try:
            return json.loads(UMBRALES_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def obtener_umbral(dominio_id: str) -> float:
    return float(_leer_umbrales().get(dominio_id, UMBRAL_DEFAULT))


def fijar_umbral(dominio_id: str, valor: float) -> dict:
    valor = max(0.0, min(1.0, float(valor)))
    u = _leer_umbrales()
    u[dominio_id] = valor
    UMBRALES_PATH.write_text(json.dumps(u, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"dominio_id": dominio_id, "umbral": valor}


# ── Ingesta real: buffer webhook + parseo de archivos ────────────────────────
INGESTA_DIR = AGORA_DIR / "ingesta"


def _buffer_path(dominio_id: str) -> Path:
    INGESTA_DIR.mkdir(parents=True, exist_ok=True)
    return INGESTA_DIR / f"{dominio_id}.json"


def buffer_recibir(dominio_id: str, payload) -> dict:
    """Recibe coordenadas en vivo. Formato: {nodo: {obs...}} o {entradas:{...}}.
    Hace merge por nodo (valores más recientes ganan)."""
    from datetime import datetime, timezone
    if isinstance(payload, dict) and "entradas" in payload:
        payload = payload["entradas"]
    if not isinstance(payload, dict):
        raise ValueError("El payload debe ser {nodo: {observable: valor}}.")
    p = _buffer_path(dominio_id)
    actual = {}
    if p.exists():
        try:
            actual = json.loads(p.read_text(encoding="utf-8")).get("entradas", {})
        except Exception:
            actual = {}
    for nodo, obs in payload.items():
        if isinstance(obs, dict):
            actual.setdefault(nodo, {}).update(obs)
    data = {"entradas": actual, "ultimo": datetime.now(timezone.utc).isoformat(),
            "n_nodos": len(actual)}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"dominio_id": dominio_id, "nodos_en_buffer": list(actual.keys()),
            "ultimo": data["ultimo"]}


def buffer_estado(dominio_id: str) -> dict:
    p = _buffer_path(dominio_id)
    if not p.exists():
        return {"dominio_id": dominio_id, "entradas": {}, "n_nodos": 0, "ultimo": None}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        d = {"entradas": {}}
    return {"dominio_id": dominio_id, "entradas": d.get("entradas", {}),
            "n_nodos": len(d.get("entradas", {})), "ultimo": d.get("ultimo")}


def buffer_vaciar(dominio_id: str) -> dict:
    p = _buffer_path(dominio_id)
    if p.exists():
        p.unlink()
    return {"dominio_id": dominio_id, "vaciado": True}


def parse_archivo(nombre: str, datos: bytes) -> dict:
    """Parsea JSON ({nodo:{obs}} o {entradas:{...}}) o CSV (columna 'nodo' + observables)."""
    import csv
    import io
    try:
        texto = datos.decode("utf-8")
    except Exception:
        return {}
    st = texto.strip()
    # JSON
    try:
        obj = json.loads(st)
        if isinstance(obj, dict):
            return obj.get("entradas", obj)
    except Exception:
        pass
    # CSV: cada fila un nodo; columna 'nodo' + observables numéricos
    entradas = {}
    try:
        reader = csv.DictReader(io.StringIO(texto))
        for row in reader:
            low = {(k or "").strip().lower(): v for k, v in row.items()}
            nodo = low.get("nodo") or low.get("node") or low.get("subdominio")
            if not nodo:
                continue
            e = {}
            for k, v in row.items():
                kk = (k or "").strip()
                if kk.lower() in ("nodo", "node", "subdominio") or v is None or v == "":
                    continue
                try:
                    e[kk] = float(v)
                except ValueError:
                    e[kk] = v
            entradas[nodo.strip()] = e
    except Exception:
        return {}
    return entradas


# ── Historial de triangulaciones por dominio ─────────────────────────────────
HISTORIAL_DIR = AGORA_DIR / "historial"


def _hist_path(dominio_id: str) -> Path:
    HISTORIAL_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORIAL_DIR / f"{dominio_id}.jsonl"


def guardar_corrida(dominio_id: str, resultado: dict) -> None:
    from datetime import datetime, timezone
    corrida = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "umbral": resultado.get("umbral"),
        "origen": resultado.get("origen"),
        "n_alertas": resultado.get("n_alertas", 0),
        "nodos": [{"nodo": p["nodo"], "x": p["x"], "y": p["y"], "alerta": p["alerta"]}
                  for p in resultado.get("plano", [])],
    }
    with open(_hist_path(dominio_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(corrida, ensure_ascii=False) + "\n")


def leer_historial(dominio_id: str, limit: int = 50) -> dict:
    p = _hist_path(dominio_id)
    if not p.exists():
        return {"dominio_id": dominio_id, "corridas": [], "series": {}, "nodos": []}
    lineas = [l for l in p.read_text(encoding="utf-8").split("\n") if l.strip()]
    corridas = []
    for l in lineas:
        try:
            corridas.append(json.loads(l))
        except Exception:
            continue
    corridas = corridas[-limit:]
    # Series por nodo: evolución de x a lo largo de las corridas
    series: dict[str, list] = {}
    nodos: list[str] = []
    for i, c in enumerate(corridas):
        for n in c.get("nodos", []):
            series.setdefault(n["nodo"], []).append(
                {"i": i, "ts": c["ts"], "x": n["x"], "alerta": n["alerta"]})
            if n["nodo"] not in nodos:
                nodos.append(n["nodo"])
    return {"dominio_id": dominio_id, "corridas": corridas, "series": series,
            "nodos": nodos, "total": len(lineas)}


def vaciar_historial(dominio_id: str) -> dict:
    p = _hist_path(dominio_id)
    if p.exists():
        p.unlink()
    return {"dominio_id": dominio_id, "vaciado": True}

