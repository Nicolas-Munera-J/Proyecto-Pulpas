from dataclasses import dataclass, field
from datetime import date
from typing import List

from app.models import CANAL_WHATSAPP


@dataclass(frozen=True)
class ItemPedidoDTO:
    producto_id: int
    cantidad: int


@dataclass
class PedidoDTO:
    """Agrupa los datos de un pedido para no pasar una lista larga de
    parámetros sueltos a registrar_pedido() (chequeo de código limpio)."""

    cliente_nombre: str
    fecha_entrega: date
    items: List[ItemPedidoDTO]
    usuario_id: int
    cliente_contacto: str = ""
    canal: str = CANAL_WHATSAPP
