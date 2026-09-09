"""
Tests for Cucurucho embudo único:
- POST /api/flujo/ejecutar-dominio para 6 dominios (sin archivos) devuelve bundle + agora demo.
- Hotel con archivos reales (compras + habitacion_ocupacion) devuelve n_aplicados > 0 y señales limpias.
- GET /api/agora/historial/hotel refleja las corridas.
- Regresión Ágora endpoints + flujo cliente (mezcal).
"""
import io
import os
import csv
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    envp = "/app/frontend/.env"
    if os.path.exists(envp):
        for line in open(envp):
            if line.strip().startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")

BASE_URL = _load_backend_url()

DOMINIOS = [
    "dom_hotel_v1", "dom_restaurante_v1", "dom_retail_v1",
    "dom_fabrica_v1", "dom_logistica_v1", "dom_clinica_v1",
]


def _csv_bytes(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


# ---------- Sin archivos: 6 dominios devuelven bundle + agora demo ----------
@pytest.mark.parametrize("domain_id", DOMINIOS)
def test_ejecutar_dominio_sin_archivos_agora_demo(domain_id):
    r = requests.post(
        f"{BASE_URL}/api/flujo/ejecutar-dominio",
        data={"domain_id": domain_id, "modo": "demo", "calibrar": "false"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # Bundle previo intacto
    for k in ("kpis_holograficos", "metricas_discretas", "features_control",
              "memoria", "historial", "lazo"):
        assert k in d, f"[{domain_id}] falta {k}"
    # Nuevo agora
    ag = d.get("agora")
    assert ag is not None, f"[{domain_id}] agora nulo"
    prep = ag.get("preparacion") or {}
    assert prep.get("dominio_agora"), f"[{domain_id}] dominio_agora ausente"
    plano = ag.get("plano")
    assert isinstance(plano, list) and len(plano) > 0
    for n in plano:
        assert "x" in n and "alerta" in n
    assert "n_alertas" in ag
    origen = (ag.get("origen") or "").lower()
    assert "demo del dominio" in origen, f"[{domain_id}] origen inesperado: {ag.get('origen')}"


# ---------- Hotel con archivos reales ----------
def test_hotel_con_archivos_reales_agora_aplicada():
    compras = _csv_bytes(
        ["insumo_comprado", "material_comprado", "concentracion_proveedor"],
        [[10, 5, 0.4], [12, 6, 0.35], [11, 5.5, 0.45]],
    )
    actividad = _csv_bytes(
        ["habitacion_noche", "habitaciones_atendidas", "horas_camarista",
         "cubiertos_servidos", "horas_cocina", "ordenes_cerradas", "backlog_ordenes"],
        [[80, 78, 40, 120, 30, 15, 3], [90, 85, 45, 130, 32, 18, 2],
         [85, 80, 42, 125, 31, 16, 4]],
    )
    files = [
        ("files", ("compras_hotel.csv", compras, "text/csv")),
        ("files", ("habitacion_ocupacion.csv", actividad, "text/csv")),
    ]
    r = requests.post(
        f"{BASE_URL}/api/flujo/ejecutar-dominio",
        data={"domain_id": "dom_hotel_v1", "modo": "real", "calibrar": "false"},
        files=files, timeout=90,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # Bundle intacto
    assert "kpis_holograficos" in d and d["kpis_holograficos"] is not None
    ag = d.get("agora")
    assert ag is not None
    prep = ag["preparacion"]
    assert prep["n_aplicados"] > 0, f"n_aplicados={prep['n_aplicados']}"
    senales = prep.get("senales_agora") or {}
    assert "compras" in senales, f"señales sin 'compras': {list(senales)}"
    assert "actividad" in senales, f"señales sin 'actividad': {list(senales)}"
    # Valores promediados (limpieza AG3)
    assert isinstance(senales["compras"].get("insumo_comprado"), (int, float))
    assert isinstance(senales["actividad"].get("habitacion_noche"), (int, float))
    origen = (ag.get("origen") or "").lower()
    assert "coordenadas preparadas por ag3" in origen, ag.get("origen")


# ---------- Historial Ágora refleja corridas ----------
def test_historial_agora_hotel():
    r = requests.get(f"{BASE_URL}/api/agora/historial/hotel", params={"limit": 5}, timeout=30)
    assert r.status_code == 200, r.text
    h = r.json()
    corridas = h.get("corridas") or h.get("items") or []
    assert len(corridas) > 0, f"sin corridas: {h}"
    ult = corridas[0]
    origen = (ult.get("origen") or ult.get("origen_label") or "").lower()
    assert "cucurucho" in origen, f"origen no viene del cucurucho: {origen}"


# ---------- Regresión Ágora ----------
def test_agora_dominios_lista():
    r = requests.get(f"{BASE_URL}/api/agora/dominios", timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("dominios") or data.get("items") or []
    assert len(items) == 7, f"esperado 7 dominios, got {len(items)}"


def test_agora_dominio_hotel():
    r = requests.get(f"{BASE_URL}/api/agora/dominio/hotel", timeout=30)
    assert r.status_code == 200
    d = r.json()
    nodos = d.get("nodos") or []
    ids = {(n.get("nodo") or n.get("id")) if isinstance(n, dict) else n for n in nodos}
    for n in ("housekeeping", "food_beverage", "maintenance"):
        assert n in ids, f"nodo {n} ausente: {ids}"
    assert "demo_entradas" in d


def test_agora_triangular_manual():
    r = requests.post(
        f"{BASE_URL}/api/agora/triangular",
        json={"dominio_id": "hotel", "fuente": "manual", "entradas": None},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d.get("plano"), list) and len(d["plano"]) == 3


# ---------- Regresión flujo cliente ----------
def test_flujo_cliente_mezcal():
    r = requests.post(
        f"{BASE_URL}/api/flujo/ejecutar",
        data={"client_id": "cli_demo_mezcal_01", "modo": "demo", "calibrar": "false"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert "kpis_holograficos" in d
    # No debería incluir agora (demo palenque)
    assert d.get("agora") in (None, {}, False) or "agora" not in d
