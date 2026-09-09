"""
Programador del Ajuste Bimestral
================================
Ejecuta automáticamente el ajuste bimestral (port del notebook) cada 50 días
contados desde la ACTIVACIÓN del cliente (campo `emitido_en` del activador).

Usa APScheduler en un hilo de fondo dentro del propio backend (sin dependencias
externas). Revisa periódicamente si ya transcurrió un nuevo período de 50 días
que aún no se ha ejecutado, y si es así dispara el ajuste. El diseño soporta
"catch-up": si el proceso estuvo apagado y se saltaron períodos, ejecuta el
período pendiente más reciente al arrancar.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

PERIODO_DIAS = 50
INTERVALO_CHEQUEO_HORAS = 6


def periodo_actual(base: datetime, ahora: Optional[datetime] = None) -> int:
    """Número de períodos completos de 50 días transcurridos desde la activación."""
    ahora = ahora or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    dias = (ahora - base).days
    if dias < 0:
        return 0
    return dias // PERIODO_DIAS


def ventana_periodo(base: datetime, indice: int):
    """Ventana [inicio, fin] de datos correspondiente al período `indice`."""
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    fin = base + timedelta(days=PERIODO_DIAS * indice)
    inicio = base + timedelta(days=PERIODO_DIAS * (indice - 1))
    return inicio, fin


def fecha_proximo_ajuste(base: datetime, ultimo_indice_ejecutado: int,
                         ahora: Optional[datetime] = None) -> datetime:
    """Fecha del próximo ajuste programado."""
    ahora = ahora or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    proximo_indice = max(ultimo_indice_ejecutado, periodo_actual(base, ahora)) + 1
    # Si ya hay un período vencido sin ejecutar, el próximo es ese
    pendiente = periodo_actual(base, ahora)
    if pendiente > ultimo_indice_ejecutado:
        proximo_indice = pendiente
    return base + timedelta(days=PERIODO_DIAS * proximo_indice)


class ProgramadorBimestral:
    def __init__(self,
                 obtener_base: Callable[[], Optional[datetime]],
                 obtener_dominio: Callable[[], Optional[str]],
                 ultimo_indice: Callable[[str], int],
                 ejecutar: Callable[..., dict]):
        self.obtener_base = obtener_base
        self.obtener_dominio = obtener_dominio
        self.ultimo_indice = ultimo_indice
        self.ejecutar = ejecutar
        self._scheduler: Optional[BackgroundScheduler] = None

    def _tick(self):
        try:
            base = self.obtener_base()
            dominio = self.obtener_dominio()
            if not base or not dominio:
                return
            indice = periodo_actual(base)
            if indice < 1:
                return
            if indice <= self.ultimo_indice(dominio):
                return  # el período vigente ya fue ejecutado
            inicio, fin = ventana_periodo(base, indice)
            logger.info(f"[SCHEDULER] Disparando ajuste bimestral · dominio={dominio} "
                        f"período={indice} ventana={inicio.date()}..{fin.date()}")
            self.ejecutar(dominio=dominio, period_index=indice,
                          window_start=inicio, window_end=fin,
                          disparado_por="scheduler")
        except Exception as e:
            logger.error(f"[SCHEDULER] Error en tick del ajuste bimestral: {e}")

    def start(self):
        if self._scheduler is not None:
            return
        self._scheduler = BackgroundScheduler(timezone="UTC")
        # Primer chequeo poco después del arranque (catch-up) y luego cada 6h.
        self._scheduler.add_job(
            self._tick, "interval", hours=INTERVALO_CHEQUEO_HORAS,
            id="ajuste_bimestral", replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=20),
            max_instances=1, coalesce=True,
        )
        self._scheduler.start()
        logger.info(f"[SCHEDULER] Programador bimestral iniciado "
                    f"(cada {PERIODO_DIAS} días desde la activación, "
                    f"chequeo cada {INTERVALO_CHEQUEO_HORAS}h).")

    def shutdown(self):
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
