"""
Conector único, parametrizado por JSON de dominio
=================================================
Un solo motor (ciego al dominio) + una librería de PRIMITIVOS de ancla + un JSON por dominio.
El JSON de hotel emite paquetes para housekeeping / food_beverage / maintenance;
el de gobierno, para agua / nomina / catastro. El motor no cambia.

Disciplina: NINGÚN `if dominio == "..."` dentro del motor. Todo el conocimiento del dominio
vive en el JSON + los primitivos. Si aparece un `if` de dominio en el motor, ese pedazo
pertenece al JSON o a un primitivo nuevo.
"""
from __future__ import annotations
import json
from typing import Callable

import numpy as np


# ======================================================================================
# LIBRERÍA DE PRIMITIVOS DE ANCLA
# Pocos y reutilizables. El JSON SELECCIONA y CONFIGURA uno; no escribe fórmulas libres
# (evaluar expresiones arbitrarias del JSON sería frágil e inseguro).
# ======================================================================================
PRIMITIVOS: dict[str, Callable[[dict, dict], dict]] = {}

def primitivo(nombre: str):
    def reg(fn): PRIMITIVOS[nombre] = fn; return fn
    return reg


@primitivo("disonancia_vs_fisico")
def disonancia_vs_fisico(obs: dict, params: dict) -> dict:
    """Patrón "reportado vs realidad física": lo cubren agua, nomina, catastro y los tres de
    hotel. reportado = lo que el actor controla; fisico = ancla infalsificable derivada de un
    observable * factor. x = razón de disonancia ponderada + término secundario opcional.
      params: {reportado, fisico_obs, fisico_factor, div, peso, sec_obs?, sec_peso?}
    """
    reportado = obs[params["reportado"]]
    fisico = obs[params["fisico_obs"]] * params.get("fisico_factor", 1.0)
    # >0 => lo reportado excede lo que el físico justifica (o al revés, según orientacion)
    if params.get("orientacion", "reportado_excede") == "fisico_excede":
        dison = (fisico - reportado) / fisico if fisico else 0.0
    else:
        dison = (reportado - fisico) / reportado if reportado else 0.0
    x = params.get("peso", 1.0) * max(dison, 0.0) / params.get("div", 0.25)
    detalle = {"disonancia": round(dison, 3), "reportado": round(reportado, 1),
               "fisico_justificado": round(fisico, 1)}
    if "sec_obs" in params:
        sec = obs[params["sec_obs"]]
        x += params.get("sec_peso", 0.0) * sec
        detalle["secundario"] = round(sec, 3)
    return {"x": float(np.clip(x, 0.0, 1.0)), "detalle": detalle}


@primitivo("coherencia_stock")
def coherencia_stock(obs: dict, params: dict) -> dict:
    """Nodos de stock (catastro/declaraciones): sin throughput; coherencia acumulación vs
    justificación. params: {activo, justificacion, div, peso}"""
    activo = obs[params["activo"]]
    just = obs[params["justificacion"]]
    dison = (activo - just) / activo if activo else 0.0
    x = params.get("peso", 1.0) * max(dison, 0.0) / params.get("div", 0.8)
    return {"x": float(np.clip(x, 0.0, 1.0)),
            "detalle": {"disonancia": round(dison, 3), "activo": activo, "justificacion": just}}


def avance_throughput(obs: dict, params: dict | None) -> float | None:
    """Numerador de avance para nodos de flujo. None si el nodo no es de flujo."""
    if not params:
        return None
    num, den = obs[params["numerador"]], obs[params["denominador"]]
    return round(num / den, 3) if den else None


# ======================================================================================
# EL MOTOR CONECTOR  (ciego al dominio)
# Cuatro módulos: embudo/ingesta -> observador (primitivo de ancla) -> atlas -> declarador γ.
# ======================================================================================
class Conector:
    def __init__(self, dominio_json: dict):
        self.dom = dominio_json
        self.dominio = dominio_json["dominio"]

    # Módulo 1 — embudo/ingesta: aquí ya recibe el dict de observables (webhook/API/archivo).
    def _ingesta(self, entrada: dict, nodo_cfg: dict) -> dict:
        campos = nodo_cfg["observables"]
        faltan = [c for c in campos if c not in entrada]
        if faltan:
            raise ValueError(f"faltan observables {faltan} para {nodo_cfg['nodo']}")
        return {c: entrada[c] for c in campos}

    # Módulo 2 — observador: aplica el PRIMITIVO seleccionado por el JSON.
    def _observar(self, obs: dict, nodo_cfg: dict) -> dict:
        prim = PRIMITIVOS[nodo_cfg["ancla"]["primitivo"]]
        return prim(obs, nodo_cfg["ancla"]["params"])

    # Módulo 4 — declarador de γ para la coordenada importada (dinero u otra).
    def _gamma(self, entrada: dict, nodo_cfg: dict) -> dict:
        y = entrada[nodo_cfg["coordenada_y"]["senal_campo"]]
        gy = entrada.get(nodo_cfg["coordenada_y"]["gamma_campo"],
                         nodo_cfg["coordenada_y"].get("gamma_default", 0.5))
        return {"senal": y, "gamma_y": gy}

    def paquete_para(self, nodo: str, entrada: dict) -> dict:
        """Genera el Paquete de Decisión Limpia para un decisor (nodo) del dominio."""
        cfg = self.dom["nodos"][nodo]
        obs = self._ingesta(entrada, cfg)
        anc = self._observar(obs, cfg)
        avance = avance_throughput(obs, cfg.get("avance"))
        return {
            "token": entrada["token"],
            "timestamp_fase": entrada.get("timestamp_fase"),
            "dominio": self.dominio,
            "nodo": nodo,
            "tipo": cfg.get("tipo", "flujo"),
            "x": anc["x"],
            "x_detalle": anc["detalle"],
            "avance": avance,                          # None si no es de flujo
            "y_dinero": self._gamma(entrada, cfg),     # Módulo 3/atlas se agrega aquí si aplica
        }

    def generar_todos(self, entradas: dict[str, dict]) -> dict[str, dict]:
        """entradas: {nodo: observables}. Devuelve {nodo: paquete}. Un Conector, N decisores."""
        return {nodo: self.paquete_para(nodo, ent) for nodo, ent in entradas.items()}


# ======================================================================================
# JSON DE DOMINIO — HOTEL (lado costo). Emite para housekeeping / food_beverage / maintenance.
# Esto es un ARCHIVO de configuración; en producción vive fuera del código.
# ======================================================================================
HOTEL_JSON = {
    "dominio": "hotel_costo",
    "nodos": {
        "housekeeping": {
            "nodo": "housekeeping", "tipo": "flujo",
            "observables": ["insumo_comprado", "habitacion_noche", "concentracion_proveedor",
                            "habitaciones_atendidas", "horas_camarista"],
            "ancla": {"primitivo": "disonancia_vs_fisico",
                      "params": {"reportado": "insumo_comprado", "fisico_obs": "habitacion_noche",
                                 "fisico_factor": 1.0, "div": 0.25, "peso": 0.8,
                                 "sec_obs": "concentracion_proveedor", "sec_peso": 0.2}},
            "avance": {"numerador": "habitaciones_atendidas", "denominador": "horas_camarista"},
            "coordenada_y": {"senal_campo": "y_senal", "gamma_campo": "y_gamma", "gamma_default": 0.5},
        },
        "food_beverage": {
            "nodo": "food_beverage", "tipo": "flujo",
            "observables": ["insumo_comprado", "cubiertos_servidos", "concentracion_proveedor",
                            "horas_cocina"],
            "ancla": {"primitivo": "disonancia_vs_fisico",
                      "params": {"reportado": "insumo_comprado", "fisico_obs": "cubiertos_servidos",
                                 "fisico_factor": 1.0, "div": 0.25, "peso": 0.8,
                                 "sec_obs": "concentracion_proveedor", "sec_peso": 0.2}},
            "avance": {"numerador": "cubiertos_servidos", "denominador": "horas_cocina"},
            "coordenada_y": {"senal_campo": "y_senal", "gamma_campo": "y_gamma", "gamma_default": 0.5},
        },
        "maintenance": {
            "nodo": "maintenance", "tipo": "flujo",
            "observables": ["material_comprado", "ordenes_cerradas", "concentracion_proveedor",
                            "backlog_ordenes"],
            "ancla": {"primitivo": "disonancia_vs_fisico",
                      "params": {"reportado": "material_comprado", "fisico_obs": "ordenes_cerradas",
                                 "fisico_factor": 1.0, "div": 0.25, "peso": 0.8,
                                 "sec_obs": "concentracion_proveedor", "sec_peso": 0.2}},
            "avance": {"numerador": "ordenes_cerradas", "denominador": "backlog_ordenes"},
            "coordenada_y": {"senal_campo": "y_senal", "gamma_campo": "y_gamma", "gamma_default": 0.5},
        },
    },
}

# JSON de GOBIERNO (esquema equivalente; solo cambian nodos/params/primitivos).
GOBIERNO_JSON = {
    "dominio": "gobierno",
    "nodos": {
        "agua": {
            "nodo": "agua", "tipo": "flujo",
            "observables": ["volumen_extraido_m3", "energia_kwh", "y_senal", "y_gamma"],
            "ancla": {"primitivo": "disonancia_vs_fisico",
                      "params": {"reportado": "volumen_extraido_m3", "fisico_obs": "energia_kwh",
                                 "fisico_factor": 1/0.45, "orientacion": "fisico_excede",
                                 "div": 0.20, "peso": 1.0}},
            "avance": None,
            "coordenada_y": {"senal_campo": "y_senal", "gamma_campo": "y_gamma"},
        },
        "catastro": {
            "nodo": "catastro", "tipo": "stock",
            "observables": ["valor_mercado", "ingreso_declarado", "y_senal", "y_gamma"],
            "ancla": {"primitivo": "coherencia_stock",
                      "params": {"activo": "valor_mercado", "justificacion": "ingreso_declarado",
                                 "div": 0.8, "peso": 1.0}},
            "avance": None,
            "coordenada_y": {"senal_campo": "y_senal", "gamma_campo": "y_gamma"},
        },
    },
}


# ======================================================================================
# DEMO — un solo Conector genera los tres paquetes del hotel
# ======================================================================================
def _entradas_hotel_demo() -> dict[str, dict]:
    return {
        "housekeeping": {"token": "TOK-7A3F", "timestamp_fase": 0.42,
                         "insumo_comprado": 3810.0, "habitacion_noche": 3000.0,
                         "concentracion_proveedor": 0.6, "habitaciones_atendidas": 3000.0,
                         "horas_camarista": 1300.0, "y_senal": 0.71, "y_gamma": 0.66},
        "food_beverage": {"token": "TOK-7A3F", "timestamp_fase": 0.42,
                          "insumo_comprado": 6300.0, "cubiertos_servidos": 5000.0,
                          "concentracion_proveedor": 0.55, "horas_cocina": 360.0,
                          "y_senal": 0.71, "y_gamma": 0.66},
        "maintenance": {"token": "TOK-7A3F", "timestamp_fase": 0.42,
                        "material_comprado": 260.0, "ordenes_cerradas": 200.0,
                        "concentracion_proveedor": 0.5, "backlog_ordenes": 90.0,
                        "y_senal": 0.71, "y_gamma": 0.66},
    }


def main() -> None:
    print("Primitivos disponibles:", list(PRIMITIVOS))
    conector = Conector(HOTEL_JSON)                       # mismo motor, JSON de hotel
    paquetes = conector.generar_todos(_entradas_hotel_demo())
    for nodo, paq in paquetes.items():
        print(f"\n== Paquete de Decisión Limpia -> decisor '{nodo}' ==")
        print(json.dumps(paq, ensure_ascii=False, indent=2))
    print("\nUn solo Conector, tres decisores. Cambiar a GOBIERNO_JSON no toca el motor.")


if __name__ == "__main__":
    main()
