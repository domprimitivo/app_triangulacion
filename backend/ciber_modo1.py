"""
Elemento de Ciberseguridad — Herramienta A: GSL Modo 1 (Observación Pasiva).

Puerto fiel y compacto del notebook `gsl_modo1_pasivo.ipynb`.
100% local, soberano. Python stdlib + numpy. Sin pandas / plotly / gradio.

Solo OBSERVA: construye el manifold geométrico de "lo normal" por extremo
(usuario o entidad SIEM), produce un score de disonancia continuo por ventana
temporal y un reporte bimestral. No bloquea, no alerta, no interviene.

Aplica SOLO a los 6 dominios empresariales (comparten el Aprendiz de logística).

Ingesta dual:
  - fuente="embudo"     : usa los archivos subidos (cucurucho). Sin archivos →
                          operación sintética demo de la config del dominio.
  - fuente="api_webhook": procesa un payload SIEM entregado inline (JSON/CSV/CEF).
"""

import json
import csv
import io
import math
import random
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

import numpy as np

from compresion_geometrica import comprimir as _comprimir_codec

BASE = Path(__file__).resolve().parent
CIBER_DIR = BASE / "flujo" / "ciber"
MEMORIA_DIR = BASE / "flujo" / "ciber_memoria"

DOMINIOS_EMPRESARIALES = ["dom_restaurante_v1", "dom_retail_v1", "dom_hotel_v1",
                          "dom_fabrica_v1", "dom_logistica_v1", "dom_clinica_v1"]

WINDOW_HOURS = 2
DIS_WEIGHTS = np.array([0.25, 0.20, 0.10, 0.15, 0.08, 0.10, 0.07, 0.05])
DIS_WEIGHTS = DIS_WEIGHTS / DIS_WEIGHTS.sum()


# ─── Config por dominio (un JSON por dominio) ────────────────────────────────
def cargar_config(domain_id: str) -> dict:
    p = CIBER_DIR / f"{domain_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Config de ciberseguridad no encontrada: {domain_id}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── Utilidades de tiempo ────────────────────────────────────────────────────
def _parse_ts(raw: Any) -> Optional[float]:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%b/%Y:%H:%M:%S %z"):
        try:
            if fmt is None:
                return datetime.fromisoformat(s).timestamp()
            return datetime.strptime(raw.strip(), fmt).timestamp()
        except Exception:
            continue
    return None


def _hour(ts: float) -> int:
    return datetime.fromtimestamp(ts, tz=timezone.utc).hour


# ─── Parsers SIEM (mismo esquema mínimo común del notebook) ──────────────────
def detectar_formato(data: Any) -> str:
    if isinstance(data, str):
        st = data.strip()
        if st.startswith("CEF:"):
            return "cef_generic"
        try:
            return detectar_formato(json.loads(st))
        except Exception:
            return "csv_generic"
    if isinstance(data, dict):
        k = set(data.keys())
        if "metadata" in k and "principal" in k:
            return "chronicle_udm"
        if "TimeGenerated" in k or "OperationName" in k:
            return "sentinel_json"
        if "result" in k or "_time" in k:
            return "splunk_json"
        return "csv_generic"
    if isinstance(data, list) and data:
        return detectar_formato(data[0])
    return "unknown"


def _row(ts, src, tgt, etype, sev, rule, outcome, plat):
    return {"timestamp": ts, "source_entity": str(src), "target_entity": str(tgt),
            "event_type": str(etype), "severity": str(sev), "rule_id": str(rule),
            "outcome": str(outcome), "raw_platform": plat}


def parse_chronicle(events: list) -> List[dict]:
    out = []
    for e in events:
        meta = e.get("metadata", {}); prin = e.get("principal", {})
        tgt = e.get("target", {}); sec = e.get("security_result", [{}])
        sec = sec[0] if isinstance(sec, list) and sec else (sec if isinstance(sec, dict) else {})
        act = sec.get("action", ["UNKNOWN"])
        out.append(_row(meta.get("eventTimestamp", ""),
                        prin.get("user", {}).get("userid", prin.get("ip", "unknown")),
                        tgt.get("asset", {}).get("assetId", tgt.get("url", "unknown")),
                        meta.get("eventType", "UNKNOWN"), sec.get("severity", "UNKNOWN"),
                        sec.get("ruleName", ""), act[0] if isinstance(act, list) and act else "UNKNOWN",
                        "chronicle_udm"))
    return out


def parse_splunk(events: list) -> List[dict]:
    out = []
    for e in events:
        r = e.get("result", e)
        out.append(_row(r.get("_time", r.get("timestamp", "")),
                        r.get("user", r.get("src", "unknown")),
                        r.get("dest", r.get("host", "unknown")),
                        r.get("EventCode", r.get("sourcetype", "UNKNOWN")),
                        r.get("severity", "UNKNOWN"), r.get("rule_name", ""),
                        r.get("action", r.get("status", "UNKNOWN")), "splunk_json"))
    return out


def parse_sentinel(events: list) -> List[dict]:
    out = []
    for e in events:
        out.append(_row(e.get("TimeGenerated", ""),
                        e.get("Account", e.get("CallerIpAddress", "unknown")),
                        e.get("ResourceId", e.get("OperationName", "unknown")),
                        e.get("OperationName", e.get("Category", "UNKNOWN")),
                        e.get("Level", "UNKNOWN"), e.get("CorrelationId", ""),
                        e.get("ResultType", "UNKNOWN"), "sentinel_json"))
    return out


def parse_cef(raw: str) -> List[dict]:
    out = []
    for line in raw.strip().split("\n"):
        if not line.startswith("CEF:"):
            continue
        parts = line.split("|")
        if len(parts) < 8:
            continue
        ext = {}
        for kv in parts[7].split():
            if "=" in kv:
                a, b = kv.split("=", 1)
                ext[a] = b
        out.append(_row(ext.get("rt", ext.get("start", "")),
                        ext.get("suser", ext.get("src", "unknown")),
                        ext.get("dhost", ext.get("dst", "unknown")),
                        parts[5] if len(parts) > 5 else "UNKNOWN",
                        parts[6] if len(parts) > 6 else "UNKNOWN",
                        parts[4] if len(parts) > 4 else "", ext.get("act", "UNKNOWN"),
                        "cef_generic"))
    return out


def parse_csv_generic(rows: List[dict]) -> List[dict]:
    cmap = {
        "timestamp": ["timestamp", "time", "datetime", "date", "_time", "timegenerated"],
        "source_entity": ["user", "username", "src_user", "account", "userid", "src"],
        "target_entity": ["target", "dest", "destination", "resource", "host", "asset"],
        "event_type": ["event_type", "eventtype", "action", "category", "operationname"],
        "severity": ["severity", "level", "priority", "urgency"],
        "rule_id": ["rule", "rule_name", "alert_name", "ruleid"],
        "outcome": ["outcome", "result", "status", "resulttype"],
    }
    out = []
    for row in rows:
        low = {str(k).lower(): v for k, v in row.items()}
        vals = {}
        for field, cands in cmap.items():
            vals[field] = "unknown"
            for c in cands:
                if c in low and str(low[c]).strip():
                    vals[field] = low[c]
                    break
        out.append(_row(vals["timestamp"], vals["source_entity"], vals["target_entity"],
                        vals["event_type"], vals["severity"], vals["rule_id"],
                        vals["outcome"], "csv_generic"))
    return out


def parse_siem(data: Any, fmt: Optional[str] = None) -> List[dict]:
    fmt = fmt or detectar_formato(data)
    if fmt == "chronicle_udm":
        return parse_chronicle(data if isinstance(data, list) else [data])
    if fmt == "splunk_json":
        return parse_splunk(data if isinstance(data, list) else [data])
    if fmt == "sentinel_json":
        return parse_sentinel(data if isinstance(data, list) else [data])
    if fmt == "cef_generic":
        return parse_cef(data if isinstance(data, str) else json.dumps(data))
    rows = data if isinstance(data, list) else [data]
    rows = [r for r in rows if isinstance(r, dict)]
    return parse_csv_generic(rows)


def _bytes_a_eventos(nombre: str, datos: bytes) -> List[dict]:
    """Parsea un archivo subido (embudo) al esquema SIEM mínimo común."""
    try:
        texto = datos.decode("utf-8")
    except Exception:
        return []
    st = texto.strip()
    if st.startswith("CEF:"):
        return parse_siem(texto, "cef_generic")
    try:
        return parse_siem(json.loads(st))
    except Exception:
        pass
    try:
        rows = list(csv.DictReader(io.StringIO(texto)))
        if rows:
            return parse_csv_generic(rows)
    except Exception:
        pass
    return []


# ─── Generador sintético (demo local cuando no hay archivos) ─────────────────
def generar_principal(cfg: dict, seed: int = 42, n: int = 300) -> List[dict]:
    rng = random.Random(seed)
    users = cfg["users"]; assets = cfg["assets"]
    actions = ["read", "write", "export", "login", "modify", "delete", "share"]
    aw = [40, 20, 10, 15, 8, 3, 4]
    base = datetime(2025, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    rows = []
    for _ in range(n):
        u = rng.choice(users); a = rng.choice(assets)
        act = rng.choices(actions, weights=aw, k=1)[0]
        h0, h1 = u["typical_hours"]
        hour = rng.randint(h0, h1) if rng.random() < 0.90 else rng.choice(
            [rng.randint(0, max(h0 - 1, 0)), rng.randint(min(h1 + 1, 23), 23)])
        ts = (base.replace(hour=hour, minute=rng.randint(0, 59))
              + timedelta(days=rng.randint(0, 59))).timestamp()
        ip = rng.choice(u["typical_ips"]) if rng.random() < 0.95 \
            else f"203.{rng.randint(1,254)}.{rng.randint(1,254)}.{rng.randint(1,254)}"
        rows.append({"timestamp": ts, "source_entity": u["id"], "target_entity": a["id"],
                     "event_type": act, "severity": "high" if a["sensitivity"] == "high" else "low",
                     "rule_id": "", "outcome": "success" if rng.random() > 0.05 else "failure",
                     "source_ip": ip, "session_id": f"SES-{u['id']}-{int(ts)%1000:03d}",
                     "sensitivity": a["sensitivity"], "raw_platform": "principal"})
    return rows


def generar_siem_mock(platform: str, cfg: dict, seed: int = 7, n: int = 150) -> List[dict]:
    rng = random.Random(seed)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    etypes = ["USER_LOGIN", "FILE_OPEN", "FILE_COPY", "NETWORK_CONNECTION",
              "PROCESS_LAUNCH", "USER_LOGOUT", "PERMISSION_CHANGE"]
    sev = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]; sw = [50, 30, 15, 5]
    users = [u["id"] for u in cfg["users"]]
    rows = []
    for _ in range(n):
        ts = (base + timedelta(days=rng.randint(0, 59), hours=rng.randint(0, 23),
                               minutes=rng.randint(0, 59))).timestamp()
        rows.append({"timestamp": ts, "source_entity": rng.choice(users),
                     "target_entity": f"srv-{rng.randint(1,10):02d}",
                     "event_type": rng.choice(etypes),
                     "severity": rng.choices(sev, weights=sw, k=1)[0],
                     "rule_id": f"RULE-{rng.randint(100,999)}",
                     "outcome": rng.choice(["ALLOW", "BLOCK", "UNKNOWN"]),
                     "raw_platform": platform})
    return rows


# ─── Manifold de firma (8D) sobre lista de eventos-dict ──────────────────────
def _norm_events(events: List[dict]) -> List[dict]:
    out = []
    for e in events:
        ts = _parse_ts(e.get("timestamp"))
        if ts is None:
            continue
        e = dict(e); e["ts"] = ts; e["hour"] = _hour(ts)
        out.append(e)
    return out


def firma_vector(subset: List[dict], entity_id: str, cfg: dict) -> np.ndarray:
    if len(subset) < 3:
        return np.full(8, 0.5)
    n = len(subset)

    # [0] ip_consistency
    ucfg = next((u for u in cfg.get("users", []) if u["id"] == entity_id), None)
    ips = [str(e.get("source_ip", "")) for e in subset if e.get("source_ip")]
    if ucfg and ips:
        known = set(ucfg.get("typical_ips", []))
        ip_cons = (sum(1 for i in ips if i in known) / len(ips)) if known else 0.5
    elif ips:
        ip_cons = 1 - (len(set(ips)) / max(len(ips), 1))
    else:
        ip_cons = 0.5

    # [1] hour_centrality
    hours = [e["hour"] for e in subset]
    hour_cent = 1 - min(float(np.std(hours)) / 12.0, 1.0) if len(hours) > 1 else 0.5

    # [2] action_entropy
    acts = [str(e.get("event_type", "")) for e in subset]
    counts = {}
    for a in acts:
        counts[a] = counts.get(a, 0) + 1
    probs = np.array([c / n for c in counts.values()])
    ent = float(-np.sum(probs * np.log2(probs + 1e-10)))
    act_ent = ent / math.log2(max(len(counts), 2))

    # [3] sensitivity_bias
    if any("sensitivity" in e for e in subset):
        sens_bias = sum(1 for e in subset if e.get("sensitivity") == "high") / n
    else:
        sens_bias = sum(1 for e in subset
                        if str(e.get("severity", "")).lower() in ("high", "critical")) / n

    # [4] session_regularity
    if any("session_id" in e for e in subset):
        sc = {}
        for e in subset:
            s = e.get("session_id", "")
            sc[s] = sc.get(s, 0) + 1
        v = np.array(list(sc.values()), dtype=float)
        sess_reg = 1 - min(float(np.std(v)) / max(float(np.mean(v)), 1), 1.0)
    else:
        sess_reg = 0.5

    # [5] failure_rate
    fails = sum(1 for e in subset if str(e.get("outcome", "")).lower()
                in ("failure", "blocked", "block", "deny", "drop", "unknown", "timeout"))
    fail_rate = fails / n

    # [6] event_velocity
    tss = sorted(e["ts"] for e in subset)
    span_h = max((tss[-1] - tss[0]) / 3600, 1)
    ev_vel = min((n / span_h) / 50.0, 1.0)

    # [7] cross_asset_spread
    targets = set(str(e.get("target_entity", "")) for e in subset)
    spread = len(targets) / max(len(cfg.get("assets", [1])), 1)

    vec = np.array([ip_cons, hour_cent, act_ent, sens_bias, sess_reg,
                    fail_rate, ev_vel, min(spread, 1.0)])
    return np.clip(vec, 0, 1)


def construir_manifold(events: List[dict], cfg: dict) -> dict:
    ent = {}
    for e in events:
        ent.setdefault(str(e["source_entity"]), []).append(e)
    manifold = {}
    for eid, evs in ent.items():
        manifold[eid] = {"vector": firma_vector(evs, eid, cfg), "n_events": len(evs)}
    return manifold


def disonancia(cur: np.ndarray, base: np.ndarray) -> float:
    return float(np.dot(np.abs(cur - base), DIS_WEIGHTS))


def score_entidad(events: List[dict], eid: str, manifold: dict, cfg: dict) -> List[dict]:
    if eid not in manifold:
        return []
    base = manifold[eid]["vector"]
    subset = sorted([e for e in events if str(e["source_entity"]) == eid], key=lambda e: e["ts"])
    if len(subset) < 2:
        return []
    tmin, tmax = subset[0]["ts"], subset[-1]["ts"]
    win = WINDOW_HOURS * 3600
    res = []
    cur = tmin
    while cur < tmax:
        end = cur + win
        w = [e for e in subset if cur <= e["ts"] < end]
        if len(w) >= 2:
            dv = firma_vector(w, eid, cfg)
            res.append({"entity_id": eid,
                        "window_start": datetime.fromtimestamp(cur, tz=timezone.utc).isoformat(),
                        "n_events": len(w), "dissonance": round(disonancia(dv, base), 4)})
        cur = end
    return res


def score_todos(events: List[dict], manifold: dict, cfg: dict, label: str) -> List[dict]:
    out = []
    for eid in manifold:
        for s in score_entidad(events, eid, manifold, cfg):
            s["source"] = label
            out.append(s)
    return out


# ─── Reporte bimestral (texto) ───────────────────────────────────────────────
def reporte_bimestral(scores: List[dict], cfg: dict, th_alert: float, th_report: float) -> str:
    if not scores:
        return "## Reporte bimestral\n\nSin ventanas temporales con datos suficientes."
    dis = [s["dissonance"] for s in scores]
    n_alert = sum(1 for d in dis if d >= th_alert)
    n_rep = sum(1 for d in dis if d >= th_report)
    por_ent = {}
    for s in scores:
        por_ent.setdefault(s["entity_id"], []).append(s["dissonance"])
    extremos = sorted(((e, max(v)) for e, v in por_ent.items()), key=lambda x: x[1], reverse=True)[:5]
    L = [f"## Reporte bimestral — {cfg.get('org_name','')}",
         f"**Bimestre:** {cfg.get('bimester','')}  ·  **Extremos observados:** {len(por_ent)}",
         "",
         f"- Ventanas temporales analizadas: **{len(scores)}**",
         f"- Disonancia media: **{np.mean(dis):.3f}**  ·  máxima: **{max(dis):.3f}**",
         f"- Ventanas ≥ {th_alert} (alerta): **{n_alert}**  ·  ≥ {th_report} (reporte): **{n_rep}**",
         "",
         "### Extremos con mayor disonancia"]
    for e, d in extremos:
        marca = "🔴" if d >= th_report else ("🟠" if d >= th_alert else "🟢")
        L.append(f"- {marca} `{e}` — disonancia máx **{d:.3f}**")
    L += ["", "> Modo 1 solo observa. No se ejecuta ninguna acción sobre los sistemas del cliente."]
    return "\n".join(L)


# ─── Memoria comprimida (códec MOCG) ─────────────────────────────────────────
def _guardar_memoria(domain_id: str, observacion: dict) -> dict:
    d = MEMORIA_DIR / domain_id
    d.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(observacion, ensure_ascii=False).encode("utf-8")
    pkg = _comprimir_codec([{"nombre": "modo1.json", "datos": payload}], org_id=domain_id)
    rid = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    (d / f"{rid}.mocg.json").write_text(json.dumps(pkg), encoding="utf-8")
    sr = pkg.get("shape_report", {}).get("compression", {})
    return {"id": rid, "created": pkg.get("created_utc"), "ratio": sr.get("ratio")}


def listar_memoria(domain_id: str) -> List[dict]:
    d = MEMORIA_DIR / domain_id
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.mocg.json"), reverse=True)[:20]:
        try:
            pkg = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": f.stem, "created": pkg.get("created_utc"),
                        "ratio": pkg.get("shape_report", {}).get("compression", {}).get("ratio"),
                        "comprimido": True})
        except Exception:
            continue
    return out


# ─── Orquestador principal ───────────────────────────────────────────────────
def ejecutar_modo1(domain_id: str, fuente: str = "embudo",
                   archivos: Optional[List[dict]] = None,
                   payload: Any = None, seed: int = 42) -> dict:
    if domain_id not in DOMINIOS_EMPRESARIALES:
        raise ValueError(f"Modo 1 aplica solo a las 6 empresas. Dominio inválido: {domain_id}")
    cfg = cargar_config(domain_id)
    th_alert = cfg["thresholds"]["geo_dissonance_alert"]
    th_report = cfg["thresholds"]["geo_dissonance_report"]

    streams = []           # {label, events}
    origen = ""
    if fuente == "api_webhook" and payload is not None:
        eventos = parse_siem(payload)
        streams.append({"label": "api_webhook", "events": _norm_events(eventos)})
        origen = "API / webhook (payload SIEM entregado)"
    elif fuente == "ingesta_live":
        from ciber_ingesta import leer_buffer
        raw = leer_buffer(domain_id)
        eventos = []
        for ev in raw:
            eventos.extend(parse_siem(ev))
        streams.append({"label": "ingesta_live", "events": _norm_events(eventos)})
        origen = f"Ingesta SIEM en vivo — {len(raw)} evento(s) del buffer del cliente"
    elif fuente == "embudo" and archivos:
        eventos = []
        for a in archivos:
            eventos.extend(_bytes_a_eventos(a["nombre"], a["datos"]))
        streams.append({"label": "embudo", "events": _norm_events(eventos)})
        origen = f"Embudo — {len(archivos)} archivo(s) del cucurucho"
    else:
        # Demo sintético local (principal + nodos SIEM configurados)
        streams.append({"label": "principal", "events": _norm_events(generar_principal(cfg, seed))})
        for node in cfg.get("nodes", []):
            plat = node.get("siem_platform", "chronicle")
            streams.append({"label": f"siem_{node.get('node_id','SIEM')}",
                            "events": _norm_events(generar_siem_mock(plat, cfg, seed))})
        origen = "Operación sintética demo (sin archivos)"

    all_scores = []
    manifiestos = {}
    for st in streams:
        evs = st["events"]
        if not evs:
            continue
        m = construir_manifold(evs, cfg)
        manifiestos[st["label"]] = {k: {"vector": [round(x, 4) for x in v["vector"].tolist()],
                                        "n_events": v["n_events"]} for k, v in m.items()}
        all_scores.extend(score_todos(evs, m, cfg, st["label"]))

    all_scores.sort(key=lambda s: s["window_start"])
    dis = [s["dissonance"] for s in all_scores]

    # Métricas
    metricas = {
        "disonancia_media": round(float(np.mean(dis)), 3) if dis else 0.0,
        "disonancia_max": round(float(max(dis)), 3) if dis else 0.0,
        "ventanas_total": len(all_scores),
        "ventanas_alerta": sum(1 for d in dis if d >= th_alert),
        "ventanas_reporte": sum(1 for d in dis if d >= th_report),
        "extremos_activos": len(set(s["entity_id"] for s in all_scores)),
    }

    # Tendencia (media de disonancia por ventana cronológica)
    tendencia = [{"window_start": s["window_start"], "dissonance": s["dissonance"],
                  "entity_id": s["entity_id"]} for s in all_scores]

    # Top 20 ventanas
    top = sorted(all_scores, key=lambda s: s["dissonance"], reverse=True)[:20]

    # Heatmap: por entidad, su serie de disonancias
    por_ent = {}
    for s in all_scores:
        por_ent.setdefault(s["entity_id"], []).append(s["dissonance"])
    heatmap = sorted(
        [{"entity_id": e, "dissonances": v, "mean": round(float(np.mean(v)), 3),
          "max": round(float(max(v)), 3)} for e, v in por_ent.items()],
        key=lambda x: x["max"], reverse=True)

    reporte = reporte_bimestral(all_scores, cfg, th_alert, th_report)

    memoria = _guardar_memoria(domain_id, {
        "domain_id": domain_id, "fuente": fuente, "metricas": metricas,
        "top_ventanas": top, "reporte": reporte})

    return {
        "domain_id": domain_id,
        "org_name": cfg.get("org_name"),
        "bimester": cfg.get("bimester"),
        "fuente": fuente,
        "origen": origen,
        "thresholds": {"alert": th_alert, "report": th_report},
        "metricas": metricas,
        "tendencia": tendencia,
        "top_ventanas": top,
        "heatmap": heatmap,
        "manifiestos": manifiestos,
        "reporte_bimestral": reporte,
        "memoria": memoria,
        "historial": listar_memoria(domain_id),
        "nodos_siem": [{"node_id": n.get("node_id"), "siem_platform": n.get("siem_platform"),
                        "deployment_level": n.get("deployment_level", 0)}
                       for n in cfg.get("nodes", [])],
    }


def info_config(domain_id: str) -> dict:
    cfg = cargar_config(domain_id)
    return {
        "domain_id": domain_id, "org_name": cfg.get("org_name"),
        "bimester": cfg.get("bimester"), "thresholds": cfg.get("thresholds"),
        "usuarios": len(cfg.get("users", [])), "activos": len(cfg.get("assets", [])),
        "nodos_siem": [{"node_id": n.get("node_id"), "siem_platform": n.get("siem_platform"),
                        "deployment_level": n.get("deployment_level", 0)}
                       for n in cfg.get("nodes", [])],
        "formatos_soportados": ["chronicle_udm", "splunk_json", "sentinel_json",
                                "cef_generic", "csv_generic"],
    }
