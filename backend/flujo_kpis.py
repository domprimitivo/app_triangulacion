"""
Flujo de KPIs — Cucurucho → 7 KPIs holográficos → Lazo de control.

Piezas del flujo (100% local, soberano):
  cliente (client_id) ── indica ──► dominio (domain_ref)
        │                              │
        │                              └── define las 7 variables/polos + umbrales
        ▼
  cucurucho / embudo  ── recibe archivos de operación (cosecha, pagos, ...) ──►
        AG3 (limpiador) + AG5 (ingeniero de features) SEPARAN los 7 KPIs
        holográficos + features de control ──► ENTRADA LIMPIA para el lazo.

Dominios empresariales (6) = únicos válidos. El palenque de mezcal
(dom_fermentacion_lotes_v1) es SOLO demostración del flujo.
"""

import json
import csv
import io
import re
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from lazo_generico import DOMINIO_CVD, lazo_asesoria, lazo_agencia
from compresion_geometrica import comprimir as _comprimir_codec

BASE = Path(__file__).resolve().parent
FLUJO_DIR = BASE / "flujo"
MEMORIA_DIR = FLUJO_DIR / "memoria"
MAIN_DIR = BASE.parent  # /app (donde viven los cucurucho_*.json de los 6 dominios)

# Sinónimos de nombres de columnas reales → campo canónico esperado por dominio.
SINONIMOS = {
    "ocupacion_pct": ["occupancy", "ocupacion", "occ", "occup"],
    "ocupacion_agenda": ["agenda", "citas_ocupadas", "booking"],
    "ocupacion_carga": ["fill_rate", "carga", "loadfactor"],
    "otif": ["ontimeinfull", "on_time_in_full", "cumplimiento"],
    "a_tiempo": ["ontime", "puntualidad", "a_tiempo_pct"],
    "ticket_promedio": ["avgticket", "ticket_medio", "aov"],
    "conversion": ["conversion_rate", "cr", "tasa_conversion"],
    "pagos_a_tiempo": ["pagospuntuales", "on_time_payments", "cxc_a_tiempo"],
    "flujo_caja": ["cashflow", "flujo", "liquidez"],
    "cartera_vencida": ["overdue", "vencido", "mora"],
    "satisfaccion": ["csat", "nps", "satisfaction"],
    "quejas": ["complaints", "reclamos", "tickets_queja"],
    "devoluciones": ["returns", "devol", "refunds"],
    "defectos": ["defects", "ppm", "no_conformes"],
    "oee": ["overall_equipment", "eficiencia_global"],
    "no_show": ["noshow", "inasistencia", "ausencias_cita"],
}

# Los 6 dominios empresariales válidos (únicos productivos)
DOMINIOS_EMPRESARIALES = [
    {"domain_id": "dom_restaurante_v1", "descriptor": "Restaurante / Food Service"},
    {"domain_id": "dom_retail_v1",      "descriptor": "Retail / Punto de venta"},
    {"domain_id": "dom_hotel_v1",       "descriptor": "Hotelería"},
    {"domain_id": "dom_fabrica_v1",     "descriptor": "Manufactura / Fábrica"},
    {"domain_id": "dom_logistica_v1",   "descriptor": "Logística / Distribución"},
    {"domain_id": "dom_clinica_v1",     "descriptor": "Clínica / Salud"},
]

CUCURUCHO_REF = "cucurucho_base_v1"


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cargar_cliente(client_id: str) -> dict:
    p = FLUJO_DIR / "clientes" / f"{client_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Cliente no encontrado: {client_id}")
    return _load_json(p)


def cargar_dominio(domain_id: str) -> dict:
    p = FLUJO_DIR / "dominios" / f"{domain_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Dominio no encontrado: {domain_id}")
    return _load_json(p)


def cargar_params(params_ref: str) -> dict:
    p = FLUJO_DIR / "params" / f"{params_ref}.json"
    if not p.exists():
        raise FileNotFoundError(f"Parametrización no encontrada: {params_ref}")
    return _load_json(p)


def cargar_cucurucho() -> dict:
    return _load_json(FLUJO_DIR / "cucurucho" / f"{CUCURUCHO_REF}.json")


def listar_clientes() -> List[dict]:
    d = FLUJO_DIR / "clientes"
    return [_load_json(f) for f in sorted(d.glob("*.json"))]


def listar_dominios() -> dict:
    """6 empresariales (válidos) + demo (palenque) si existe."""
    demo = []
    dd = FLUJO_DIR / "dominios"
    for f in sorted(dd.glob("*.json")):
        cfg = _load_json(f)
        if cfg.get("es_demo"):
            demo.append({"domain_id": cfg["domain_id"], "descriptor": cfg["descriptor"], "es_demo": True})
    return {"empresariales": DOMINIOS_EMPRESARIALES, "demostracion": demo}


# ─── AG3 limpiador + AG5 ingeniero de features: separar señales de operación ──
def _categoria_de(nombre: str, categorias: dict) -> Optional[str]:
    n = nombre.lower()
    for cat, cfg in categorias.items():
        if any(k in n for k in cfg.get("keywords", [])):
            return cat
    return None


def _agg_numericos(datos: bytes) -> Dict[str, float]:
    """Promedia columnas numéricas de un CSV/JSON (limpieza AG3)."""
    try:
        texto = datos.decode("utf-8")
    except Exception:
        return {}
    # JSON objeto
    try:
        obj = json.loads(texto)
        if isinstance(obj, dict):
            return {k: float(v) for k, v in obj.items()
                    if isinstance(v, (int, float)) and not isinstance(v, bool)}
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            acc: Dict[str, list] = {}
            for row in obj:
                for k, v in row.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        acc.setdefault(k, []).append(float(v))
            return {k: float(np.mean(v)) for k, v in acc.items()}
    except Exception:
        pass
    # CSV
    try:
        reader = csv.DictReader(io.StringIO(texto))
        acc: Dict[str, list] = {}
        for row in reader:
            for k, v in row.items():
                try:
                    acc.setdefault(k, []).append(float(v))
                except (TypeError, ValueError):
                    continue
        return {k: float(np.mean(v)) for k, v in acc.items() if v}
    except Exception:
        return {}


def _extraer_columnas(datos: bytes) -> Dict[str, list]:
    """Devuelve {columna: [valores numéricos]} desde CSV/JSON (para calibrar rangos)."""
    try:
        texto = datos.decode("utf-8")
    except Exception:
        return {}
    acc: Dict[str, list] = {}
    try:
        obj = json.loads(texto)
        rows = obj if isinstance(obj, list) else [obj]
        for row in rows:
            if isinstance(row, dict):
                for k, v in row.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        acc.setdefault(k, []).append(float(v))
        if acc:
            return acc
    except Exception:
        pass
    try:
        for row in csv.DictReader(io.StringIO(texto)):
            for k, v in row.items():
                try:
                    acc.setdefault(k, []).append(float(v))
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass
    return acc


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _mapear_columnas(cols: Dict[str, list], esperadas: List[str]) -> Dict[str, list]:
    """Mapea nombres de columnas REALES → campo canónico esperado (alias + sinónimos)."""
    normmap = {_norm_name(k): k for k in cols}
    out: Dict[str, list] = {}
    for canon in esperadas:
        nc = _norm_name(canon)
        found = normmap.get(nc)
        if not found:
            for rn, orig in normmap.items():
                if nc and (nc in rn or rn in nc):
                    found = orig
                    break
        if not found:
            for syn in SINONIMOS.get(canon, []):
                ns = _norm_name(syn)
                for rn, orig in normmap.items():
                    if ns and (ns in rn or rn in ns):
                        found = orig
                        break
                if found:
                    break
        if found:
            out[canon] = cols[found]
    return out


def extraer_senales(archivos: List[dict], mapa: dict):
    """
    Parte del baseline demo y superpone datos REALES (columnas mapeadas por dominio).
    Devuelve (senales, rangos_observados) — los rangos sirven para auto-calibrar.
    """
    categorias = mapa.get("categorias_operacion", {})
    senales = json.loads(json.dumps(mapa.get("demo_operacion", {})))  # baseline demo
    rangos: Dict[str, list] = {}
    for a in archivos or []:
        cat = _categoria_de(a["nombre"], categorias)
        if not cat:
            continue
        cols = _extraer_columnas(a["datos"])
        esperadas = categorias.get(cat, {}).get("columnas_esperadas", [])
        cols = _mapear_columnas(cols, esperadas)
        for canon, vals in cols.items():
            if not vals:
                continue
            senales.setdefault(cat, {})[canon] = round(float(np.mean(vals)), 4)
            rangos[f"{cat}.{canon}"] = [float(min(vals)), float(max(vals))]
    return senales, rangos


def _norm(v: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def preparar_kpis(senales: Dict[str, Dict[str, float]], mapa: dict,
                  rangos: Optional[dict] = None, calibrar: bool = False):
    """
    AG5: separa los 7 KPIs (0-1). Si calibrar=True usa el rango observado en los
    datos reales para cada señal (el semáforo refleja la operación exacta).
    Devuelve (kpis, calibracion_aplicada).
    """
    kpis: Dict[str, float] = {}
    calib: Dict[str, list] = {}
    for kpi, terminos in mapa.get("kpi_map", {}).items():
        total = 0.0
        peso_total = 0.0
        for t in terminos:
            cat, col = t["signal"].split(".", 1)
            val = senales.get(cat, {}).get(col)
            if val is None:
                continue
            lo, hi = t.get("norm", [0.0, 1.0])
            if calibrar and rangos and t["signal"] in rangos:
                rlo, rhi = rangos[t["signal"]]
                if rhi > rlo:
                    lo, hi = rlo, rhi
                    calib[t["signal"]] = [round(lo, 3), round(hi, 3)]
            x = _norm(float(val), lo, hi)
            if t.get("invertir"):
                x = 1.0 - x
            total += t.get("peso", 1.0) * x
            peso_total += t.get("peso", 1.0)
        kpis[kpi] = round(total / peso_total, 4) if peso_total else 0.5
    return kpis, calib


def detalle_discreto(senales: Dict[str, Dict[str, float]], params: dict) -> Dict[str, list]:
    """
    Para cada métrica geométrica, sus datos tradicionales (discretos) que la
    componen. Hace explícita la armonía dato discreto ↔ contraparte geométrica.
    """
    out: Dict[str, list] = {}
    for kpi, terminos in params.get("kpi_map", {}).items():
        discretos = []
        for t in terminos:
            cat, col = t["signal"].split(".", 1)
            val = senales.get(cat, {}).get(col)
            lo, hi = t.get("norm", [0.0, 1.0])
            norm = None if val is None else round(_norm(float(val), lo, hi), 3)
            discretos.append({"signal": t["signal"], "categoria": cat, "campo": col,
                              "valor": val, "norm": norm, "peso": t.get("peso", 1.0)})
        out[kpi] = discretos
    return out


def control_features(kpis: Dict[str, float], dominio: dict, overrides: dict) -> dict:
    """Features de control adicionales para el lazo (viabilidad, firmeza, coherencia)."""
    umb = dominio.get("umbrales_operativos", {})
    c_crit = overrides.get("c_viabilidad_critico", umb.get("c_viabilidad_critico", 1.07))
    firmeza_min = umb.get("firmeza_suelo_minima_R", 0.60)
    delta_max = umb.get("delta_max_coherencia", 0.12)

    firmeza_R = kpis.get("Retorno al Suelo", 0.5)
    c_viab = round(1.0 + 0.1 * (0.6 * kpis.get("Tensión TR", 0.5) + 0.4 * kpis.get("Ruptura de Fase", 0.5)), 3)
    delta_coh = round(float(np.std(list(kpis.values()))), 3)
    return {
        "c_viabilidad": c_viab, "c_viabilidad_critico": c_crit, "viable": c_viab < c_crit,
        "firmeza_suelo_R": round(firmeza_R, 3), "firmeza_minima_R": firmeza_min, "suelo_firme": firmeza_R >= firmeza_min,
        "delta_coherencia": delta_coh, "delta_max_coherencia": delta_max, "coherente": delta_coh <= delta_max,
    }


def agentes_activos(cucurucho: dict) -> List[dict]:
    core = cucurucho.get("agentes_core", {})
    prep = {"AG3_limpiador", "AG5_ingeniero_features"}
    return [{"id": k, "prepara_kpis": k in prep}
            for k, v in core.items() if v.get("activo")]


POLOS_STD = ["Permeabilidad", "Tensión TR", "Sutura", "Retorno al Suelo",
             "Estancamiento", "Ruptura de Fase", "Resonancia"]
UMBRALES_STD = {"c_viabilidad_critico": 1.070, "firmeza_suelo_minima_R": 0.60, "delta_max_coherencia": 0.12}


def _sector(domain_id: str) -> str:
    s = domain_id
    if s.startswith("dom_"):
        s = s[4:]
    if s.endswith("_v1"):
        s = s[:-3]
    return s


def cargar_mapa_dominio(domain_id: str) -> dict:
    """
    Mapa de las 7 métricas (doble hélice: dato tradicional ↔ geométrico) para
    el dominio. Demo → params palenque. Empresarial → mapa_metricas del
    cucurucho_{sector}_v1.json en main.
    """
    if domain_id == "dom_fermentacion_lotes_v1":
        return cargar_params("palenque_fermentacion_params")
    p = MAIN_DIR / f"cucurucho_{_sector(domain_id)}_v1.json"
    if not p.exists():
        raise FileNotFoundError(f"Cucurucho de dominio no encontrado: {p.name}")
    cfg = _load_json(p)
    mapa = cfg.get("mapa_metricas")
    if not mapa:
        raise FileNotFoundError(f"El cucurucho {p.name} no define 'mapa_metricas'.")
    return mapa


def _descriptor_dominio(domain_id: str) -> str:
    for d in DOMINIOS_EMPRESARIALES:
        if d["domain_id"] == domain_id:
            return d["descriptor"]
    return domain_id


def guardar_memoria(domain_id: str, observacion: dict) -> dict:
    """Guarda la observación en memoria, COMPRIMIDA automáticamente por el códec."""
    d = MEMORIA_DIR / domain_id
    d.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(observacion, ensure_ascii=False).encode("utf-8")
    paquete = _comprimir_codec([{"nombre": "observacion.json", "datos": payload}], org_id=domain_id)
    rid = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    (d / f"{rid}.mocg.json").write_text(json.dumps(paquete), encoding="utf-8")
    sr = paquete.get("shape_report", {}).get("compression", {})
    return {"id": rid, "created": paquete.get("created_utc"),
            "ratio": sr.get("ratio"), "original_bytes": sr.get("original_bytes")}


def listar_memoria(domain_id: str) -> List[dict]:
    d = MEMORIA_DIR / domain_id
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.mocg.json"), reverse=True)[:20]:
        try:
            pkg = json.loads(f.read_text(encoding="utf-8"))
            sr = pkg.get("shape_report", {})
            out.append({"id": f.stem, "created": pkg.get("created_utc"),
                        "ratio": sr.get("compression", {}).get("ratio"),
                        "comprimido": True})
        except Exception:
            continue
    return out


def ejecutar_flujo_dominio(domain_id: str, archivos: List[dict], modo: str = "ASESORIA",
                           calibrar: bool = False) -> dict:
    """Flujo por dominio (los 6 empresariales o el demo): cada uno con su doble hélice."""
    es_demo = domain_id == "dom_fermentacion_lotes_v1"
    mapa = cargar_mapa_dominio(domain_id)
    cucurucho = cargar_cucurucho()

    dominio = {"domain_id": domain_id, "descriptor": _descriptor_dominio(domain_id),
               "es_demo": es_demo, "umbrales_operativos": UMBRALES_STD}

    senales, rangos = extraer_senales(archivos, mapa)
    kpis, calib = preparar_kpis(senales, mapa, rangos, calibrar)
    discretos = detalle_discreto(senales, mapa)
    control = control_features(kpis, dominio, {})
    resultado_lazo = lazo_asesoria(kpis, DOMINIO_CVD) if modo == "ASESORIA" \
        else lazo_agencia(kpis, DOMINIO_CVD)

    memoria = guardar_memoria(domain_id, {
        "domain_id": domain_id, "descriptor": dominio["descriptor"],
        "kpis": kpis, "control": control, "senales": senales,
        "estado": resultado_lazo["estado_general"],
        "trayectoria": resultado_lazo["geodesica_sugerida"]["nombre"],
    })

    # Embudo único: la MISMA ingesta prepara EN PARALELO las coordenadas del Ágora.
    # No reemplaza nada; solo AÑADE lo que el Ágora necesita. Import perezoso (evita ciclo).
    agora = None
    try:
        from cucurucho_embudo import preparar_agora
        agora = preparar_agora(domain_id, archivos, guardar=True)
    except Exception:
        agora = None

    return {
        "cliente": {"client_id": domain_id, "client_name": dominio["descriptor"],
                    "active_subscription": True, "overrides": {}},
        "dominio": {"domain_id": domain_id, "descriptor": dominio["descriptor"],
                    "es_demo": es_demo, "polos": POLOS_STD},
        "cucurucho": {"id": cucurucho["id_config"], "agentes": agentes_activos(cucurucho)},
        "senales_operacion": senales,
        "kpis_holograficos": kpis,
        "metricas_discretas": discretos,
        "features_control": control,
        "calibracion": {"aplicada": calibrar, "rangos": calib},
        "memoria": memoria,
        "historial": listar_memoria(domain_id),
        "lazo": resultado_lazo,
        "agora": agora,
    }


def ejecutar_flujo(client_id: str, archivos: List[dict], modo: str = "ASESORIA") -> dict:
    """Flujo completo por CLIENTE: cliente → dominio → cucurucho → lazo."""
    cliente = cargar_cliente(client_id)
    if not cliente.get("active_subscription"):
        raise PermissionError("La suscripción del cliente no está activa.")

    dominio = cargar_dominio(cliente["domain_ref"])
    params = cargar_params(dominio.get("params_ref", "palenque_fermentacion_params"))
    cucurucho = cargar_cucurucho()

    senales, _rangos = extraer_senales(archivos, params)
    kpis, _calib = preparar_kpis(senales, params)            # entrada LIMPIA para el lazo
    discretos = detalle_discreto(senales, params)            # armonía discreto ↔ geométrico
    control = control_features(kpis, dominio, cliente.get("overrides", {}))

    resultado_lazo = lazo_asesoria(kpis, DOMINIO_CVD) if modo == "ASESORIA" \
        else lazo_agencia(kpis, DOMINIO_CVD)

    return {
        "cliente": {"client_id": cliente["client_id"], "client_name": cliente["client_name"],
                    "active_subscription": cliente["active_subscription"],
                    "overrides": cliente.get("overrides", {})},
        "dominio": {"domain_id": dominio["domain_id"], "descriptor": dominio["descriptor"],
                    "es_demo": dominio.get("es_demo", False),
                    "polos": dominio["grafo_meso"]["nombres_polos"]},
        "cucurucho": {"id": cucurucho["id_config"], "agentes": agentes_activos(cucurucho)},
        "senales_operacion": senales,
        "kpis_holograficos": kpis,          # <-- lo que recibe la observación (métricas)
        "metricas_discretas": discretos,    # <-- datos tradicionales por métrica
        "features_control": control,
        "lazo": resultado_lazo,
    }
