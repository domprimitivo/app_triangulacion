"""
Cucurucho — embudo ÚNICO. De una sola ingesta de archivos de operación,
prepara EN PARALELO:
  (a) el bundle de KPIs (elemento de claridad)  → lo arma flujo_kpis (intacto).
  (b) las coordenadas LIMPIAS para el Ágora (elemento de habitabilidad) → aquí.

'Todo pasa por el cucurucho': los mismos archivos se limpian una vez (AG3) y
alimentan ambas rutas. Sin archivos → coordenadas demo del dominio (como hoy).

No reemplaza nada: los artefactos que ya generan los agentes se conservan; esto
solo AÑADE lo que el Ágora necesita.
"""
from __future__ import annotations

import json
from typing import Optional

import numpy as np

from flujo_kpis import (
    _extraer_columnas, _mapear_columnas, _categoria_de, MAIN_DIR, _sector,
)
import agora_conector as _ag


def cargar_mapa_agora(domain_id: str) -> Optional[dict]:
    """Lee el bloque `mapa_agora` del cucurucho del sector (en /app). None si no existe."""
    p = MAIN_DIR / f"cucurucho_{_sector(domain_id)}_v1.json"
    if not p.exists():
        return None
    cfg = json.loads(p.read_text(encoding="utf-8"))
    return cfg.get("mapa_agora")


def _senales_agora(archivos, categorias: dict):
    """AG3: limpia/agrega las columnas de operación del lado costo/actividad del Ágora."""
    senales: dict = {}
    for a in archivos or []:
        cat = _categoria_de(a["nombre"], categorias)
        if not cat:
            continue
        cols = _extraer_columnas(a["datos"])
        esperadas = categorias.get(cat, {}).get("columnas_esperadas", [])
        cols = _mapear_columnas(cols, esperadas)
        for canon, vals in cols.items():
            if not vals:
                continue
            senales.setdefault(cat, {})[canon] = round(float(np.mean(vals)), 4)
    return senales


def preparar_entradas(dominio_agora: str, mapa_agora: dict, archivos):
    """Base = demo del dominio Ágora; sobreescribe observables con señales reales."""
    entradas = _ag.demo_entradas(dominio_agora)
    categorias = mapa_agora.get("categorias_operacion", {})
    senales = _senales_agora(archivos, categorias)
    columnas = mapa_agora.get("columnas", {})
    aplicadas: dict = {}
    for nodo, mapcols in columnas.items():
        if nodo not in entradas:
            continue
        for obs, ref in (mapcols or {}).items():
            try:
                cat, col = str(ref).split(".", 1)
            except ValueError:
                continue
            val = senales.get(cat, {}).get(col)
            if val is not None:
                entradas[nodo][obs] = val
                aplicadas[f"{nodo}.{obs}"] = val
    return entradas, senales, aplicadas


def preparar_agora(domain_id: str, archivos, umbral: Optional[float] = None,
                   guardar: bool = True) -> Optional[dict]:
    """Prepara y triangula el Ágora del dominio desde la MISMA ingesta del cucurucho."""
    mapa_agora = cargar_mapa_agora(domain_id)
    if not mapa_agora:
        return None
    dominio_agora = mapa_agora.get("dominio_agora", _sector(domain_id))
    try:
        entradas, senales, aplicadas = preparar_entradas(dominio_agora, mapa_agora, archivos)
        origen = ("Cucurucho · embudo único (coordenadas preparadas por AG3)"
                  if archivos else "Cucurucho · embudo único (demo del dominio)")
        tri = _ag.triangular(dominio_agora, entradas, umbral,
                             origen_label=origen, guardar=guardar)
    except Exception:
        # El Ágora es ADITIVO: cualquier fallo aquí no debe comprometer el bundle de KPIs.
        return None
    tri["preparacion"] = {
        "dominio_agora": dominio_agora,
        "senales_agora": senales,
        "observables_aplicados": aplicadas,
        "n_aplicados": len(aplicadas),
    }
    return tri
