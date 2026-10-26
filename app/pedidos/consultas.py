"""HU07 - Búsqueda y consulta del historial de pedidos."""
from dataclasses import dataclass, field
from datetime import date
from math import ceil
from typing import List, Optional

from sqlalchemy.orm import selectinload

from app.errores import DatosInvalidosException
from app.models import CANALES, ESTADOS_PEDIDO, DetallePedido, Pedido

PEDIDOS_POR_PAGINA = 20
LONGITUD_MAXIMA_BUSQUEDA = 120


@dataclass
class FiltrosHistorial:
    """Todos los filtros son opcionales; los vacíos no filtran."""

    desde: Optional[date] = None  # fecha de ENTREGA, inclusive
    hasta: Optional[date] = None
    estado: str = ""
    canal: str = ""
    cliente: str = ""


@dataclass
class PaginaPedidos:
    pedidos: List[Pedido] = field(default_factory=list)
    pagina: int = 1
    total_paginas: int = 1
    total: int = 0


def _escapar_like(texto: str) -> str:
    """Para que un % o _ escrito por el usuario se busque como texto y no
    como comodín de SQL."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validar_filtros(filtros: FiltrosHistorial) -> None:
    if filtros.desde and filtros.hasta and filtros.desde > filtros.hasta:
        raise DatosInvalidosException("La fecha inicial no puede ser posterior a la fecha final.")
    if filtros.estado and filtros.estado not in ESTADOS_PEDIDO:
        raise DatosInvalidosException("El estado indicado no es válido.")
    if filtros.canal and filtros.canal not in CANALES:
        raise DatosInvalidosException("El canal indicado no es válido.")
    if len(filtros.cliente) > LONGITUD_MAXIMA_BUSQUEDA:
        raise DatosInvalidosException(
            f"La búsqueda no puede superar {LONGITUD_MAXIMA_BUSQUEDA} caracteres."
        )


def buscar_pedidos(filtros: FiltrosHistorial, pagina: int = 1) -> PaginaPedidos:
    """HU07 - Pedidos que cumplen los filtros, del más reciente al más antiguo
    (por fecha de entrega), de a PEDIDOS_POR_PAGINA."""
    validar_filtros(filtros)

    consulta = Pedido.query
    if filtros.desde:
        consulta = consulta.filter(Pedido.fecha_entrega >= filtros.desde)
    if filtros.hasta:
        consulta = consulta.filter(Pedido.fecha_entrega <= filtros.hasta)
    if filtros.estado:
        consulta = consulta.filter(Pedido.estado == filtros.estado)
    if filtros.canal:
        consulta = consulta.filter(Pedido.canal == filtros.canal)
    texto = filtros.cliente.strip()
    if texto:
        consulta = consulta.filter(
            Pedido.cliente_nombre.ilike(f"%{_escapar_like(texto)}%", escape="\\")
        )

    total = consulta.count()
    total_paginas = max(1, ceil(total / PEDIDOS_POR_PAGINA))
    pagina = min(max(1, pagina), total_paginas)

    pedidos = (
        consulta.options(selectinload(Pedido.detalles).selectinload(DetallePedido.producto))
        .order_by(Pedido.fecha_entrega.desc(), Pedido.id.desc())
        .limit(PEDIDOS_POR_PAGINA)
        .offset((pagina - 1) * PEDIDOS_POR_PAGINA)
        .all()
    )
    return PaginaPedidos(pedidos=pedidos, pagina=pagina, total_paginas=total_paginas, total=total)
