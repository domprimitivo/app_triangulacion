"""Backend tests for Ciber Modo2 / Admin / Movimiento / Ingesta live."""
import json
import os
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    env_p = Path("/app/frontend/.env")
    if env_p.exists():
        for line in env_p.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"


# ─── /api/ciber/herramientas (4, todas disponibles) ─────────────────────────
def test_herramientas_all_four_available():
    r = requests.get(f"{API}/ciber/herramientas", timeout=30)
    assert r.status_code == 200
    hs = r.json()["herramientas"]
    assert len(hs) == 4
    for h in hs:
        assert h["disponible"] is True, f"{h['id']} debería estar disponible"
    ids = {h["id"] for h in hs}
    assert ids == {"modo1", "modo2", "administrativa", "movimiento"}


# ─── Modo 2 ─────────────────────────────────────────────────────────────────
class TestModo2:
    def test_analizar_hotel_embudo(self):
        r = requests.post(f"{API}/ciber/modo2/analizar",
                          data={"domain_id": "dom_hotel_v1", "fuente": "embudo", "seed": 42},
                          timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "forensic" in d and isinstance(d["forensic"], list)
        assert "adapter" in d
        assert "weights" in d["adapter"] and "correction_rate" in d["adapter"]
        assert "reporte_adapter" in d
        assert "metricas_modo1" in d
        if d["forensic"]:
            rec = d["forensic"][0]
            for k in ("override_token", "action", "recomendaciones", "sha256"):
                assert k in rec, f"missing {k} in forensic record"

    def test_analizar_invalid_domain_400(self):
        r = requests.post(f"{API}/ciber/modo2/analizar",
                          data={"domain_id": "dom_x_invalid", "fuente": "embudo"},
                          timeout=60)
        assert r.status_code == 400

    def test_flow_confirmar_override(self):
        r = requests.post(f"{API}/ciber/modo2/analizar",
                          data={"domain_id": "dom_hotel_v1", "fuente": "embudo", "seed": 42},
                          timeout=120)
        assert r.status_code == 200
        forensic = r.json()["forensic"]
        if len(forensic) < 2:
            pytest.skip("demo produjo <2 registros forensic")
        tok1 = forensic[0]["override_token"]
        tok2 = forensic[1]["override_token"]

        # Confirmar tok1
        rc = requests.post(f"{API}/ciber/modo2/confirmar",
                           params={"domain_id": "dom_hotel_v1"},
                           json={"override_token": tok1, "admin": "adminA"},
                           timeout=30)
        assert rc.status_code == 200, rc.text
        assert rc.json().get("ok") is True

        # Segundo confirm del mismo token → 400
        rc2 = requests.post(f"{API}/ciber/modo2/confirmar",
                            params={"domain_id": "dom_hotel_v1"},
                            json={"override_token": tok1, "admin": "adminA"},
                            timeout=30)
        assert rc2.status_code == 400

        # Override tok2
        ro = requests.post(f"{API}/ciber/modo2/override",
                           params={"domain_id": "dom_hotel_v1"},
                           json={"override_token": tok2, "admin": "adminB",
                                 "accion_correcta": None},
                           timeout=30)
        assert ro.status_code == 200, ro.text
        assert ro.json().get("ok") is True


# ─── Admin ──────────────────────────────────────────────────────────────────
class TestAdmin:
    def test_analizar_clinica(self):
        r = requests.post(f"{API}/ciber/admin/analizar",
                          data={"domain_id": "dom_clinica_v1", "fuente": "embudo", "seed": 42},
                          timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        st = d["stats"]
        for k in ("total_events", "forensic_recs", "critical", "gsl_attacks"):
            assert k in st
        assert isinstance(d.get("records"), list)
        if d["records"]:
            rec = d["records"][0]
            assert "gsl_self_attack" in rec
            # 8D dims + reasons
            assert "dims" in rec or "dimensiones" in rec or "vector" in rec
        assert "grafo" in d
        assert "reporte" in d

    def test_forense_clinica(self):
        # asegurar corrida
        requests.post(f"{API}/ciber/admin/analizar",
                      data={"domain_id": "dom_clinica_v1", "fuente": "embudo"}, timeout=120)
        r = requests.get(f"{API}/ciber/admin/forense/dom_clinica_v1", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json().get("records"), list)


# ─── Movimiento ─────────────────────────────────────────────────────────────
class TestMovimiento:
    def test_analizar_fabrica(self):
        r = requests.post(f"{API}/ciber/movimiento/analizar",
                          data={"domain_id": "dom_fabrica_v1", "fuente": "embudo", "seed": 42},
                          timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        st = d["stats"]
        for k in ("impossible_travel", "tokens_activos"):
            assert k in st
        assert "records" in d and isinstance(d["records"], list)
        if d["records"]:
            rec = d["records"][0]
            # Anonymous TK-* token
            tok = rec.get("token") or rec.get("token_anonimo") or rec.get("anon_token")
            assert tok and str(tok).startswith("TK-"), f"expected TK-* token, got {tok}"
            assert "anomaly_type" in rec or "tipo" in rec
            assert "combined_dissonance" in rec or "combined" in rec
        # ocupacion 8 espacios
        occ = d.get("ocupacion", [])
        assert isinstance(occ, list) and len(occ) == 8, f"expected 8 spaces, got {len(occ)}"
        assert any("anomalo" in o for o in occ), "missing anomalo flag on ocupacion"
        assert "reporte" in d

    def test_forense_fabrica(self):
        requests.post(f"{API}/ciber/movimiento/analizar",
                      data={"domain_id": "dom_fabrica_v1", "fuente": "embudo"}, timeout=120)
        r = requests.get(f"{API}/ciber/movimiento/forense/dom_fabrica_v1", timeout=30)
        assert r.status_code == 200
        assert "records" in r.json()

    def test_resolver_same_admin_400(self):
        r = requests.post(f"{API}/ciber/movimiento/resolver-identidad",
                          params={"domain_id": "dom_fabrica_v1"},
                          json={"record_id": "anything", "admin1": "a", "admin2": "a"},
                          timeout=30)
        assert r.status_code == 400

    def test_resolver_nonexistent_record_400(self):
        r = requests.post(f"{API}/ciber/movimiento/resolver-identidad",
                          params={"domain_id": "dom_fabrica_v1"},
                          json={"record_id": "rec_no_existe_xyz", "admin1": "a", "admin2": "b"},
                          timeout=30)
        assert r.status_code == 400


# ─── Ingesta en vivo ────────────────────────────────────────────────────────
class TestIngesta:
    def _mk_events(self, n=5):
        return [{"_time": "2025-01-15T09:00:00Z", "user": f"u{i}",
                 "src": "app", "dest": "pms",
                 "EventCode": "USER_LOGIN", "action": "success"} for i in range(n)]

    def test_webhook_and_buffer_and_consume_and_clear(self):
        dom = "dom_hotel_v1"
        # vaciar primero
        requests.delete(f"{API}/ciber/ingesta/buffer/{dom}", timeout=15)

        r = requests.post(f"{API}/ciber/ingesta/webhook/{dom}",
                          json=self._mk_events(6), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["eventos_agregados"] == 6
        assert d["buffer"]["total"] >= 6

        # buffer estado
        rb = requests.get(f"{API}/ciber/ingesta/buffer/{dom}", timeout=15)
        assert rb.status_code == 200
        jb = rb.json()
        assert jb["estado"]["total"] >= 6
        assert isinstance(jb["ultimos"], list) and len(jb["ultimos"]) >= 1

        # consumir con modo1 fuente=ingesta_live
        ra = requests.post(f"{API}/ciber/modo1/analizar",
                           data={"domain_id": dom, "fuente": "ingesta_live", "seed": 42},
                           timeout=120)
        assert ra.status_code == 200, ra.text
        da = ra.json()
        origen = str(da.get("origen", "") or da.get("fuente_desc", "") or json.dumps(da))
        assert "ingesta" in origen.lower() or "siem" in origen.lower() or da.get("fuente") == "ingesta_live"

        # vaciar
        rd = requests.delete(f"{API}/ciber/ingesta/buffer/{dom}", timeout=15)
        assert rd.status_code == 200
        rb2 = requests.get(f"{API}/ciber/ingesta/buffer/{dom}", timeout=15)
        assert rb2.json()["estado"]["total"] == 0

    def test_webhook_invalid_domain_400(self):
        r = requests.post(f"{API}/ciber/ingesta/webhook/dom_no_existe",
                          json=[{"a": 1}], timeout=15)
        assert r.status_code == 400

    def test_poll_unreachable_502(self):
        r = requests.post(f"{API}/ciber/ingesta/poll/dom_hotel_v1",
                          json={"url": "http://invalid.local", "api_key": ""},
                          timeout=30)
        assert r.status_code == 502
