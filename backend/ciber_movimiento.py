"""
Elemento de Ciberseguridad — Herramienta D: MOCG Capa de Movimiento.

Puerto fiel del notebook `gsl_capa_movimiento.ipynb` (Python stdlib + numpy).
Manifold espaciotemporal con PRIVACIDAD por diseño:
  - Capa anónima: tokens HMAC-SHA256 (sal que rota bimestralmente).
  - Capa de identidad: resolución token→persona SOLO con autorización dual.
Detecta imposible travel, secuencia inversa, badge clonado, espacio anómalo,
rol roto. Emite `movement_anomaly` al Modo 2. 100% local.
"""

import json
import csv
import io
import hmac
import hashlib
import random
import heapq
import uuid
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

import numpy as np

from ciber_modo1 import cargar_config as _cargar_dom

BASE = Path(__file__).resolve().parent
FORENSE_DIR = BASE / "flujo" / "ciber_movimiento"
DOMS = ["dom_restaurante_v1", "dom_retail_v1", "dom_hotel_v1",
        "dom_fabrica_v1", "dom_logistica_v1", "dom_clinica_v1"]

SPACES = [
    {'id': 'entrada', 'name': 'Entrada', 'type': 'transit', 'capacity': 50, 'sensitivity': 'low'},
    {'id': 'lobby', 'name': 'Lobby', 'type': 'common', 'capacity': 30, 'sensitivity': 'low'},
    {'id': 'oficinas_a', 'name': 'Oficinas Ala A', 'type': 'office', 'capacity': 20, 'sensitivity': 'medium'},
    {'id': 'oficinas_b', 'name': 'Oficinas Ala B', 'type': 'office', 'capacity': 20, 'sensitivity': 'medium'},
    {'id': 'sala_reuniones', 'name': 'Sala reuniones', 'type': 'meeting', 'capacity': 12, 'sensitivity': 'medium'},
    {'id': 'servidores', 'name': 'Sala servidores', 'type': 'critical', 'capacity': 4, 'sensitivity': 'critical'},
    {'id': 'archivo', 'name': 'Archivo confidencial', 'type': 'restricted', 'capacity': 3, 'sensitivity': 'high'},
    {'id': 'salida', 'name': 'Salida', 'type': 'transit', 'capacity': 50, 'sensitivity': 'low'},
]
ADJ = [['entrada', 'lobby', 30], ['lobby', 'oficinas_a', 60], ['lobby', 'oficinas_b', 60],
       ['lobby', 'sala_reuniones', 90], ['oficinas_a', 'servidores', 120],
       ['oficinas_b', 'archivo', 90], ['sala_reuniones', 'servidores', 60],
       ['oficinas_a', 'salida', 120], ['oficinas_b', 'salida', 120], ['lobby', 'salida', 180]]
ROLE_PERMS = {
    'admin': ['entrada', 'lobby', 'oficinas_a', 'oficinas_b', 'sala_reuniones', 'servidores', 'archivo', 'salida'],
    'staff': ['entrada', 'lobby', 'oficinas_a', 'oficinas_b', 'sala_reuniones', 'salida'],
    'external': ['entrada', 'lobby', 'sala_reuniones', 'salida'],
    'it': ['entrada', 'lobby', 'oficinas_a', 'servidores', 'salida'],
    'legal': ['entrada', 'lobby', 'oficinas_b', 'archivo', 'salida'],
    'visitor': ['entrada', 'lobby', 'salida'],
}
BADGE_ROLES = {'B001': 'admin', 'B002': 'staff', 'B003': 'staff', 'B004': 'external',
               'B005': 'it', 'B006': 'legal', 'B007': 'visitor', 'B008': 'staff'}
THRESHOLDS = {'badge_dissonance_alert': 0.30, 'space_dissonance_alert': 0.35,
              'combined_dissonance_alert': 0.40, 'combined_dissonance_id': 0.65,
              'id_resolution_events': 3, 'impossible_travel_factor': 1.2,
              'space_occupancy_sigma': 2.5}

SPACE_MAP = {s['id']: s for s in SPACES}
_GRAPH = defaultdict(dict)
for a, b, t in ADJ:
    _GRAPH[a][b] = t
    _GRAPH[b][a] = t


def _config(domain_id: str) -> dict:
    dom = _cargar_dom(domain_id)
    return {"org_name": dom.get("org_name"), "bimester": dom.get("bimester", "2026-B1"),
            "token_salt": f"mocg-salt-{dom.get('bimester','2026-B1')}",
            "spaces": SPACES, "role_permissions": ROLE_PERMS, "badge_roles": BADGE_ROLES,
            "thresholds": THRESHOLDS}


def tokenize(badge_id: str, salt: str, length: int = 12) -> str:
    raw = hmac.new(salt.encode(), badge_id.encode(), hashlib.sha256).hexdigest()
    return f"TK-{raw[:length].upper()}"


def resolve_token(token: str, salt: str, registry: dict) -> Optional[str]:
    for badge_id in registry:
        if tokenize(badge_id, salt) == token:
            return badge_id
    return None


def _dijkstra(src: str, dst: str) -> float:
    if src == dst:
        return 0.0
    pq = [(0.0, src)]; seen = set()
    while pq:
        d, node = heapq.heappop(pq)
        if node == dst:
            return d
        if node in seen:
            continue
        seen.add(node)
        for nb, w in _GRAPH.get(node, {}).items():
            if nb not in seen:
                heapq.heappush(pq, (d + w, nb))
    return 300.0


def generar_eventos(cfg: dict, seed: int = 42, n_days: int = 20) -> List[dict]:
    rng = random.Random(seed)
    salt = cfg["token_salt"]
    rev = {b: tokenize(b, salt) for b in cfg["badge_roles"]}
    base = datetime(2025, 1, 20, tzinfo=timezone.utc)
    ev = []

    def mk(token, role, space, direction, ts, granted=True):
        return {"event_id": str(uuid.uuid4())[:8], "timestamp": ts, "token": token,
                "token_role": role, "space_id": space, "direction": direction,
                "access_granted": granted}

    def seq(role):
        perms = cfg["role_permissions"].get(role, ['entrada', 'lobby', 'salida'])
        work = [s for s in perms if s not in ('entrada', 'lobby', 'salida')]
        s = ['entrada', 'lobby']
        if work:
            s += rng.sample(work, min(len(work), 2))
        return s + ['salida']

    for day in range((n_days // 2) * 5):
        bid = rng.choice(list(cfg["badge_roles"].keys()))
        role = cfg["badge_roles"][bid]; token = rev[bid]
        dt = base + timedelta(days=day // 5)
        ts = dt.replace(hour=rng.randint(8, 10), minute=rng.randint(0, 59)).timestamp()
        for i, sp in enumerate(seq(role)):
            ev.append(mk(token, role, sp, 'enter', ts))
            stay = rng.randint(5, 30) * 60
            ev.append(mk(token, role, sp, 'exit', ts + stay))
            if i < len(seq(role)) - 1:
                ts = ts + stay + 120 + rng.randint(0, 60)
    # Ataque: imposible travel + violación de rol (external en servidores)
    atk_b = 'B004'; atk_t = rev[atk_b]; atk_r = cfg["badge_roles"][atk_b]
    atk = (base + timedelta(days=n_days // 2, hours=14, minutes=23)).timestamp()
    ev.append(mk(atk_t, atk_r, 'lobby', 'enter', atk))
    ev.append(mk(atk_t, atk_r, 'servidores', 'enter', atk + 45, granted=False))
    ev.append(mk(atk_t, atk_r, 'servidores', 'exit', atk + 600, granted=False))
    return ev


def _bytes_mov(datos: bytes, salt: str, badge_roles: dict) -> List[dict]:
    try:
        texto = datos.decode("utf-8")
    except Exception:
        return []
    rows = []
    try:
        obj = json.loads(texto)
        rows = obj if isinstance(obj, list) else [obj]
    except Exception:
        try:
            rows = list(csv.DictReader(io.StringIO(texto)))
        except Exception:
            return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        bid = str(r.get("badge_id", r.get("badge", "")))
        token = r.get("token") or (tokenize(bid, salt) if bid else "unknown")
        role = badge_roles.get(bid, r.get("role", "staff"))
        ts = r.get("timestamp", r.get("time"))
        try:
            ts = float(ts) if isinstance(ts, (int, float)) else datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        out.append({"event_id": str(uuid.uuid4())[:8], "timestamp": ts, "token": token,
                    "token_role": role, "space_id": str(r.get("space_id", r.get("space", "lobby"))),
                    "direction": str(r.get("direction", "enter")),
                    "access_granted": str(r.get("access_granted", "true")).lower() in ("true", "1", "yes")})
    return out


def firma_badge(events: List[dict], token: str, cfg: dict) -> np.ndarray:
    te = [e for e in events if e["token"] == token]
    if len(te) < 2:
        return np.full(7, 0.1)
    se = sorted(te, key=lambda e: e["timestamp"])
    off = sum(1 for e in te if not (8 <= datetime.fromtimestamp(e["timestamp"], tz=timezone.utc).hour <= 20)) / len(te)
    sp_div = len(set(e["space_id"] for e in te)) / max(len(cfg["spaces"]), 1)
    crit_sp = {s['id'] for s in cfg["spaces"] if s['sensitivity'] in ('critical', 'high')}
    crit = sum(1 for e in te if e["space_id"] in crit_sp) / len(te)
    denied = sum(1 for e in te if not e["access_granted"]) / len(te)
    vel = 0
    for i in range(1, len(se)):
        p, c = se[i - 1], se[i]
        if p["space_id"] != c["space_id"]:
            mn = _dijkstra(p["space_id"], c["space_id"])
            if c["timestamp"] - p["timestamp"] < mn / cfg["thresholds"]["impossible_travel_factor"]:
                vel += 1
    vel_a = min(vel / max(len(se) - 1, 1), 1.0)
    sc = defaultdict(int)
    for e in se:
        sc[e["space_id"]] += 1
    probs = np.array(list(sc.values()), dtype=float); probs /= probs.sum()
    ent = float(-np.sum(probs * np.log2(probs + 1e-10)))
    seq_reg = 1.0 - ent / np.log2(max(len(sc), 2))
    ts_l = [e["timestamp"] for e in te]
    span = max((max(ts_l) - min(ts_l)) / 86400, 1)
    freq = min(len(te) / span / 20, 1.0)
    return np.clip(np.array([off, sp_div, crit, denied, vel_a, seq_reg, freq]), 0, 1)


def firma_espacio(events: List[dict], sid: str, cfg: dict, win_h=1.0) -> dict:
    cap = SPACE_MAP.get(sid, {}).get("capacity", 10)
    se = sorted([e for e in events if e["space_id"] == sid], key=lambda e: e["timestamp"])
    if not se:
        return {"series": [], "mean": 0, "std": 1, "capacity": cap, "space_id": sid}
    win_s = win_h * 3600; series = []; cur = se[0]["timestamp"]; tmax = se[-1]["timestamp"]
    while cur < tmax:
        inw = set()
        for e in se:
            if cur <= e["timestamp"] < cur + win_s:
                if e["direction"] == "enter" and e["access_granted"]:
                    inw.add(e["token"])
                elif e["direction"] == "exit":
                    inw.discard(e["token"])
        series.append({"ts": cur, "occupancy": len(inw)})
        cur += win_s
    occ = [s["occupancy"] for s in series]
    return {"series": series, "mean": float(np.mean(occ)), "std": float(np.std(occ)),
            "capacity": cap, "space_id": sid}


def detect_it(events: List[dict], token: str, cfg: dict) -> List[str]:
    te = sorted([e for e in events if e["token"] == token], key=lambda e: e["timestamp"])
    out = []
    f = cfg["thresholds"]["impossible_travel_factor"]
    for i in range(1, len(te)):
        p, c = te[i - 1], te[i]
        if p["space_id"] == c["space_id"]:
            continue
        el = c["timestamp"] - p["timestamp"]
        mn = _dijkstra(p["space_id"], c["space_id"])
        if el < mn / f:
            out.append(f"Imposible travel: {p['space_id']}→{c['space_id']} en {el:.0f}s (min {mn:.0f}s)")
    return out


def _hash(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def ejecutar_movimiento(domain_id: str, fuente: str = "embudo",
                        archivos: Optional[List[dict]] = None, payload: Any = None,
                        seed: int = 42) -> dict:
    if domain_id not in DOMS:
        raise ValueError(f"Capa de movimiento aplica solo a las 6 empresas: {domain_id}")
    cfg = _config(domain_id)
    salt = cfg["token_salt"]; th = cfg["thresholds"]
    token_role = {tokenize(b, salt): r for b, r in cfg["badge_roles"].items()}

    if fuente == "api_webhook" and payload is not None:
        events = _bytes_mov(json.dumps(payload).encode() if not isinstance(payload, (bytes,)) else payload, salt, cfg["badge_roles"])
        origen = "API / webhook (lectores de acceso)"
    elif fuente == "embudo" and archivos:
        events = []
        for a in archivos:
            events.extend(_bytes_mov(a["datos"], salt, cfg["badge_roles"]))
        origen = f"Embudo — {len(archivos)} archivo(s)"
    else:
        events = generar_eventos(cfg, seed); origen = "Operación sintética demo (escenario mixed)"

    events = [e for e in events if e.get("timestamp")]
    if not events:
        return {"domain_id": domain_id, "origen": origen, "records": [], "stats": {},
                "ocupacion": [], "reporte": "Sin eventos de movimiento."}

    tokens = list(set(e["token"] for e in events))
    es = sorted(events, key=lambda e: e["timestamp"])
    base_ev = es[:max(len(es) // 2, 10)]
    baselines = {t: firma_badge(base_ev, t, cfg) for t in tokens}
    space_manifolds = {s["id"]: firma_espacio(events, s["id"], cfg) for s in cfg["spaces"]}

    space_anom = {}
    for sid, mf in space_manifolds.items():
        std = max(mf["std"], 0.1); anoms = []
        for w in mf["series"]:
            z = (w["occupancy"] - mf["mean"]) / std
            if abs(z) > th["space_occupancy_sigma"]:
                anoms.append(min(abs(z) / (th["space_occupancy_sigma"] * 2), 1.0))
            if w["occupancy"] > mf["capacity"]:
                anoms.append(min(w["occupancy"] / mf["capacity"], 1.0))
        if anoms:
            space_anom[sid] = max(anoms)

    records = []; alert_count = defaultdict(int)
    for token in tokens:
        role = token_role.get(token, "staff")
        base = baselines.get(token, np.full(7, 0.1))
        cur = firma_badge(events, token, cfg)
        badge_dis = float(np.mean(np.abs(cur - base)))
        if badge_dis < th["badge_dissonance_alert"]:
            baselines[token] = 0.95 * base + 0.05 * cur
        it = detect_it(events, token, cfg)
        perms = set(cfg["role_permissions"].get(role, []))
        role_v = [e for e in events if e["token"] == token and e["space_id"] not in perms]
        amp = badge_dis; atype = "behavioral"; desc = ""
        if it:
            amp = min(amp * 3.0, 1.0); atype = "impossible_travel"; desc = it[0]
        if role_v:
            amp = min(amp + 0.3, 1.0)
            atype = "role_violation" if not it else "impossible_travel+role_violation"
            if not desc:
                desc = f"{len(role_v)} accesos fuera de permisos del rol {role}"
        tok_sp = set(e["space_id"] for e in events if e["token"] == token)
        space_dis = max([space_anom.get(s, 0.0) for s in tok_sp], default=0.0)
        combined = amp * 0.6 + space_dis * 0.4
        if amp > th["badge_dissonance_alert"] and space_dis > 0:
            combined = min(combined * 1.5, 1.0)
        if not desc and space_dis > 0:
            desc = "Token en espacio anómalo"
        if combined < th["combined_dissonance_alert"] and not it:
            continue
        alert_count[token] += 1
        id_req = combined >= th["combined_dissonance_id"] and alert_count[token] >= th["id_resolution_events"]
        action = ("request_id_resolution" if id_req else
                  "report_impossible_travel" if it else "report_movement_anomaly")
        te = sorted([e for e in events if e["token"] == token], key=lambda e: e["timestamp"])
        rec = {
            "record_id": f"MR-{str(uuid.uuid4())[:8].upper()}",
            "timestamp": datetime.fromtimestamp(te[-1]["timestamp"], tz=timezone.utc).isoformat(),
            "token": token, "token_role": role, "space_id": te[-1]["space_id"],
            "anomaly_type": atype, "badge_dissonance": round(amp, 4),
            "space_dissonance": round(space_dis, 4), "combined_dissonance": round(combined, 4),
            "description": desc, "id_resolution_requested": id_req,
            "id_resolution_authorized": False, "id_resolution_by": [], "resolved_badge_id": "",
            "action": action, "override_token": str(uuid.uuid4())[:12],
        }
        rec["sha256"] = _hash({"record_id": rec["record_id"], "token": token,
                               "anomaly": atype, "combined": round(combined, 4)})
        records.append(rec)

    it_det = sum(1 for r in records if "impossible_travel" in r["anomaly_type"])
    id_reqs = sum(1 for r in records if r["id_resolution_requested"])
    ocupacion = [{"space_id": sid, "name": SPACE_MAP[sid]["name"], "mean": round(mf["mean"], 2),
                  "capacity": mf["capacity"], "sensitivity": SPACE_MAP[sid]["sensitivity"],
                  "anomalo": sid in space_anom} for sid, mf in space_manifolds.items()]
    reporte = _reporte(cfg, records, len(events), it_det, id_reqs)
    _persistir(domain_id, records)

    return {
        "domain_id": domain_id, "org_name": cfg["org_name"], "origen": origen,
        "stats": {"total_events": len(events), "forensic_recs": len(records),
                  "impossible_travel": it_det, "id_requests": id_reqs, "tokens_activos": len(tokens)},
        "records": sorted(records, key=lambda r: r["combined_dissonance"], reverse=True),
        "ocupacion": ocupacion, "reporte": reporte,
    }


def _reporte(cfg, records, n_ev, it_det, id_reqs) -> str:
    L = [f"## Capa de Movimiento — {cfg['org_name']}",
         f"**Bimestre:** {cfg.get('bimester','')}  ·  Privacidad por diseño (tokens anónimos)",
         "",
         f"- Eventos procesados: **{n_ev}**  ·  registros: **{len(records)}**",
         f"- 🚪 Imposible travel: **{it_det}**  ·  solicitudes de identidad: **{id_reqs}**", ""]
    if id_reqs:
        L.append("> ⚠️ Hay anomalías que requieren **resolución de identidad con doble autorización**.")
    for r in sorted(records, key=lambda x: x["combined_dissonance"], reverse=True)[:5]:
        marca = "🔴" if r["id_resolution_requested"] else "🟠"
        L.append(f"- {marca} `{r['token']}` ({r['token_role']}) — {r['anomaly_type']} · {r['description']}")
    return "\n".join(L)


def _persistir(domain_id: str, records: List[dict]):
    FORENSE_DIR.mkdir(parents=True, exist_ok=True)
    (FORENSE_DIR / f"{domain_id}.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def leer_forense(domain_id: str) -> List[dict]:
    p = FORENSE_DIR / f"{domain_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def resolver_identidad(domain_id: str, record_id: str, auth1: str, auth2: str) -> dict:
    if not auth1 or not auth2 or auth1 == auth2:
        return {"ok": False, "msg": "Requiere dos autorizadores distintos."}
    cfg = _config(domain_id)
    records = leer_forense(domain_id)
    rec = next((r for r in records if r["record_id"] == record_id), None)
    if not rec:
        return {"ok": False, "msg": f"Registro no encontrado: {record_id}"}
    if not rec["id_resolution_requested"]:
        return {"ok": False, "msg": "Este registro no requiere resolución de identidad."}
    badge = resolve_token(rec["token"], cfg["token_salt"], cfg["badge_roles"])
    if not badge:
        return {"ok": False, "msg": "No se pudo resolver el token."}
    rec["id_resolution_authorized"] = True
    rec["id_resolution_by"] = [auth1, auth2]
    rec["resolved_badge_id"] = badge
    _persistir(domain_id, records)
    return {"ok": True, "badge_id": badge, "role": cfg["badge_roles"].get(badge, "unknown"),
            "record_id": record_id, "msg": f"Identidad resuelta: {badge} (autorizan {auth1}, {auth2})"}
