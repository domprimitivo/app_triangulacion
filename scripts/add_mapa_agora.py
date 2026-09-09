"""Inyecta el bloque `mapa_agora` en cada cucurucho_{sector}_v1.json (idempotente)."""
import json
from pathlib import Path

MAIN = Path("/app")

MAPAS = {
    "hotel": {
        "dominio_agora": "hotel",
        "categorias_operacion": {
            "compras": {"keywords": ["compra", "insumo", "material", "proveedor"],
                        "columnas_esperadas": ["insumo_comprado", "material_comprado", "concentracion_proveedor"]},
            "actividad": {"keywords": ["habitacion", "ocupa", "cubierto", "orden", "atendid", "camarista", "cocina", "checkin"],
                          "columnas_esperadas": ["habitacion_noche", "habitaciones_atendidas", "horas_camarista",
                                                  "cubiertos_servidos", "horas_cocina", "ordenes_cerradas", "backlog_ordenes"]},
            "dinero": {"keywords": ["69b", "sat", "gamma", "bandera", "sobreprecio"],
                       "columnas_esperadas": ["y_senal", "y_gamma"]},
        },
        "columnas": {
            "housekeeping": {"insumo_comprado": "compras.insumo_comprado", "habitacion_noche": "actividad.habitacion_noche",
                             "concentracion_proveedor": "compras.concentracion_proveedor",
                             "habitaciones_atendidas": "actividad.habitaciones_atendidas", "horas_camarista": "actividad.horas_camarista",
                             "y_senal": "dinero.y_senal", "y_gamma": "dinero.y_gamma"},
            "food_beverage": {"insumo_comprado": "compras.insumo_comprado", "cubiertos_servidos": "actividad.cubiertos_servidos",
                              "concentracion_proveedor": "compras.concentracion_proveedor", "horas_cocina": "actividad.horas_cocina",
                              "y_senal": "dinero.y_senal", "y_gamma": "dinero.y_gamma"},
            "maintenance": {"material_comprado": "compras.material_comprado", "ordenes_cerradas": "actividad.ordenes_cerradas",
                            "concentracion_proveedor": "compras.concentracion_proveedor", "backlog_ordenes": "actividad.backlog_ordenes",
                            "y_senal": "dinero.y_senal", "y_gamma": "dinero.y_gamma"},
        },
    },
    "restaurante": {
        "dominio_agora": "restaurante",
        "categorias_operacion": {
            "compras": {"keywords": ["compra", "insumo", "bebida", "proveedor"],
                        "columnas_esperadas": ["insumo_comprado", "bebidas_compradas", "concentracion_proveedor"]},
            "actividad": {"keywords": ["cubierto", "servicio", "mesa", "cliente", "hora", "conteo", "inventario", "merma", "barra", "salon"],
                          "columnas_esperadas": ["cubiertos_servidos", "horas_cocina", "servicios_barra", "horas_bar",
                                                  "mesas_ocupadas", "mesas_servidas", "horas_salon", "clientes_atendidos",
                                                  "inventario_declarado", "conteo_fisico", "patron_acceso", "merma_reportada"]},
            "dinero": {"keywords": ["69b", "sat", "gamma"], "columnas_esperadas": ["y_senal", "y_gamma"]},
        },
        "columnas": {
            "cocina": {"insumo_comprado": "compras.insumo_comprado", "cubiertos_servidos": "actividad.cubiertos_servidos",
                       "concentracion_proveedor": "compras.concentracion_proveedor", "horas_cocina": "actividad.horas_cocina",
                       "merma_reportada": "actividad.merma_reportada"},
            "barra": {"bebidas_compradas": "compras.bebidas_compradas", "servicios_barra": "actividad.servicios_barra",
                      "concentracion_proveedor": "compras.concentracion_proveedor", "horas_bar": "actividad.horas_bar"},
            "salon": {"mesas_ocupadas": "actividad.mesas_ocupadas", "mesas_servidas": "actividad.mesas_servidas",
                      "horas_salon": "actividad.horas_salon", "clientes_atendidos": "actividad.clientes_atendidos"},
            "almacen_restaurante": {"inventario_declarado": "actividad.inventario_declarado", "conteo_fisico": "actividad.conteo_fisico",
                                    "patron_acceso": "actividad.patron_acceso", "merma_reportada": "actividad.merma_reportada"},
        },
    },
    "retail": {
        "dominio_agora": "retail",
        "categorias_operacion": {
            "ventas": {"keywords": ["venta", "ticket", "caja", "factura", "cliente", "unidad"],
                       "columnas_esperadas": ["tickets_reportados", "unidades_vendidas", "monto_facturado",
                                               "horas_caja", "clientes_atendidos", "ventas_totales"]},
            "inventario": {"keywords": ["inventario", "conteo", "merma", "stock", "rotacion", "acceso"],
                           "columnas_esperadas": ["inventario_declarado", "conteo_fisico", "patron_acceso",
                                                   "merma_reportada", "rotacion_esperada", "stock_final", "stock_critico"]},
            "compras": {"keywords": ["compra", "proveedor", "producto", "reposicion", "almacen", "orden"],
                        "columnas_esperadas": ["producto_comprado", "concentracion_proveedor", "producto_repuesto",
                                                "horas_almacen", "ordenes_reposicion"]},
            "devol": {"keywords": ["devol", "return", "motivo", "afectado"],
                      "columnas_esperadas": ["devoluciones_reportadas", "motivos_devolucion", "clientes_afectados"]},
        },
        "columnas": {
            "ventas_caja": {"tickets_reportados": "ventas.tickets_reportados", "unidades_vendidas": "ventas.unidades_vendidas",
                            "monto_facturado": "ventas.monto_facturado", "horas_caja": "ventas.horas_caja",
                            "clientes_atendidos": "ventas.clientes_atendidos"},
            "inventario_retail": {"inventario_declarado": "inventario.inventario_declarado", "conteo_fisico": "inventario.conteo_fisico",
                                  "patron_acceso": "inventario.patron_acceso", "merma_reportada": "inventario.merma_reportada",
                                  "rotacion_esperada": "inventario.rotacion_esperada"},
            "compras_retail": {"producto_comprado": "compras.producto_comprado", "unidades_vendidas": "ventas.unidades_vendidas",
                               "concentracion_proveedor": "compras.concentracion_proveedor", "stock_final": "inventario.stock_final"},
            "devoluciones": {"devoluciones_reportadas": "devol.devoluciones_reportadas", "ventas_totales": "ventas.ventas_totales",
                             "motivos_devolucion": "devol.motivos_devolucion", "clientes_afectados": "devol.clientes_afectados"},
            "reposicion": {"producto_repuesto": "compras.producto_repuesto", "horas_almacen": "compras.horas_almacen",
                           "stock_critico": "inventario.stock_critico", "ordenes_reposicion": "compras.ordenes_reposicion"},
        },
    },
    "fabrica": {
        "dominio_agora": "fabrica",
        "categorias_operacion": {
            "produccion": {"keywords": ["produc", "unidad", "capacidad", "linea", "yield", "buffer", "carga"],
                           "columnas_esperadas": ["unidades_producidas", "unidades_buenas", "capacidad", "horas_linea",
                                                   "yield_calidad", "buffer_salud", "carga_relativa_produccion"]},
            "calidad": {"keywords": ["calidad", "falla", "campo", "defecto"],
                        "columnas_esperadas": ["calidad_declarada", "tasa_falla_campo"]},
            "mantenimiento": {"keywords": ["mantenimiento", "backlog", "orden", "maquina", "cierre"],
                              "columnas_esperadas": ["backlog_ordenes", "ordenes_cerradas", "estado_maquina"]},
            "coherencia": {"keywords": ["coherencia", "clima", "escucha", "disciplina"],
                           "columnas_esperadas": ["coherencia"]},
        },
        "columnas": {
            "production": {"unidades_producidas": "produccion.unidades_producidas", "unidades_buenas": "produccion.unidades_buenas",
                           "capacidad": "produccion.capacidad", "horas_linea": "produccion.horas_linea",
                           "yield_calidad": "produccion.yield_calidad", "buffer_salud": "produccion.buffer_salud"},
            "quality": {"calidad_declarada": "calidad.calidad_declarada", "tasa_falla_campo": "calidad.tasa_falla_campo",
                        "unidades_buenas": "produccion.unidades_buenas", "unidades_producidas": "produccion.unidades_producidas",
                        "carga_relativa_produccion": "produccion.carga_relativa_produccion"},
            "maintenance": {"backlog_ordenes": "mantenimiento.backlog_ordenes", "ordenes_cerradas": "mantenimiento.ordenes_cerradas",
                            "estado_maquina": "mantenimiento.estado_maquina",
                            "carga_relativa_produccion": "produccion.carga_relativa_produccion"},
            "line_load": {"coherencia": "coherencia.coherencia"},
            "quality_discipline": {"coherencia": "coherencia.coherencia"},
            "maintenance_coherence": {"coherencia": "coherencia.coherencia"},
        },
    },
    "logistica": {
        "dominio_agora": "logistica",
        "categorias_operacion": {
            "operacion": {"keywords": ["entrega", "gps", "firma", "ruta", "vehiculo", "km", "kilometro", "tiempo"],
                          "columnas_esperadas": ["entregas_reportadas", "entregas_gps", "firmas_cliente", "horas_ruta",
                                                  "vehiculos_activos", "kilometros_recorridos", "tiempo_ruta_real",
                                                  "tiempo_ruta_esperado", "vehiculos_asignados", "entregas_realizadas"]},
            "compras": {"keywords": ["combustible", "mantenimiento", "proveedor", "falla"],
                        "columnas_esperadas": ["combustible_comprado", "combustible_esperado", "concentracion_proveedor",
                                                "mantenimiento_reportado", "mantenimiento_esperado", "fallas_vehiculo"]},
            "inventario": {"keywords": ["inventario", "conteo", "merma", "acceso", "almacen"],
                           "columnas_esperadas": ["inventario_declarado", "conteo_fisico", "patron_acceso", "merma_reportada"]},
        },
        "columnas": {
            "entregas": {"entregas_reportadas": "operacion.entregas_reportadas", "entregas_gps": "operacion.entregas_gps",
                         "firmas_cliente": "operacion.firmas_cliente", "horas_ruta": "operacion.horas_ruta",
                         "vehiculos_activos": "operacion.vehiculos_activos"},
            "combustible": {"combustible_comprado": "compras.combustible_comprado", "kilometros_recorridos": "operacion.kilometros_recorridos",
                            "combustible_esperado": "compras.combustible_esperado", "concentracion_proveedor": "compras.concentracion_proveedor"},
            "mantenimiento_vehiculos": {"mantenimiento_reportado": "compras.mantenimiento_reportado",
                                        "kilometros_recorridos": "operacion.kilometros_recorridos",
                                        "mantenimiento_esperado": "compras.mantenimiento_esperado", "fallas_vehiculo": "compras.fallas_vehiculo"},
            "rutas_operacion": {"tiempo_ruta_real": "operacion.tiempo_ruta_real", "tiempo_ruta_esperado": "operacion.tiempo_ruta_esperado",
                                "vehiculos_asignados": "operacion.vehiculos_asignados", "entregas_realizadas": "operacion.entregas_realizadas"},
            "almacen_logistica": {"inventario_declarado": "inventario.inventario_declarado", "conteo_fisico": "inventario.conteo_fisico",
                                  "patron_acceso": "inventario.patron_acceso", "merma_reportada": "inventario.merma_reportada"},
        },
    },
    "clinica": {
        "dominio_agora": "clinica",
        "categorias_operacion": {
            "atencion": {"keywords": ["consulta", "paciente", "atencion", "medico", "estancia", "cama", "alta", "ingreso",
                                       "procedimiento", "quirurg", "muestra", "laboratorio", "prescrip", "dosis"],
                         "columnas_esperadas": ["consultas_reportadas", "duracion_promedio_consulta", "tiempo_total_atencion",
                                                 "horas_medico", "pacientes_atendidos", "procedimientos_reportados", "material_utilizado",
                                                 "insumo_por_procedimiento", "horas_quirurgicas", "dias_estancia_reportados",
                                                 "ocupacion_cama_real", "pacientes_ingresados", "altas", "pacientes_tratados",
                                                 "muestras_reportadas", "reactivos_consumidos", "horas_laboratorio",
                                                 "prescripciones_emitidas", "dosis_promedio"]},
            "compras": {"keywords": ["farmaco", "insumo", "compra", "proveedor", "reactivo"],
                        "columnas_esperadas": ["farmacos_comprados", "concentracion_proveedor"]},
        },
        "columnas": {
            "consultas_medicas": {"consultas_reportadas": "atencion.consultas_reportadas", "duracion_promedio_consulta": "atencion.duracion_promedio_consulta",
                                  "tiempo_total_atencion": "atencion.tiempo_total_atencion", "horas_medico": "atencion.horas_medico",
                                  "pacientes_atendidos": "atencion.pacientes_atendidos"},
            "procedimientos_clinicos": {"procedimientos_reportados": "atencion.procedimientos_reportados",
                                        "insumo_por_procedimiento": "atencion.insumo_por_procedimiento",
                                        "material_utilizado": "atencion.material_utilizado", "horas_quirurgicas": "atencion.horas_quirurgicas"},
            "estancias_hospitalarias": {"dias_estancia_reportados": "atencion.dias_estancia_reportados", "ocupacion_cama_real": "atencion.ocupacion_cama_real",
                                        "pacientes_ingresados": "atencion.pacientes_ingresados", "altas": "atencion.altas"},
            "farmacia": {"farmacos_comprados": "compras.farmacos_comprados", "pacientes_tratados": "atencion.pacientes_tratados",
                         "dosis_promedio": "atencion.dosis_promedio", "prescripciones_emitidas": "atencion.prescripciones_emitidas"},
            "laboratorio_clinico": {"muestras_reportadas": "atencion.muestras_reportadas", "reactivos_consumidos": "atencion.reactivos_consumidos",
                                    "horas_laboratorio": "atencion.horas_laboratorio"},
        },
    },
}


def main():
    for sector, mapa in MAPAS.items():
        p = MAIN / f"cucurucho_{sector}_v1.json"
        if not p.exists():
            print(f"SKIP (no existe): {p.name}")
            continue
        cfg = json.loads(p.read_text(encoding="utf-8"))
        cfg["mapa_agora"] = mapa
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK: {p.name} (+ mapa_agora, dominio_agora={mapa['dominio_agora']})")


if __name__ == "__main__":
    main()
