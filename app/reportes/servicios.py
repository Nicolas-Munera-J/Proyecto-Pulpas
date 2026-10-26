"""Reportes de ventas: HU17 (ventas por periodo) y HU18 (productos más vendidos).

Reglas compartidas:
- Una VENTA es un pedido DESPACHADO. Los confirmados todavía no se han
  entregado ni cobrado, y los cancelados nunca se vendieron.
- El periodo se mide por la fecha y hora de despacho, en hora de Colombia.
- Los valores salen de precio_unitario guardado en cada línea, así que un
  cambio posterior de precios en el catálogo no altera ventas ya hechas.
"""
import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List

from sqlalchemy.orm import selectinload

from app.errores import DatosInvalidosException
from app.models import ESTADO_DESPACHADO, DetallePedido, Pedido
from app.tiempo import a_hora_negocio, rango_utc_del_negocio


@dataclass
class VentaPorFormaPago:
    forma_pago: str
    numero_pedidos: int
    total: Decimal


@dataclass
class ResumenVentas:
    desde: date
    hasta: date
    numero_pedidos: int
    total_ventas: Decimal
    por_forma_pago: List[VentaPorFormaPago]


@dataclass
class ProductoVendido:
    producto_id: int
    nombre: str
    presentacion: str
    cantidad: int
    ingresos: Decimal


def validar_periodo(desde: date, hasta: date) -> None:
    if desde is None or hasta is None:
        raise DatosInvalidosException("Indica la fecha inicial y la fecha final del periodo.")
    if desde > hasta:
        raise DatosInvalidosException("La fecha inicial no puede ser posterior a la fecha final.")


def pedidos_despachados_en_periodo(desde: date, hasta: date) -> List[Pedido]:
    """Pedidos despachados entre `desde` y `hasta`, ambos días incluidos."""
    validar_periodo(desde, hasta)
    inicio, fin = rango_utc_del_negocio(desde, hasta)
    return (
        Pedido.query.options(
            selectinload(Pedido.detalles).selectinload(DetallePedido.producto)
        )
        .filter(
            Pedido.estado == ESTADO_DESPACHADO,
            Pedido.fecha_despacho >= inicio,
            Pedido.fecha_despacho < fin,
        )
        .all()
    )


def resumen_ventas(desde: date, hasta: date) -> ResumenVentas:
    """HU17 - Total de ventas y número de pedidos de un rango de fechas,
    con el desglose por forma de pago (HU11)."""
    return _construir_resumen(desde, hasta, pedidos_despachados_en_periodo(desde, hasta))


def _construir_resumen(desde: date, hasta: date, pedidos: List[Pedido]) -> ResumenVentas:
    por_forma: Dict[str, VentaPorFormaPago] = {}
    total = Decimal("0")
    for pedido in pedidos:
        total += pedido.total
        fila = por_forma.setdefault(
            pedido.forma_pago or "sin registrar",
            VentaPorFormaPago(pedido.forma_pago or "sin registrar", 0, Decimal("0")),
        )
        fila.numero_pedidos += 1
        fila.total += pedido.total

    return ResumenVentas(
        desde=desde,
        hasta=hasta,
        numero_pedidos=len(pedidos),
        total_ventas=total,
        por_forma_pago=sorted(por_forma.values(), key=lambda f: (-f.total, f.forma_pago)),
    )


def productos_mas_vendidos(desde: date, hasta: date) -> List[ProductoVendido]:
    """HU18 - Productos ordenados de mayor a menor cantidad vendida en el
    periodo (a igual cantidad, por nombre, para que el orden sea estable)."""
    vendidos: Dict[int, ProductoVendido] = {}
    for pedido in pedidos_despachados_en_periodo(desde, hasta):
        for detalle in pedido.detalles:
            fila = vendidos.setdefault(
                detalle.producto_id,
                ProductoVendido(
                    detalle.producto_id,
                    detalle.producto.nombre,
                    detalle.producto.presentacion,
                    0,
                    Decimal("0"),
                ),
            )
            fila.cantidad += detalle.cantidad
            fila.ingresos += detalle.subtotal

    return sorted(vendidos.values(), key=lambda f: (-f.cantidad, f.nombre, f.presentacion))


# --------------------------------------------------------------------------
# HU19 - Exportar el reporte de ventas
# --------------------------------------------------------------------------
SEPARADOR_CSV = ";"  # Excel en español (Colombia) separa columnas con punto y coma
_INICIOS_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _celda_segura(valor) -> str:
    """Evita la inyección de fórmulas en Excel: si un texto escrito por una
    persona (p. ej. el nombre de un cliente) empieza por = + - @, Excel lo
    ejecutaría como fórmula al abrir el archivo. Se antepone una comilla."""
    texto = str(valor)
    return "'" + texto if texto.startswith(_INICIOS_DE_FORMULA) else texto


def _pesos(valor: Decimal) -> int:
    """Pesos enteros, igual que se muestran en pantalla (sin decimales)."""
    return int(Decimal(valor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def exportar_ventas_csv(desde: date, hasta: date) -> str:
    """HU19 - Contenido CSV del reporte de ventas (HU17) del periodo: resumen,
    desglose por forma de pago y detalle pedido por pedido.

    Va con BOM UTF-8 para que Excel muestre bien las tildes y la ñ.
    """
    pedidos = sorted(
        pedidos_despachados_en_periodo(desde, hasta), key=lambda p: (p.fecha_despacho, p.id)
    )
    resumen = _construir_resumen(desde, hasta, pedidos)

    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=SEPARADOR_CSV, lineterminator="\r\n")

    escritor.writerow(["Reporte de ventas"])
    escritor.writerow(["Desde", desde.isoformat()])
    escritor.writerow(["Hasta", hasta.isoformat()])
    escritor.writerow(["Total de ventas (COP)", _pesos(resumen.total_ventas)])
    escritor.writerow(["Pedidos despachados", resumen.numero_pedidos])
    escritor.writerow([])

    escritor.writerow(["Por forma de pago"])
    escritor.writerow(["Forma de pago", "Pedidos", "Total (COP)"])
    for fila in resumen.por_forma_pago:
        escritor.writerow([_celda_segura(fila.forma_pago), fila.numero_pedidos, _pesos(fila.total)])
    escritor.writerow([])

    escritor.writerow(["Detalle de pedidos"])
    escritor.writerow(["Pedido", "Fecha de despacho", "Cliente", "Forma de pago", "Total (COP)"])
    for pedido in pedidos:
        escritor.writerow(
            [
                pedido.id,
                a_hora_negocio(pedido.fecha_despacho).strftime("%Y-%m-%d %H:%M"),
                _celda_segura(pedido.cliente_nombre),
                _celda_segura(pedido.forma_pago or "sin registrar"),
                _pesos(pedido.total),
            ]
        )
    return "\ufeff" + salida.getvalue()
