"""Tests for El Ágora Unificado (Retícula de Triangulación)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend env file
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass

API = f"{BASE_URL}/api"

EXPECTED_NODES = {
    "hotel": 3, "restaurante": 4, "clinica": 5, "logistica": 5,
    "retail": 5, "fabrica": 6, "gobierno": 3,
}


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# -- Listado de dominios ------------------------------------------------------
def test_listar_dominios(s):
    r = s.get(f"{API}/agora/dominios", timeout=10)
    assert r.status_code == 200
    doms = r.json()["dominios"]
    assert len(doms) == 7
    got = {d["id"]: d["n_nodos"] for d in doms}
    assert got == EXPECTED_NODES
    for d in doms:
        for k in ("id", "etiqueta", "triangulacion", "primaria", "n_nodos"):
            assert k in d


# -- Info por dominio ---------------------------------------------------------
def test_info_hotel(s):
    r = s.get(f"{API}/agora/dominio/hotel", timeout=10)
    assert r.status_code == 200
    info = r.json()
    assert "demo_entradas" in info
    assert len(info["nodos"]) == 3
    for n in info["nodos"]:
        for k in ("observables", "primitivo", "tipo", "tiene_avance", "y_tipo"):
            assert k in n
        assert n["nodo"] in info["demo_entradas"]


def test_info_dominio_inexistente(s):
    r = s.get(f"{API}/agora/dominio/inexistente_xyz", timeout=10)
    assert r.status_code == 404


# -- Triangular hotel con demo ------------------------------------------------
def test_triangular_hotel_demo(s):
    r = s.post(f"{API}/agora/triangular", json={"dominio_id": "hotel"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "paquetes" in data and "plano" in data
    assert len(data["plano"]) == 3
    for p in data["plano"]:
        assert 0.0 <= p["x"] <= 1.0
        assert p["y_tipo"] == "externa"
        for k in ("nodo", "x", "y", "tipo", "avance"):
            assert k in p


# -- Gobierno: catastro=stock/coherencia_stock; agua/nomina=disonancia_vs_fisico
def test_triangular_gobierno_demo(s):
    r = s.post(f"{API}/agora/triangular", json={"dominio_id": "gobierno"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    paq = data["paquetes"]
    assert paq["catastro"]["primitivo"] == "coherencia_stock"
    assert paq["catastro"]["tipo"] == "stock"
    assert paq["catastro"]["avance"] is None
    assert paq["agua"]["primitivo"] == "disonancia_vs_fisico"
    assert paq["nomina"]["primitivo"] == "disonancia_vs_fisico"
    for p in data["plano"]:
        assert p["y_tipo"] == "externa"


# -- Fábrica: triangulación interna + nodos blandos ---------------------------
def test_triangular_fabrica_demo(s):
    r = s.post(f"{API}/agora/triangular", json={"dominio_id": "fabrica"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    paq = data["paquetes"]

    assert paq["production"]["primitivo"] == "saturacion"
    assert paq["quality"]["primitivo"] == "disonancia_vs_fisico"
    assert paq["maintenance"]["primitivo"] == "deuda_backlog"

    for n in ("production", "quality", "maintenance"):
        assert paq[n]["y"]["tipo"] == "interna"

    # 3 blandas
    for n in ("line_load", "quality_discipline", "maintenance_coherence"):
        assert paq[n]["tipo"] == "blanda"
        assert paq[n]["x"] is None
        assert paq[n]["coherencia"] is not None

    # plano NO incluye blandas
    plano_nodos = {p["nodo"] for p in data["plano"]}
    assert plano_nodos == {"production", "quality", "maintenance"}


# -- Entradas personalizadas: x cambia según valores --------------------------
def test_triangular_hotel_entradas_custom(s):
    # reportado muy por encima del físico → x alto
    entradas = {
        "housekeeping": {
            "insumo_comprado": 2000.0,
            "habitacion_noche": 1000.0,
            "concentracion_proveedor": 0.8,
            "habitaciones_atendidas": 300.0,
            "horas_camarista": 120.0,
            "y_senal": 0.6, "y_gamma": 0.5,
        },
        "food_beverage": {
            "insumo_comprado": 1000.0,
            "cubiertos_servidos": 1000.0,
            "concentracion_proveedor": 0.0,
            "horas_cocina": 100.0,
            "y_senal": 0.6, "y_gamma": 0.5,
        },
        "maintenance": {
            "material_comprado": 1000.0,
            "ordenes_cerradas": 1000.0,
            "concentracion_proveedor": 0.0,
            "backlog_ordenes": 100.0,
            "y_senal": 0.6, "y_gamma": 0.5,
        },
    }
    r = s.post(f"{API}/agora/triangular", json={"dominio_id": "hotel", "entradas": entradas}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    xs = {p["nodo"]: p["x"] for p in data["plano"]}
    # housekeeping tiene reportado mucho > fisico → x cerca de 1 (peso 0.8*0.5/0.25 + 0.2*0.8 = 1.76 → clip 1.0)
    assert xs["housekeeping"] >= 0.9
    # food_beverage y maintenance reportado == fisico → x = 0
    assert xs["food_beverage"] == 0.0
    assert xs["maintenance"] == 0.0


def test_triangular_hotel_entradas_incompletas(s):
    entradas = {"housekeeping": {"insumo_comprado": 100.0}}  # faltan observables
    r = s.post(f"{API}/agora/triangular", json={"dominio_id": "hotel", "entradas": entradas}, timeout=15)
    assert r.status_code == 400


# -- Fórmulas de primitivos (validación aritmética) ---------------------------
def test_formula_disonancia_vs_fisico_reportado_excede(s):
    """dison=(rep-fis)/rep; x=peso*max(dison,0)/div (+ sec*sec_peso), clip[0,1]"""
    entradas = {
        "housekeeping": {
            "insumo_comprado": 1250.0, "habitacion_noche": 1000.0,
            "concentracion_proveedor": 0.5,
            "habitaciones_atendidas": 100.0, "horas_camarista": 50.0,
            "y_senal": 0.6, "y_gamma": 0.5,
        },
        "food_beverage": {
            "insumo_comprado": 1000.0, "cubiertos_servidos": 1000.0,
            "concentracion_proveedor": 0.0, "horas_cocina": 50.0,
            "y_senal": 0.6, "y_gamma": 0.5,
        },
        "maintenance": {
            "material_comprado": 1000.0, "ordenes_cerradas": 1000.0,
            "concentracion_proveedor": 0.0, "backlog_ordenes": 100.0,
            "y_senal": 0.6, "y_gamma": 0.5,
        },
    }
    r = s.post(f"{API}/agora/triangular", json={"dominio_id": "hotel", "entradas": entradas}, timeout=15)
    assert r.status_code == 200
    xs = {p["nodo"]: p["x"] for p in r.json()["plano"]}
    # dison = 250/1250 = 0.2 ; x = 0.8*0.2/0.25 + 0.2*0.5 = 0.64 + 0.10 = 0.74
    assert abs(xs["housekeeping"] - 0.74) < 0.01


def test_formula_coherencia_stock(s):
    """Gobierno catastro: dison=(activo-just)/activo; x=peso*dison/div"""
    entradas_full = requests.get(f"{API}/agora/dominio/gobierno", timeout=10).json()["demo_entradas"]
    entradas_full["catastro"]["valor_mercado"] = 1000.0
    entradas_full["catastro"]["ingreso_declarado"] = 200.0
    r = s.post(f"{API}/agora/triangular", json={"dominio_id": "gobierno", "entradas": entradas_full}, timeout=15)
    assert r.status_code == 200
    xs = {p["nodo"]: p["x"] for p in r.json()["plano"]}
    # dison = (1000-200)/1000 = 0.8 ; x = 1.0 * 0.8 / 0.8 = 1.0
    assert abs(xs["catastro"] - 1.0) < 0.01


def test_formula_saturacion_fabrica(s):
    entradas_full = requests.get(f"{API}/agora/dominio/fabrica", timeout=10).json()["demo_entradas"]
    entradas_full["production"]["unidades_producidas"] = 1200.0
    entradas_full["production"]["capacidad"] = 1000.0
    r = s.post(f"{API}/agora/triangular", json={"dominio_id": "fabrica", "entradas": entradas_full}, timeout=15)
    assert r.status_code == 200
    xs = {p["nodo"]: p["x"] for p in r.json()["plano"]}
    # dison = max(1200/1000-1, 0) = 0.2 ; x = 1.0 * 0.2 / 0.25 = 0.8
    assert abs(xs["production"] - 0.8) < 0.01


# -- Nomina con concentracion_cuentas sec_obs no listado en observables -------
def test_gobierno_nomina_sec_obs_ok(s):
    """El demo debe rellenar concentracion_cuentas aunque no esté en 'observables'; sin KeyError."""
    r = s.post(f"{API}/agora/triangular", json={"dominio_id": "gobierno"}, timeout=15)
    assert r.status_code == 200
    paq = r.json()["paquetes"]
    assert paq["nomina"]["x"] is not None
