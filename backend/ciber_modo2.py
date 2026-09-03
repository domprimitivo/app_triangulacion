"""
Elemento de Ciberseguridad — Herramienta B: GSL Modo 2 (Respuesta Adaptativa).

Puerto fiel del notebook `gsl_modo2_activo.ipynb` (Python stdlib + numpy).
Consume la disonancia del Modo 1. Añade:
  - PolicyAdapter: (disonancia + contexto) → acción recomendada (pesos aprendidos).
  - Ejecución por nivel (0 recomienda · 1 webhook · 2 API · 3 agente).
  - Override humano (con señal de entrenamiento) + confirmación.
  - Registro forense INMUTABLE (ForensicRecord con sha256) = lista rastreable.
Estado (adapter + forense) persistido por dominio. 100% local.
"""

import json
import uuid
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from ciber_modo1 import ejecutar_modo1 as _modo1, DOMINIOS_EMPRESARIALES

BASE = Path(__file__).resolve().parent
STATE_DIR = BASE / "flujo" / "ciber_modo2"

W_CONFIRM, W_CORRECTION, W_LOW_CLARITY = 1.0, 2.0, 0.5
ACTIONS = [
    "reduce_write_permissions", "increase_validation_weight", "snapshot_state",
    "isolate_session", "terminate_session", "revoke_credentials",
    "freeze_affected_assets", "generate_incident_report",
]
ACTIONS_DICT = {
    "reduce_write_permissions": {"description": "Reduce permisos de escritura", "reversible": True, "impact": "low", "min_dissonance": 0.25},
    "increase_validation_weight": {"description": "Añade latencia de validación", "reversible": True, "impact": "low", "min_dissonance": 0.25},
    "snapshot_state": {"description": "Copia inmutable del estado de activos", "reversible": False, "impact": "low", "min_dissonance": 0.25},
    "isolate_session": {"description": "Mueve sesión a sandbox de solo lectura", "reversible": True, "impact": "medium", "min_dissonance": 0.55},
    "terminate_session": {"description": "Cierra sesión con timeout", "reversible": False, "impact": "high", "min_dissonance": 0.70},
    "revoke_credentials": {"description": "Suspende credenciales hasta verificación", "reversible": True, "impact": "high", "min_dissonance": 0.70},
    "freeze_affected_assets": {"description": "Marca activos para auditoría", "reversible": True, "impact": "medium", "min_dissonance": 0.55},
    "generate_incident_report": {"description": "Ensambla línea de tiempo forense", "reversible": False, "impact": "none", "min_dissonance": 0.25},
}
ACTION_LEVELS = {a: 0 for a in ACTIONS}  # todas en Nivel 0 hasta que el cliente confíe más
LEVEL_LABELS = {0: "Nivel 0 — Recomendación (un click)", 1: "Nivel 1 — Webhook saliente",
                2: "Nivel 2 — API directa", 3: "Nivel 3 — Agente local"}


def _bucket(d: float) -> str:
    return "low" if d < 0.25 else "med" if d < 0.45 else "high" if d < 0.65 else "critical"


def _init_weights() -> Dict[str, Dict[str, float]]:
    w = {}
    for act in ACTIONS:
        m = ACTIONS_DICT[act]["min_dissonance"]
        w[act] = {"low": 1.0 if m <= 0.25 else 0.1, "med": 1.0 if 0.25 < m <= 0.45 else 0.3,
                  "high": 1.0 if 0.45 < m <= 0.65 else 0.2, "critical": 1.0 if m > 0.65 else 0.1}
    return w


def _state_path(domain_id: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{domain_id}.json"


def _load_state(domain_id: str) -> dict:
    p = _state_path(domain_id)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"weights": _init_weights(), "history": [], "correction_rate": 0.0, "forensic": []}


def _save_state(domain_id: str, st: dict):
    _state_path(domain_id).write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def recomendar(weights: dict, dissonance: float) -> List[dict]:
    b = _bucket(dissonance)
    out = []
    for act in ACTIONS:
        if dissonance < ACTIONS_DICT[act]["min_dissonance"]:
            continue
        out.append({"action": act, "score": round(weights.get(act, {}).get(b, 0.1), 4),
                    "level": ACTION_LEVELS.get(act, 0), "level_label": LEVEL_LABELS[ACTION_LEVELS.get(act, 0)],
                    "reversible": ACTIONS_DICT[act]["reversible"], "impact": ACTIONS_DICT[act]["impact"],
                    "description": ACTIONS_DICT[act]["description"]})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def _hash(rec: dict) -> str:
    payload = json.dumps({"record_id": rec["record_id"], "timestamp": rec["timestamp"],
                          "entity_id": rec["entity_id"], "action": rec["action"],
                          "dissonance": rec["dissonance"], "executed": rec["executed"]}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def ejecutar_modo2(domain_id: str, fuente: str = "embudo",
                   archivos: Optional[List[dict]] = None, payload: Any = None,
                   seed: int = 42) -> dict:
    if domain_id not in DOMINIOS_EMPRESARIALES:
        raise ValueError(f"Modo 2 aplica solo a las 6 empresas: {domain_id}")
    # 1. Consumir la disonancia del Modo 1 (no reconstruye la firma)
    m1 = _modo1(domain_id, fuente=fuente, archivos=archivos, payload=payload, seed=seed)
    th_alert = m1["thresholds"]["alert"]

    st = _load_state(domain_id)
    weights = st["weights"]

    # Máx disonancia por extremo
    por_ent = {}
    for row in m1["heatmap"]:
        por_ent[row["entity_id"]] = row["max"]

    nuevos = []
    for eid, dis in sorted(por_ent.items(), key=lambda x: x[1], reverse=True):
        if dis < th_alert:
            continue
        recs = recomendar(weights, dis)
        if not recs:
            continue
        top = recs[0]
        rec = {
            "record_id": f"FR-{str(uuid.uuid4())[:8].upper()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entity_id": eid, "dissonance": round(dis, 4),
            "action": top["action"], "level": top["level"], "level_label": top["level_label"],
            "recomendaciones": recs[:4],
            "executed": False,  # Nivel 0: pendiente de confirmación humana
            "execution_result": f"[L{top['level']}] Recomendación pendiente: {top['action']} sobre {eid}.",
            "override": False, "override_by": "", "override_action": "", "override_ts": "",
            "override_token": str(uuid.uuid4())[:12], "confirmed": False,
        }
        rec["sha256"] = _hash(rec)
        nuevos.append(rec)

    st["forensic"] = nuevos + st.get("forensic", [])
    st["forensic"] = st["forensic"][:200]
    _save_state(domain_id, st)

    return {
        "domain_id": domain_id, "org_name": m1.get("org_name"), "fuente": fuente,
        "origen": m1["origen"], "thresholds": m1["thresholds"],
        "metricas_modo1": m1["metricas"],
        "forensic": st["forensic"],
        "adapter": {"weights": weights, "correction_rate": round(st.get("correction_rate", 0.0), 4),
                    "decisiones": len(st.get("history", []))},
        "niveles": LEVEL_LABELS,
        "reporte_adapter": reporte_adapter(st),
    }


def _record_decision(st: dict, action: str, dissonance: float, confirmed: bool,
                     overridden_to: str = None):
    b = _bucket(dissonance)
    w = W_CONFIRM if confirmed else W_CORRECTION
    st["weights"].setdefault(action, _init_weights()[action])
    if confirmed:
        st["weights"][action][b] = min(st["weights"][action][b] * (1 + 0.1 * w), 3.0)
    else:
        st["weights"][action][b] = max(st["weights"][action][b] * (1 - 0.15 * w), 0.01)
        if overridden_to and overridden_to in st["weights"]:
            st["weights"][overridden_to][b] = min(st["weights"][overridden_to][b] * (1 + 0.2 * w), 3.0)
    st["history"].append({"timestamp": datetime.now(timezone.utc).isoformat(), "action": action,
                          "dissonance": dissonance, "bucket": b, "confirmed": confirmed,
                          "overridden_to": overridden_to})
    st["correction_rate"] = sum(1 for h in st["history"] if not h["confirmed"]) / len(st["history"])


def override(domain_id: str, override_token: str, admin: str, accion_correcta: str = None) -> dict:
    st = _load_state(domain_id)
    rec = next((r for r in st["forensic"] if r["override_token"] == override_token), None)
    if not rec:
        return {"ok": False, "msg": f"Token no encontrado: {override_token}"}
    if rec["override"]:
        return {"ok": False, "msg": f"Ya fue sobreescrito: {rec['record_id']}"}
    rec["override"] = True
    rec["override_by"] = admin
    rec["override_action"] = accion_correcta or "false_positive"
    rec["override_ts"] = datetime.now(timezone.utc).isoformat()
    _record_decision(st, rec["action"], rec["dissonance"], confirmed=False, overridden_to=accion_correcta)
    _save_state(domain_id, st)
    return {"ok": True, "record_id": rec["record_id"], "correction_rate": round(st["correction_rate"], 4),
            "weights": st["weights"], "msg": "Override aplicado. Señal de entrenamiento registrada."}


def confirmar(domain_id: str, override_token: str, admin: str) -> dict:
    st = _load_state(domain_id)
    rec = next((r for r in st["forensic"] if r["override_token"] == override_token), None)
    if not rec:
        return {"ok": False, "msg": f"Token no encontrado: {override_token}"}
    if rec.get("confirmed"):
        return {"ok": False, "msg": "Ya estaba confirmado."}
    rec["confirmed"] = True
    rec["executed"] = True
    rec["execution_result"] = f"[L{rec['level']}] Acción confirmada y ejecutada por {admin}: {rec['action']}."
    rec["sha256"] = _hash(rec)
    _record_decision(st, rec["action"], rec["dissonance"], confirmed=True)
    _save_state(domain_id, st)
    return {"ok": True, "record_id": rec["record_id"], "correction_rate": round(st["correction_rate"], 4),
            "msg": "Acción confirmada. Peso reforzado en el PolicyAdapter."}


def reporte_adapter(st: dict) -> str:
    hist = st.get("history", [])
    cr = st.get("correction_rate", 0.0)
    n = len(hist); conf = sum(1 for h in hist if h["confirmed"]); ov = n - conf
    L = [f"## PolicyAdapter", "",
         f"- Decisiones totales: **{n}**  ·  confirmadas: **{conf}**  ·  overrides: **{ov}**",
         f"- Correction rate: **{cr:.0%}**", ""]
    if cr > 0.4:
        L.append("> Aprendizaje inicial (normal en B1).")
    elif cr < 0.1 and n:
        L.append("> Adapter estabilizado — considera expandir acciones delegadas.")
    return "\n".join(L)


def leer_forense(domain_id: str) -> dict:
    st = _load_state(domain_id)
    return {"forensic": st.get("forensic", []), "adapter": {"weights": st["weights"],
            "correction_rate": round(st.get("correction_rate", 0.0), 4),
            "decisiones": len(st.get("history", []))}, "reporte_adapter": reporte_adapter(st)}
