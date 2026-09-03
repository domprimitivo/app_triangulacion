"""Genera un JSON de config de ciberseguridad por dominio empresarial (Modo 1)."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "flujo" / "ciber"
OUT.mkdir(parents=True, exist_ok=True)

# (domain_id, org_name, plataforma_siem, roles temáticos, activos temáticos)
DOMS = {
    "dom_restaurante_v1": ("Restaurante / Food Service", "splunk",
        [("chef", "Chef Ejecutivo", "kitchen", [8, 23]),
         ("cajero", "Cajero POS", "pos", [10, 22]),
         ("gerente", "Gerente Turno", "admin", [9, 20]),
         ("svc_pos", "Servicio POS", "service", [0, 23])],
        [("menu", "Sistema de Menú", "low"), ("pos", "Terminal de Pagos", "high"),
         ("inventario", "Inventario Insumos", "medium"), ("nomina", "Nómina", "high")]),
    "dom_retail_v1": ("Retail / Punto de venta", "sentinel",
        [("vendedor", "Vendedor Piso", "sales", [9, 21]),
         ("cajero", "Cajero", "pos", [9, 21]),
         ("gerente", "Gerente Tienda", "admin", [8, 20]),
         ("svc_erp", "Servicio ERP", "service", [0, 23])],
        [("pos", "Punto de Venta", "high"), ("stock", "Inventario Stock", "medium"),
         ("clientes", "Base Clientes", "high"), ("precios", "Catálogo Precios", "medium")]),
    "dom_hotel_v1": ("Hotelería", "chronicle",
        [("recepcion", "Recepción", "frontdesk", [0, 23]),
         ("housekeeping", "Ama de Llaves", "ops", [7, 18]),
         ("gerente", "Gerente General", "admin", [8, 20]),
         ("svc_pms", "Servicio PMS", "service", [0, 23])],
        [("pms", "Property Mgmt System", "high"), ("reservas", "Motor Reservas", "high"),
         ("facturacion", "Facturación", "high"), ("accesos", "Control Accesos", "medium")]),
    "dom_fabrica_v1": ("Manufactura / Fábrica", "cef",
        [("operador", "Operador Línea", "floor", [6, 22]),
         ("supervisor", "Supervisor Turno", "ops", [6, 22]),
         ("ingeniero", "Ingeniero Planta", "admin", [8, 19]),
         ("svc_scada", "Servicio SCADA", "service", [0, 23])],
        [("scada", "Sistema SCADA", "high"), ("mes", "MES Producción", "high"),
         ("calidad", "Control Calidad", "medium"), ("mantenimiento", "Mantenimiento", "low")]),
    "dom_logistica_v1": ("Logística / Distribución", "splunk",
        [("chofer", "Chofer Flota", "field", [5, 21]),
         ("despachador", "Despachador", "ops", [6, 22]),
         ("coordinador", "Coordinador Rutas", "admin", [7, 20]),
         ("svc_tms", "Servicio TMS", "service", [0, 23])],
        [("tms", "Transport Mgmt System", "high"), ("wms", "Warehouse Mgmt", "high"),
         ("rastreo", "Rastreo GPS", "medium"), ("facturacion", "Facturación", "high")]),
    "dom_clinica_v1": ("Clínica / Salud", "sentinel",
        [("medico", "Médico", "clinical", [7, 21]),
         ("enfermeria", "Enfermería", "clinical", [0, 23]),
         ("admin", "Administración", "admin", [8, 18]),
         ("svc_his", "Servicio HIS", "service", [0, 23])],
        [("his", "Historia Clínica (HIS)", "high"), ("laboratorio", "Laboratorio", "high"),
         ("farmacia", "Farmacia", "high"), ("citas", "Agenda Citas", "low")]),
}

for did, (name, plat, roles, assets) in DOMS.items():
    users = []
    for i, (rid, rname, role, hours) in enumerate(roles, 1):
        users.append({"id": f"{rid}", "name": rname, "role": role,
                      "typical_ips": [f"10.{i}.0.{10+i}"], "typical_hours": hours})
    cfg = {
        "domain_id": did,
        "org_name": name,
        "org_type": did,
        "principal_id": did.upper(),
        "bimester": "2026-B1",
        "users": users,
        "assets": [{"id": aid, "name": an, "sensitivity": sens} for aid, an, sens in assets],
        "nodes": [{
            "node_id": "SIEM-001", "node_type": "siem", "siem_platform": plat,
            "deployment_level": 0, "api_endpoint": "", "api_key": "",
            "webhook_url": "", "poll_interval_min": 30
        }],
        "thresholds": {"geo_dissonance_alert": 0.25, "geo_dissonance_report": 0.40},
    }
    (OUT / f"{did}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("escrito:", did)

print("OK")
