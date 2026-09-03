"""
Elemento de Ciberseguridad — Herramienta C: GSL Capa Administrativa.

Puerto fiel del notebook `gsl_capa_administrativa.ipynb` (Python stdlib + numpy).
Manifold de INTENCIONES declaradas (no efectos): cada acción admin con autor,
timestamp y objeto. Fuentes: Active Directory, Azure AD, Linux auditd, IAM genérico.
Diferenciador: AUTOPROTECCIÓN del GSL (detecta ataques al propio sistema).
Emite `admin_anomaly` al PolicyAdapter del Modo 2. 100% local.
"""

import json
import csv
import io
import random
import time
import uuid
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

import numpy as np

from ciber_modo1 import cargar_config as _cargar_dom
from compresion_geometrica import comprimir as _comprimir_codec

BASE = Path(__file__).resolve().parent
FORENSE_DIR = BASE / "flujo" / "ciber_admin"

EVENT_TAXONOMY = {
    'user_created': {'cat': 'account', 'impact': 'medium', 'gsl': False},
    'user_deleted': {'cat': 'account', 'impact': 'high', 'gsl': False},
    'user_enabled': {'cat': 'account', 'impact': 'medium', 'gsl': False},
    'password_reset': {'cat': 'account', 'impact': 'medium', 'gsl': False},
    'mfa_disabled': {'cat': 'account', 'impact': 'high', 'gsl': False},
    'permission_granted': {'cat': 'permission', 'impact': 'high', 'gsl': True},
    'role_assigned': {'cat': 'permission', 'impact': 'high', 'gsl': False},
    'admin_role_granted': {'cat': 'permission', 'impact': 'critical', 'gsl': True},
    'group_member_added': {'cat': 'group', 'impact': 'medium', 'gsl': False},
    'policy_modified': {'cat': 'policy', 'impact': 'high', 'gsl': True},
    'policy_deleted': {'cat': 'policy', 'impact': 'critical', 'gsl': True},
    'audit_log_cleared': {'cat': 'policy', 'impact': 'critical', 'gsl': True},
    'audit_policy_disabled': {'cat': 'policy', 'impact': 'critical', 'gsl': True},
    'sudo_session_start': {'cat': 'session', 'impact': 'high', 'gsl': True},
    'sudo_session_end': {'cat': 'session', 'impact': 'low', 'gsl': False},
    'acl_modified': {'cat': 'resource', 'impact': 'high', 'gsl': True},
    'resource_shared': {'cat': 'resource', 'impact': 'medium', 'gsl': False},
    'firewall_rule_deleted': {'cat': 'resource', 'impact': 'critical', 'gsl': True},
}
IMPACT_WEIGHTS = {'low': 0.1, 'medium': 0.3, 'high': 0.6, 'critical': 1.0}
LOGICAL_SEQUENCE = {
    'permission_granted': ['user_created', 'user_enabled'],
    'admin_role_granted': ['role_assigned', 'permission_granted'],
    'acl_modified': ['permission_granted', 'resource_shared'],
    'sudo_session_start': ['user_enabled', 'role_assigned'],
}
NORMAL_WINDOWS = {
    'account': (8, 18), 'permission': (9, 17), 'policy': (10, 16),
    'session': (0, 23), 'group': (8, 18), 'resource': (9, 17),
}
GSL_PROTEGIDOS = ['gsl_service_account', 'gsl_policy', 'gsl_audit_log',
                  'gsl_config', 'resistor_rules', 'manifold_store']
THRESHOLDS = {'dissonance_alert': 0.28, 'dissonance_critical': 0.55,
              'off_hours_weight': 2.5, 'sequence_violation_w': 3.0, 'gsl_self_attack_w': 5.0}
AD_MAP = {'4720': 'user_created', '4722': 'user_enabled', '4723': 'password_reset',
          '4728': 'group_member_added', '4732': 'group_member_added',
          '4670': 'permission_granted', '4907': 'acl_modified',
          '4719': 'audit_policy_disabled', '1102': 'audit_log_cleared',
          '4672': 'admin_role_granted'}


def _admin_config(domain_id: str) -> dict:
    dom = _cargar_dom(domain_id)
    admins = []
    for u in dom.get("users", []):
        admins.append({"id": u["id"], "name": u["name"], "role": u.get("role", "admin"),
                       "typical_hours": u.get("typical_hours", [9, 18]),
                       "manages": ["account", "permission", "policy", "resource"]})
    return {"org_name": dom.get("org_name"), "bimester": dom.get("bimester"),
            "admins": admins, "gsl_protected_resources": GSL_PROTEGIDOS,
            "thresholds": THRESHOLDS}


def _parse_ts(raw: Any) -> Optional[float]:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _mk(etype, actor, ts, obj, obj_type, ip="192.168.1.10", success=True, role="admin"):
    tax = EVENT_TAXONOMY.get(etype, {})
    return {"event_id": str(uuid.uuid4())[:8], "timestamp": ts, "actor_id": actor,
            "actor_role": role, "event_type": etype, "category": tax.get("cat", "unknown"),
            "object_id": obj, "object_type": obj_type, "impact": tax.get("impact", "low"),
            "source_ip": ip, "success": success}


# ─── Parsers IAM (esquema mínimo común) ──────────────────────────────────────
def parse_admin(data: Any, platform: str = "generic", cfg: dict = None) -> List[dict]:
    gsl = set((cfg or {}).get("gsl_protected_resources", GSL_PROTEGIDOS))
    rows = data if isinstance(data, list) else [data]
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if platform == "ad":
            code = str(r.get("EventID", r.get("event_id", "")))
            etype = AD_MAP.get(code)
            if not etype:
                continue
            obj = r.get("TargetUserName", r.get("ObjectName", "unknown"))
            ts = _parse_ts(r.get("TimeCreated", r.get("timestamp"))) or time.time()
            actor = r.get("SubjectUserName", r.get("actor", "unknown"))
            ip = r.get("IpAddress", "0.0.0.0")
        else:  # azure_ad / auditd / generic → intentar campos comunes
            etype_raw = str(r.get("event_type", r.get("action", r.get("operationName", "")))).lower()
            etype = next((k for k in EVENT_TAXONOMY if k in etype_raw), "permission_granted")
            obj = str(r.get("object", r.get("target", r.get("object_id", "unknown"))))
            ts = _parse_ts(r.get("timestamp", r.get("time", r.get("activityDateTime")))) or time.time()
            actor = str(r.get("actor", r.get("user", r.get("account", "unknown"))))
            ip = str(r.get("ip", r.get("source_ip", "0.0.0.0")))
        obj_type = "gsl" if obj in gsl else "user"
        suc = str(r.get("success", r.get("result", "true"))).lower() in ("true", "success", "1", "yes")
        out.append(_mk(etype, actor, ts, obj, obj_type, ip, suc,
                       role=str(r.get("role", "admin"))))
    return out


def _bytes_admin(datos: bytes) -> List[dict]:
    try:
        texto = datos.decode("utf-8")
    except Exception:
        return []
    try:
        return parse_admin(json.loads(texto))
    except Exception:
        pass
    try:
        rows = list(csv.DictReader(io.StringIO(texto)))
        if rows:
            return parse_admin(rows)
    except Exception:
        pass
    return []


# ─── Generador sintético (escenario mixed) ───────────────────────────────────
def generar_admin(cfg: dict, seed: int = 42, n: int = 150) -> List[dict]:
    rng = random.Random(seed)
    admins = cfg["admins"]
    gsl = cfg["gsl_protected_resources"]
    base = datetime(2025, 1, 20, 9, 0, 0, tzinfo=timezone.utc)
    normal = [('user_created',), ('user_enabled',), ('password_reset',),
              ('group_member_added',), ('permission_granted',), ('role_assigned',),
              ('policy_modified',), ('sudo_session_start',), ('sudo_session_end',),
              ('resource_shared',)]
    ev = []
    for _ in range(n // 2):
        (etype,) = rng.choice(normal)
        adm = rng.choice(admins)
        h0, h1 = adm["typical_hours"]
        ts = (base.replace(hour=rng.randint(h0, h1), minute=rng.randint(0, 59))
              + timedelta(days=rng.randint(0, 59))).timestamp()
        ev.append(_mk(etype, adm["id"], ts, f"obj_{rng.randint(1,20):03d}", "user",
                      role=adm.get("role", "admin")))
    atk = (base.replace(hour=3) + timedelta(days=30)).timestamp()
    a0 = admins[0]["id"]
    # Escalada con secuencia invertida
    ev.append(_mk("admin_role_granted", a0, atk, "compromised_user", "user", "203.45.67.89"))
    ev.append(_mk("permission_granted", a0, atk + 120, "compromised_user", "user", "203.45.67.89"))
    ev.append(_mk("user_created", a0, atk + 300, "compromised_user", "user", "203.45.67.89"))
    # Cambios críticos fuera de horario
    ev.append(_mk("policy_deleted", a0, atk + 600, "obj_critica", "policy", "203.45.67.89"))
    # Auto-ataque al GSL
    for i, res in enumerate(gsl[:3]):
        ev.append(_mk("audit_log_cleared" if i == 0 else "acl_modified", a0,
                      atk + 900 + i * 60, res, "gsl", "203.45.67.89"))
    return ev


# ─── Motor de manifold administrativo (8D) ───────────────────────────────────
def _grafo_permisos(events: List[dict]) -> Dict[str, Dict[str, float]]:
    G: Dict[str, Dict[str, float]] = {}
    for e in events:
        if e["event_type"] in ("permission_granted", "admin_role_granted", "role_assigned", "acl_modified"):
            w = IMPACT_WEIGHTS.get(e["impact"], 0.1)
            G.setdefault(e["actor_id"], {})
            G[e["actor_id"]][e["object_id"]] = G[e["actor_id"]].get(e["object_id"], 0.0) + w
    return G


def firma_admin(events: List[dict], actor: str, cfg: dict, grafo=None) -> np.ndarray:
    ae = [e for e in events if e["actor_id"] == actor]
    if len(ae) < 2:
        return np.full(8, 0.1)
    adm = next((a for a in cfg["admins"] if a["id"] == actor), None)
    off = 0
    for e in ae:
        h = datetime.fromtimestamp(e["timestamp"], tz=timezone.utc).hour
        lo, hi = NORMAL_WINDOWS.get(e["category"], (8, 18))
        if not (lo <= h <= hi):
            off += 1
        if adm and not (adm["typical_hours"][0] <= h <= adm["typical_hours"][1]):
            off += 0.5
    off_r = off / max(len(ae), 1)
    crit = sum(1 for e in ae if e["impact"] in ("critical", "high")) / len(ae)
    seen = set(); viol = 0
    for e in sorted(ae, key=lambda x: x["timestamp"]):
        pre = LOGICAL_SEQUENCE.get(e["event_type"], [])
        if pre and not any(p in seen for p in pre):
            viol += 1
        seen.add(e["event_type"])
    seq = min(viol / max(len(ae), 1), 1.0)
    priv = 0.0
    objs = set(e["object_id"] for e in ae)
    obj_div = min(len(objs) / 20.0, 1.0)
    gsl = set(cfg["gsl_protected_resources"])
    gsl_r = sum(1 for e in ae if e["object_id"] in gsl or e["object_type"] == "gsl") / max(len(ae), 1)
    fail = sum(1 for e in ae if not e["success"]) / max(len(ae), 1)
    cent = 0.0
    if grafo is not None:
        nodes = set(grafo.keys()) | {o for v in grafo.values() for o in v}
        deg = len(grafo.get(actor, {}))
        cent = deg / max(len(nodes), 1)
    return np.clip(np.array([off_r, crit, seq, priv, obj_div, gsl_r, fail, cent]), 0, 1)


def disonancia_admin(cur, base, cfg, events, actor) -> Tuple[float, List[str]]:
    th = cfg["thresholds"]; gsl = set(cfg["gsl_protected_resources"])
    w = np.array([0.20, 0.15, 0.20, 0.10, 0.08, 0.15, 0.07, 0.05]); w /= w.sum()
    dis = float(np.dot(np.abs(cur - base), w)); reasons = []
    ae = [e for e in events if e["actor_id"] == actor]
    off = sum(1 for e in ae if not (NORMAL_WINDOWS.get(e["category"], (8, 18))[0]
              <= datetime.fromtimestamp(e["timestamp"], tz=timezone.utc).hour
              <= NORMAL_WINDOWS.get(e["category"], (8, 18))[1]))
    if off > 0:
        dis *= (1 + 0.3 * th["off_hours_weight"] * off / max(len(ae), 1))
        reasons.append(f"{off} eventos fuera de ventana horaria")
    if cur[2] > base[2] * 2:
        dis *= (1 + 0.2 * th["sequence_violation_w"])
        reasons.append("Secuencia lógica de permisos violada")
    gsl_ev = [e for e in ae if e["object_id"] in gsl or e["object_type"] == "gsl"]
    if gsl_ev:
        dis *= (1 + th["gsl_self_attack_w"] * len(gsl_ev) / max(len(ae), 1))
        reasons.append(f"⚠️ {len(gsl_ev)} eventos sobre recursos GSL protegidos")
    return float(np.clip(dis, 0, 1)), reasons


def _hash(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def ejecutar_admin(domain_id: str, fuente: str = "embudo",
                   archivos: Optional[List[dict]] = None, payload: Any = None,
                   platform: str = "generic", seed: int = 42) -> dict:
    if domain_id not in _cargar_dom.__globals__.get("DOMINIOS_EMPRESARIALES", []) \
            and domain_id not in ["dom_restaurante_v1", "dom_retail_v1", "dom_hotel_v1",
                                  "dom_fabrica_v1", "dom_logistica_v1", "dom_clinica_v1"]:
        raise ValueError(f"Capa administrativa aplica solo a las 6 empresas: {domain_id}")
    cfg = _admin_config(domain_id)
    th = cfg["thresholds"]

    if fuente == "api_webhook" and payload is not None:
        events = parse_admin(payload, platform, cfg); origen = "API / webhook (IAM)"
    elif fuente == "embudo" and archivos:
        events = []
        for a in archivos:
            events.extend(_bytes_admin(a["datos"]))
        origen = f"Embudo — {len(archivos)} archivo(s)"
    else:
        events = generar_admin(cfg, seed); origen = "Operación sintética demo (escenario mixed)"

    events = [e for e in events if e.get("timestamp")]
    if not events:
        return {"domain_id": domain_id, "origen": origen, "records": [], "stats": {},
                "grafo": [], "reporte": "Sin eventos administrativos."}

    grafo = _grafo_permisos(events)
    actors = list(set(e["actor_id"] for e in events))
    es = sorted(events, key=lambda e: e["timestamp"])
    base_ev = es[:max(len(es) // 2, 10)]
    baselines = {a: firma_admin(base_ev, a, cfg, grafo) for a in actors}

    records = []
    ts_min, ts_max = es[0]["timestamp"], es[-1]["timestamp"]
    win_s = 7 * 86400
    cur = ts_min + win_s
    while cur <= ts_max + win_s:
        wev = [e for e in es if cur - win_s <= e["timestamp"] <= cur]
        if not wev:
            cur += win_s / 4; continue
        for actor in actors:
            ae = [e for e in wev if e["actor_id"] == actor]
            if len(ae) < 2:
                continue
            vec = firma_admin(wev, actor, cfg, grafo)
            base = baselines.get(actor, np.full(8, 0.1))
            dis, reasons = disonancia_admin(vec, base, cfg, wev, actor)
            if dis < th["dissonance_alert"]:
                baselines[actor] = 0.95 * base + 0.05 * vec
                continue
            trig = max(ae, key=lambda e: IMPACT_WEIGHTS.get(e["impact"], 0))
            gsl = set(cfg["gsl_protected_resources"])
            gsl_attack = (trig["object_id"] in gsl or trig["object_type"] == "gsl"
                          or any(e["object_id"] in gsl for e in ae))
            action = ("alert_gsl_self_attack" if gsl_attack
                      else "report_admin_critical" if dis >= th["dissonance_critical"]
                      else "report_admin_anomaly")
            rec = {
                "record_id": f"AR-{str(uuid.uuid4())[:8].upper()}",
                "timestamp": datetime.fromtimestamp(trig["timestamp"], tz=timezone.utc).isoformat(),
                "actor_id": actor, "actor_role": next((a["role"] for a in cfg["admins"] if a["id"] == actor), "unknown"),
                "dissonance": round(dis, 4), "reasons": reasons,
                "dims": {"off_hours": round(float(vec[0]), 3), "critical": round(float(vec[1]), 3),
                         "seq_viol": round(float(vec[2]), 3), "priv_dur": round(float(vec[3]), 3),
                         "obj_divers": round(float(vec[4]), 3), "gsl_touch": round(float(vec[5]), 3),
                         "fail_rate": round(float(vec[6]), 3), "centrality": round(float(vec[7]), 3)},
                "trigger_event": trig["event_type"], "trigger_object": trig["object_id"],
                "gsl_self_attack": gsl_attack, "action": action,
                "override_token": str(uuid.uuid4())[:12],
            }
            rec["sha256"] = _hash({"record_id": rec["record_id"], "actor_id": actor,
                                   "dissonance": round(dis, 4), "gsl_attack": gsl_attack})
            records.append(rec)
        cur += win_s / 4

    gsl_atk = sum(1 for r in records if r["gsl_self_attack"])
    critical = sum(1 for r in records if r["dissonance"] >= th["dissonance_critical"])
    grafo_edges = [{"actor": a, "object": o, "weight": round(w, 3)}
                   for a, objs in grafo.items() for o, w in objs.items()]
    reporte = _reporte(cfg, records, len(events), critical, gsl_atk)
    _persistir(domain_id, records)

    return {
        "domain_id": domain_id, "org_name": cfg["org_name"], "origen": origen,
        "stats": {"total_events": len(events), "forensic_recs": len(records),
                  "critical": critical, "gsl_attacks": gsl_atk, "actors": actors},
        "records": sorted(records, key=lambda r: r["dissonance"], reverse=True),
        "grafo": grafo_edges, "reporte": reporte,
    }


def _reporte(cfg, records, n_ev, critical, gsl_atk) -> str:
    L = [f"## Capa Administrativa — {cfg['org_name']}",
         f"**Bimestre:** {cfg.get('bimester','')}",
         "",
         f"- Eventos procesados: **{n_ev}**",
         f"- Registros forenses: **{len(records)}**  ·  críticos: **{critical}**",
         f"- 🔑 Auto-ataques al GSL detectados: **{gsl_atk}**", ""]
    if gsl_atk:
        L.append("> ⚠️ Se detectaron intentos contra el propio sistema de detección (recursos GSL).")
    for r in sorted(records, key=lambda x: x["dissonance"], reverse=True)[:5]:
        marca = "🔴" if r["gsl_self_attack"] else "🟠"
        L.append(f"- {marca} `{r['actor_id']}` — {r['trigger_event']} sobre `{r['trigger_object']}` (dis {r['dissonance']})")
    return "\n".join(L)


def _persistir(domain_id: str, records: List[dict]):
    FORENSE_DIR.mkdir(parents=True, exist_ok=True)
    (FORENSE_DIR / f"{domain_id}.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def leer_forense(domain_id: str) -> List[dict]:
    p = FORENSE_DIR / f"{domain_id}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))
