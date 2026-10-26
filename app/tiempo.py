"""Manejo de fechas del negocio.

El negocio opera en hora de Colombia, pero el servidor (y el pipeline de CI)
suelen correr en UTC. Si se usara date.today() a secas, después de las 7 p. m.
en Bogotá el "día actual" del servidor ya sería el de mañana y los pedidos del
día (HU01) aparecerían vacíos. Por eso todo "hoy" sale de hoy_negocio().
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ZONA_HORARIA_NEGOCIO = ZoneInfo("America/Bogota")


def ahora_utc() -> datetime:
    """Momento actual en UTC, sin zona (como se guardan las fechas en la BD)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hoy_negocio() -> date:
    """Fecha de hoy según la hora de Colombia."""
    return datetime.now(ZONA_HORARIA_NEGOCIO).date()


def a_hora_negocio(momento_utc: datetime) -> datetime:
    """Convierte una fecha guardada en UTC a la hora local del negocio."""
    return momento_utc.replace(tzinfo=timezone.utc).astimezone(ZONA_HORARIA_NEGOCIO)


def rango_utc_del_negocio(desde: date, hasta: date):
    """Convierte un periodo de fechas LOCALES (inclusive) al intervalo UTC
    [inicio, fin) con que se guardan las fechas en la base de datos.

    Un pedido despachado a las 11:30 p. m. en Bogotá ya es del día siguiente
    en UTC; sin esta conversión las ventas de esa noche caerían en el día
    equivocado de los reportes (HU17/HU18).
    """
    inicio_local = datetime.combine(desde, time.min, tzinfo=ZONA_HORARIA_NEGOCIO)
    fin_local = datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=ZONA_HORARIA_NEGOCIO)
    a_utc = lambda momento: momento.astimezone(timezone.utc).replace(tzinfo=None)
    return a_utc(inicio_local), a_utc(fin_local)
