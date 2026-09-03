"""Backend tests for the Ciberseguridad Modo 1 (Observación Pasiva) product."""
import json
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback for tests: load .env
    from pathlib import Path
    env_p = Path("/app/frontend/.env")
    if env_p.exists():
        for line in env_p.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"


# ─── /api/ciber/herramientas ────────────────────────────────────────────────
def test_herramientas_list_four_with_modo1_available():
    r = requests.get(f"{API}/ciber/herramientas", timeout=30)
    assert r.status_code == 200
    data = r.json()
    hs = data["herramientas"]
    assert len(hs) == 4
    by_id = {h["id"]: h for h in hs}
    assert by_id["modo1"]["disponible"] is True
    for oid in ("modo2", "administrativa", "movimiento"):
        assert by_id[oid]["disponible"] is False


# ─── /api/ciber/dominios ────────────────────────────────────────────────────
def test_dominios_six_companies_no_palenque():
    r = requests.get(f"{API}/ciber/dominios", timeout=30)
    assert r.status_code == 200
    doms = r.json()["dominios"]
    assert len(doms) == 6
    ids = {d["domain_id"] for d in doms}
    expected = {"dom_restaurante_v1", "dom_retail_v1", "dom_hotel_v1",
                "dom_fabrica_v1", "dom_logistica_v1", "dom_clinica_v1"}
    assert ids == expected
    for d in doms:
        assert d["domain_id"].startswith("dom_")
        assert "palenque" not in d.get("id", "").lower()
        assert "palenque" not in d.get("nombre", "").lower()


# ─── /api/ciber/modo1/config ────────────────────────────────────────────────
def test_config_hotel_ok():
    r = requests.get(f"{API}/ciber/modo1/config", params={"dominio": "dom_hotel_v1"}, timeout=30)
    assert r.status_code == 200
    c = r.json()
    assert c["org_name"]
    assert "nodos_siem" in c and isinstance(c["nodos_siem"], list)
    assert "thresholds" in c
    assert "formatos_soportados" in c and len(c["formatos_soportados"]) >= 4


def test_config_invalid_domain_404():
    r = requests.get(f"{API}/ciber/modo1/config",
                     params={"dominio": "dom_fermentacion_lotes_v1"}, timeout=30)
    assert r.status_code == 404


# ─── /api/ciber/modo1/analizar (embudo demo) ────────────────────────────────
def test_analizar_embudo_demo_hotel():
    r = requests.post(f"{API}/ciber/modo1/analizar",
                      data={"domain_id": "dom_hotel_v1", "fuente": "embudo", "seed": 42},
                      timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    m = d["metricas"]
    for k in ("disonancia_media", "disonancia_max", "ventanas_total",
              "ventanas_alerta", "extremos_activos"):
        assert k in m
    assert isinstance(d["tendencia"], list)
    assert isinstance(d["top_ventanas"], list) and len(d["top_ventanas"]) <= 20
    assert isinstance(d["heatmap"], list)
    assert isinstance(d["reporte_bimestral"], str) and len(d["reporte_bimestral"]) > 20
    assert "memoria" in d and "ratio" in d["memoria"]


# ─── /api/ciber/modo1/analizar (api_webhook JSON Splunk) ────────────────────
def test_analizar_api_webhook_splunk_payload():
    events = []
    # build ~40 splunk-like events across time
    from datetime import datetime, timedelta, timezone
    base = datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc)
    users = ["recepcion", "housekeeping", "gerente", "svc_pms"]
    for i in range(40):
        t = (base + timedelta(hours=i * 1)).isoformat()
        events.append({"result": {"_time": t, "user": users[i % 4],
                                   "dest": "pms",
                                   "EventCode": ["USER_LOGIN", "FILE_OPEN", "FILE_COPY"][i % 3],
                                   "severity": "high" if i % 5 == 0 else "low",
                                   "action": "success" if i % 7 else "failure"}})
    r = requests.post(f"{API}/ciber/modo1/analizar",
                      data={"domain_id": "dom_hotel_v1", "fuente": "api_webhook",
                            "payload": json.dumps(events), "seed": 42},
                      timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["fuente"] == "api_webhook"
    assert d["metricas"]["ventanas_total"] >= 0
    assert "reporte_bimestral" in d


# ─── /api/ciber/modo1/analizar invalid domain ───────────────────────────────
@pytest.mark.parametrize("bad", ["dom_fermentacion_lotes_v1", "dom_x"])
def test_analizar_invalid_domain_400(bad):
    r = requests.post(f"{API}/ciber/modo1/analizar",
                      data={"domain_id": bad, "fuente": "embudo"}, timeout=60)
    assert r.status_code == 400


# ─── /api/ciber/modo1/historial ─────────────────────────────────────────────
def test_historial_hotel_after_analisis():
    # ensure at least one run
    requests.post(f"{API}/ciber/modo1/analizar",
                  data={"domain_id": "dom_hotel_v1", "fuente": "embudo"}, timeout=120)
    r = requests.get(f"{API}/ciber/modo1/historial/dom_hotel_v1", timeout=30)
    assert r.status_code == 200
    lst = r.json()
    assert isinstance(lst, list) and len(lst) >= 1
    it = lst[0]
    assert "id" in it and "ratio" in it and it.get("comprimido") is True
