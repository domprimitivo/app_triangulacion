"""
Backend tests — Ajuste Bimestral (Aprendiz)
============================================
Cubre:
1. GET /api/bimestral/ajuste/estado (dominio hotel, base=emitido_en)
2. Ejecución completa con datos sintéticos (contador) → entrenamiento real,
   reemplazo in-place con .bak, adapter incluido, sha256 cambia.
3. Bundle activo modificado sigue siendo válido (zip contiene policy_adapter.pt,
   policy_meta.json, allowed_actions_by_phase.json y conserva phase_rnn_state_dict.pt);
   BundleLoader lo carga (_cargado=True).
4. GET /api/bimestral/{dom}/ajuste/historial devuelve el run con entrenado=1.
5. Caso datos insuficientes: consultor_pyme sin learning log → entrenado=false,
   con motivo.
6. Scheduler: periodo_actual, ventana_periodo, fecha_proximo_ajuste e
   idempotencia de _tick.
"""
import os
import json
import shutil
import zipfile
import hashlib
import random
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get(
    "BACKEND_URL",
    "https://bimestral-activation.preview.emergentagent.com",
).rstrip("/")

BACKEND_DIR = Path("/app/backend")
APRENDIZ_DIR = BACKEND_DIR / "aprendiz_data"
MODELOS_DIR = BACKEND_DIR / "aprendiz_motor" / "modelos"
DB_PATH = BACKEND_DIR / "mileforum.db"

DOM_TRAIN = "contador"
DOM_EMPTY = "consultor_pyme"
BUNDLE_TRAIN = "contador_multiceph_bundle_v1"


# ─────────── helpers de seed / cleanup ───────────

def _seed_learning_log(dominio: str, n_events: int = 40):
    """Genera ~n eventos sintéticos dentro de los últimos 50 días."""
    log = APRENDIZ_DIR / f"{dominio}_learning_log.jsonl"
    APRENDIZ_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    action_ids = ["a_revisar_libro", "a_cerrar_periodo", "a_conciliar_bancos"]
    phases = ["stable", "tension"]
    lines = []
    random.seed(1)
    for i in range(n_events):
        ts = (now - timedelta(days=random.randint(0, 40),
                              hours=random.randint(0, 23))).isoformat()
        phase = phases[i % 2]
        p_stable = 0.7 if phase == "stable" else 0.3
        aid = action_ids[i % len(action_ids)]
        ev = {
            "timestamp": ts,
            "domain": dominio,
            "node_id": f"n_{i%3}",
            "backbone_inference": {
                "phase": phase,
                "phase_probs": {"stable": p_stable, "tension": 1 - p_stable},
                "clarity": {"ok": True, "pmax": p_stable,
                            "gap": abs(2 * p_stable - 1), "entropy": 0.5},
                "R_score": 0.4 + 0.01 * i,
            },
            "soft_context": {"soft_tags": ["cierre_mes"] if i % 3 == 0
                             else ["conciliacion", "iva"]},
            "action_execution": {
                "action_id": aid,
                "action_label": aid.replace("_", " "),
                "action_known": True,
                "user_accepted_suggestion": bool(i % 2),
            },
        }
        lines.append(json.dumps(ev, ensure_ascii=False))
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    action_dict = APRENDIZ_DIR / f"{dominio}_action_dictionary_state.json"
    actions_by_phase = {
        "stable": [{"action_id": a, "label": a} for a in action_ids],
        "tension": [{"action_id": a, "label": a} for a in action_ids],
    }
    action_dict.write_text(
        json.dumps({"actions_by_phase": actions_by_phase}, indent=2),
        encoding="utf-8",
    )


def _cleanup_dominio(dominio: str):
    for p in [
        APRENDIZ_DIR / f"{dominio}_learning_log.jsonl",
        APRENDIZ_DIR / f"{dominio}_action_dictionary_state.json",
    ]:
        if p.exists():
            p.unlink()
    ajustes_dir = APRENDIZ_DIR / "ajustes" / dominio
    if ajustes_dir.exists():
        shutil.rmtree(ajustes_dir, ignore_errors=True)


def _cleanup_bundle_files():
    if MODELOS_DIR.exists():
        for p in MODELOS_DIR.glob("*.zip"):
            p.unlink()
        for p in MODELOS_DIR.glob("*.bak_*.zip"):
            p.unlink()


def _cleanup_db_runs():
    if not DB_PATH.exists():
        return
    con = sqlite3.connect(str(DB_PATH))
    con.execute("DELETE FROM ajuste_bimestral_runs")
    con.commit()
    con.close()


@pytest.fixture(scope="module", autouse=True)
def _global_cleanup():
    """Cleanup residual state before, and after all tests."""
    _cleanup_dominio(DOM_TRAIN)
    _cleanup_dominio(DOM_EMPTY)
    _cleanup_bundle_files()
    _cleanup_db_runs()
    yield
    _cleanup_dominio(DOM_TRAIN)
    _cleanup_dominio(DOM_EMPTY)
    _cleanup_bundle_files()
    _cleanup_db_runs()


# ─────────── 1. Estado ───────────

def test_estado_ajuste_bimestral_hotel_base():
    r = requests.get(f"{BASE_URL}/api/bimestral/ajuste/estado", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["programado"] is True
    assert d["dominio"] == "hotel"
    assert d["periodo_dias"] == 50
    base = datetime.fromisoformat(d["activacion_base"])
    assert base.year == 2026 and base.month == 9 and base.day == 2
    prox = datetime.fromisoformat(d["proximo_ajuste"])
    # próximo = base + 50 días (mientras no haya runs y período_vigente=0 → índice 1)
    assert prox == base + timedelta(days=50)
    # dias_para_proximo_ajuste coherente
    ahora = datetime.now(timezone.utc)
    esperado = (prox - ahora).days
    assert abs(d["dias_para_proximo_ajuste"] - esperado) <= 1


# ─────────── 2 + 3. Ejecución con entrenamiento real ───────────

def test_ejecutar_ajuste_con_entrenamiento_real():
    _seed_learning_log(DOM_TRAIN, n_events=40)

    r = requests.post(f"{BASE_URL}/api/bimestral/{DOM_TRAIN}/ajuste/ejecutar",
                      timeout=180)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ejecutado"
    report = body["report"]

    # Training real
    training = report["training"]
    assert training["entrenado"] is True, f"training={training}"

    # Counts
    counts = report["counts"]
    assert counts["samples_supervised"] > 0
    assert counts["events_in_window"] > 0

    # Bundle reemplazo in-place
    bundle = report["bundle"]
    reemplazo = bundle["reemplazo_in_place"]
    assert reemplazo is not None
    assert reemplazo["adapter_incluido"] is True
    assert reemplazo["respaldo"].startswith(f"{BUNDLE_TRAIN}.bak_")
    assert "sha256_nuevo" in reemplazo
    sha_previo = bundle["sha256_previo"]
    assert sha_previo and reemplazo["sha256_nuevo"] != sha_previo

    # Backup y bundle nuevo existen físicamente
    activo = MODELOS_DIR / f"{BUNDLE_TRAIN}.zip"
    assert activo.exists()
    # sha256 en disco coincide con sha256_nuevo
    h = hashlib.sha256(activo.read_bytes()).hexdigest()
    assert h == reemplazo["sha256_nuevo"]
    backups = list(MODELOS_DIR.glob(f"{BUNDLE_TRAIN}.bak_*.zip"))
    assert len(backups) >= 1


def test_bundle_activo_valido_tras_reemplazo():
    activo = MODELOS_DIR / f"{BUNDLE_TRAIN}.zip"
    assert activo.exists(), "El bundle activo debe existir tras el ajuste"
    with zipfile.ZipFile(activo, "r") as z:
        names = z.namelist()
    prefix = f"{BUNDLE_TRAIN}/policy/"
    assert prefix + "policy_adapter.pt" in names
    assert prefix + "policy_meta.json" in names
    assert prefix + "allowed_actions_by_phase.json" in names
    # Conserva backbone
    backbone_present = any(n.endswith("backbone/phase_rnn_state_dict.pt")
                           for n in names)
    assert backbone_present, f"Falta phase_rnn_state_dict.pt en el bundle: {names[:10]}"

    # BundleLoader carga OK tras el reemplazo
    import sys
    sys.path.insert(0, str(BACKEND_DIR))
    from aprendiz_motor.notebook_engine import BundleLoader
    loader = BundleLoader(DOM_TRAIN)
    assert loader._cargado is True, "BundleLoader debe cargar tras el reemplazo"


# ─────────── 4. Historial ───────────

def test_historial_ajuste_incluye_run():
    r = requests.get(f"{BASE_URL}/api/bimestral/{DOM_TRAIN}/ajuste/historial",
                     timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["dominio"] == DOM_TRAIN
    assert d["total"] >= 1
    run = d["runs"][0]
    assert run["entrenado"] == 1
    assert run["disparado_por"] == "manual"


# ─────────── 5. Datos insuficientes ───────────

def test_ejecutar_ajuste_sin_datos_no_rompe():
    # Aseguramos no haya learning_log para DOM_EMPTY
    _cleanup_dominio(DOM_EMPTY)
    r = requests.post(f"{BASE_URL}/api/bimestral/{DOM_EMPTY}/ajuste/ejecutar",
                      timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ejecutado"
    training = body["report"]["training"]
    assert training["entrenado"] is False
    motivo = (training.get("motivo") or "").lower()
    assert "insuficientes" in motivo or "insuficiente" in motivo, training


# ─────────── 6. Scheduler ───────────

def test_scheduler_periodo_actual_y_proximo():
    import sys
    sys.path.insert(0, str(BACKEND_DIR))
    from aprendiz_motor.scheduler import (
        periodo_actual, ventana_periodo, fecha_proximo_ajuste, PERIODO_DIAS,
    )

    assert PERIODO_DIAS == 50
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ahora = base + timedelta(days=125)  # 2 períodos completos + 25 días
    assert periodo_actual(base, ahora) == 2

    ini, fin = ventana_periodo(base, 2)
    assert (fin - ini).days == 50
    assert fin == base + timedelta(days=100)

    # Sin runs previos y con periodo_vigente=2, el próximo es base + 100 (el pendiente)
    prox = fecha_proximo_ajuste(base, ultimo_indice_ejecutado=0, ahora=ahora)
    assert prox == base + timedelta(days=100)

    # Si ya se ejecutó hasta el índice 2 (al día), el próximo es 3
    prox2 = fecha_proximo_ajuste(base, ultimo_indice_ejecutado=2, ahora=ahora)
    assert prox2 == base + timedelta(days=150)


def test_scheduler_tick_es_idempotente():
    import sys
    sys.path.insert(0, str(BACKEND_DIR))
    from aprendiz_motor.scheduler import ProgramadorBimestral

    base = datetime.now(timezone.utc) - timedelta(days=60)  # 1 período pendiente
    calls = []

    def obtener_base():
        return base

    def obtener_dominio():
        return "mock_dom"

    # Simulamos que primero no hay runs, luego el _tick debería registrar 1
    ultimo_state = {"v": 0}

    def ultimo_indice(dominio):
        return ultimo_state["v"]

    def ejecutar(**kwargs):
        calls.append(kwargs)
        ultimo_state["v"] = kwargs["period_index"]  # marca como ejecutado
        return {"ok": True}

    prog = ProgramadorBimestral(
        obtener_base=obtener_base,
        obtener_dominio=obtener_dominio,
        ultimo_indice=ultimo_indice,
        ejecutar=ejecutar,
    )
    prog._tick()  # debería disparar
    prog._tick()  # NO debería re-disparar (idempotencia)
    prog._tick()

    assert len(calls) == 1, f"Se esperaba 1 disparo, hubo {len(calls)}"
    assert calls[0]["period_index"] == 1
    assert calls[0]["disparado_por"] == "scheduler"
