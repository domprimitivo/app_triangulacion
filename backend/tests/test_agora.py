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


# ============================================================================
# NEW FEATURES: Umbral de alerta + Ingesta real (webhook + archivo)
# ============================================================================

# -- Umbral: GET/PUT persistencia ---------------------------------------------
def test_umbral_default_get(s):
    # Reset first to make deterministic (default 0.5)
    s.put(f"{API}/agora/umbral/hotel", json={"umbral": 0.5}, timeout=10)
    r = s.get(f"{API}/agora/umbral/hotel", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["dominio_id"] == "hotel"
    assert data["umbral"] == 0.5


def test_umbral_put_persiste(s):
    r = s.put(f"{API}/agora/umbral/hotel", json={"umbral": 0.6}, timeout=10)
    assert r.status_code == 200
    assert abs(r.json()["umbral"] - 0.6) < 1e-6
    # GET vuelve a 0.6
    r2 = s.get(f"{API}/agora/umbral/hotel", timeout=10)
    assert abs(r2.json()["umbral"] - 0.6) < 1e-6
    # cleanup
    s.put(f"{API}/agora/umbral/hotel", json={"umbral": 0.5}, timeout=10)


# -- Triangular con alertas y override ----------------------------------------
def test_triangular_hotel_alertas(s):
    # Set umbral 0.5 first
    s.put(f"{API}/agora/umbral/hotel", json={"umbral": 0.5}, timeout=10)
    r = s.post(f"{API}/agora/triangular", json={"dominio_id": "hotel", "fuente": "demo"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "umbral" in data
    assert "n_alertas" in data
    assert data["umbral"] == 0.5
    for p in data["plano"]:
        assert "alerta" in p
        assert p["alerta"] == (p["x"] >= data["umbral"])
    base_alertas = data["n_alertas"]

    # Bajar umbral a 0.2 y re-triangular → n_alertas incrementa (o >=)
    s.put(f"{API}/agora/umbral/hotel", json={"umbral": 0.2}, timeout=10)
    r2 = s.post(f"{API}/agora/triangular", json={"dominio_id": "hotel", "fuente": "demo"}, timeout=15)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["umbral"] == 0.2
    assert d2["n_alertas"] >= base_alertas
    # restore
    s.put(f"{API}/agora/umbral/hotel", json={"umbral": 0.5}, timeout=10)


def test_triangular_umbral_override_no_persiste(s):
    s.put(f"{API}/agora/umbral/hotel", json={"umbral": 0.5}, timeout=10)
    r = s.post(f"{API}/agora/triangular",
               json={"dominio_id": "hotel", "umbral": 0.9, "fuente": "demo"}, timeout=15)
    assert r.status_code == 200
    assert abs(r.json()["umbral"] - 0.9) < 1e-6
    # persistido sigue en 0.5
    r2 = s.get(f"{API}/agora/umbral/hotel", timeout=10)
    assert r2.json()["umbral"] == 0.5


# -- Webhook: buffer merge / DELETE -------------------------------------------
def test_webhook_buffer_merge_y_vaciar(s):
    # cleanup
    s.delete(f"{API}/agora/ingesta/buffer/gobierno", timeout=10)

    payload1 = {"agua": {"volumen_extraido_m3": 5000, "energia_kwh": 1000,
                          "y_senal": 0.7, "y_gamma": 0.5}}
    r = s.post(f"{API}/agora/ingesta/webhook/gobierno", json=payload1, timeout=10)
    assert r.status_code == 200
    assert "agua" in r.json()["nodos_en_buffer"]

    r2 = s.get(f"{API}/agora/ingesta/buffer/gobierno", timeout=10)
    assert r2.status_code == 200
    b = r2.json()
    assert b["n_nodos"] >= 1
    assert "agua" in b["entradas"]

    # Segundo POST con otro nodo → merge
    payload2 = {"nomina": {"nomina_pagada": 100.0, "empleados_biometricos": 90.0,
                            "concentracion_cuentas": 0.4,
                            "y_senal": 0.6, "y_gamma": 0.5}}
    r3 = s.post(f"{API}/agora/ingesta/webhook/gobierno", json=payload2, timeout=10)
    assert r3.status_code == 200
    b2 = s.get(f"{API}/agora/ingesta/buffer/gobierno", timeout=10).json()
    assert "agua" in b2["entradas"] and "nomina" in b2["entradas"]

    # DELETE vacía
    d = s.delete(f"{API}/agora/ingesta/buffer/gobierno", timeout=10)
    assert d.status_code == 200
    b3 = s.get(f"{API}/agora/ingesta/buffer/gobierno", timeout=10).json()
    assert b3["n_nodos"] == 0


def test_triangular_ingesta_live(s):
    s.delete(f"{API}/agora/ingesta/buffer/gobierno", timeout=10)
    payload = {"agua": {"volumen_extraido_m3": 5000, "energia_kwh": 1000,
                         "y_senal": 0.7, "y_gamma": 0.5}}
    s.post(f"{API}/agora/ingesta/webhook/gobierno", json=payload, timeout=10)
    r = s.post(f"{API}/agora/triangular",
               json={"dominio_id": "gobierno", "fuente": "ingesta_live"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "Ingesta en vivo" in data["origen"]
    plano_nodos = {p["nodo"] for p in data["plano"]}
    assert plano_nodos == {"agua"}
    # cleanup
    s.delete(f"{API}/agora/ingesta/buffer/gobierno", timeout=10)


# -- Ingesta por archivo JSON / CSV -------------------------------------------
def test_ingesta_archivo_json(s):
    import json as _json
    payload = {"housekeeping": {
        "insumo_comprado": 1250.0, "habitacion_noche": 1000.0,
        "concentracion_proveedor": 0.5,
        "habitaciones_atendidas": 100.0, "horas_camarista": 50.0,
        "y_senal": 0.6, "y_gamma": 0.5,
    }}
    files = {"files": ("hk.json", _json.dumps(payload).encode("utf-8"), "application/json")}
    data = {"dominio_id": "hotel"}
    r = s.post(f"{API}/agora/ingesta/archivo", files=files, data=data, timeout=15)
    assert r.status_code == 200, r.text
    resp = r.json()
    plano_nodos = {p["nodo"] for p in resp["plano"]}
    assert "housekeeping" in plano_nodos


def test_ingesta_archivo_csv(s):
    csv_text = ("nodo,insumo_comprado,habitacion_noche,concentracion_proveedor,"
                "habitaciones_atendidas,horas_camarista,y_senal,y_gamma\n"
                "housekeeping,1250,1000,0.5,100,50,0.6,0.5\n")
    files = {"files": ("hk.csv", csv_text.encode("utf-8"), "text/csv")}
    data = {"dominio_id": "hotel"}
    r = s.post(f"{API}/agora/ingesta/archivo", files=files, data=data, timeout=15)
    assert r.status_code == 200, r.text
    plano_nodos = {p["nodo"] for p in r.json()["plano"]}
    assert "housekeeping" in plano_nodos


def test_ingesta_archivo_vacio_400(s):
    files = {"files": ("empty.txt", b"", "text/plain")}
    data = {"dominio_id": "hotel"}
    r = s.post(f"{API}/agora/ingesta/archivo", files=files, data=data, timeout=10)
    assert r.status_code == 400
