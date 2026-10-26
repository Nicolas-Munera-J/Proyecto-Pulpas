from typing import Dict, List

from sqlalchemy import func, select, update

from app.extensions import db
from app.models import (
    ESTADO_CONFIRMADO,
    DetallePedido,
    MovimientoInventario,
    Pedido,
    Producto,
    TIPO_ENTRADA,
)
from app.errores import DatosInvalidosException, InventarioInsuficienteException


def registrar_entrada_inventario(producto_id: int, cantidad: int, usuario_id: int,
                                  observacion: str = "") -> MovimientoInventario:
    """HU08 - Permite al administrador registrar producto/insumo, cantidad y
    fecha para incrementar existencias.

    verificarInventarioDisponible() / registrarPedido() se mantienen como
    funciones separadas en el módulo de pedidos (Sprint 2); esta función
    solo hace una cosa: registrar una entrada y sumarla a la existencia
    disponible del producto.
    """
    if cantidad is None or cantidad <= 0:
        raise DatosInvalidosException("La cantidad debe ser mayor que cero.")

    producto = Producto.query.get(producto_id)
    if producto is None:
        raise DatosInvalidosException("El producto indicado no existe.")

    movimiento = MovimientoInventario(
        producto_id=producto.id,
        tipo=TIPO_ENTRADA,
        cantidad=cantidad,
        observacion=observacion,
        usuario_id=usuario_id,
    )
    producto.existencia_disponible += cantidad

    db.session.add(movimiento)
    db.session.commit()
    return movimiento


def listar_existencias():
    """HU14 - Muestra existencias disponibles y permite identificar
    existencias bajas (el cálculo de stock_bajo vive en el modelo Producto)."""
    return Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()


# --------------------------------------------------------------------------
# HU04 - Existencias comprometidas
#
# Reglas (sección 6.3 del documento):
#   existencia física = disponible + comprometida
#   confirmar/aumentar un pedido -> disponible baja, comprometida sube
#   cancelar/reducir un pedido   -> comprometida baja, disponible sube
#   despachar un pedido          -> comprometida baja (la fruta sale del
#                                   negocio), disponible no cambia
# Todas las funciones usan UPDATE condicional: nunca dejan una existencia
# negativa, ni siquiera con dos operaciones simultáneas (R-006, RNF06).
# No hacen commit: el que las llama decide cuándo confirmar la transacción,
# para que pedido e inventario se guarden juntos o no se guarden.
# --------------------------------------------------------------------------
def comprometer_existencias(cantidades: Dict[int, int]) -> None:
    """Pasa unidades de 'disponible' a 'comprometida'."""
    for producto_id, cantidad in cantidades.items():
        resultado = db.session.execute(
            update(Producto)
            .where(
                Producto.id == producto_id,
                Producto.existencia_disponible >= cantidad,
            )
            .values(
                existencia_disponible=Producto.existencia_disponible - cantidad,
                existencia_comprometida=Producto.existencia_comprometida + cantidad,
            )
        )
        if resultado.rowcount == 0:
            raise InventarioInsuficienteException(
                "El inventario cambió mientras se guardaba el pedido. Intenta de nuevo."
            )


def liberar_existencia_comprometida(cantidades: Dict[int, int]) -> None:
    """Devuelve unidades de 'comprometida' a 'disponible' (cancelación o
    reducción de un pedido)."""
    for producto_id, cantidad in cantidades.items():
        resultado = db.session.execute(
            update(Producto)
            .where(
                Producto.id == producto_id,
                Producto.existencia_comprometida >= cantidad,
            )
            .values(
                existencia_comprometida=Producto.existencia_comprometida - cantidad,
                existencia_disponible=Producto.existencia_disponible + cantidad,
            )
        )
        if resultado.rowcount == 0:
            raise InventarioInsuficienteException(
                "No hay suficientes unidades comprometidas para liberar. "
                "Revisa la coherencia del inventario."
            )


def consumir_existencia_comprometida(cantidades: Dict[int, int]) -> None:
    """Descuenta unidades comprometidas porque el pedido se despachó: la
    pulpa sale físicamente del inventario."""
    for producto_id, cantidad in cantidades.items():
        resultado = db.session.execute(
            update(Producto)
            .where(
                Producto.id == producto_id,
                Producto.existencia_comprometida >= cantidad,
            )
            .values(existencia_comprometida=Producto.existencia_comprometida - cantidad)
        )
        if resultado.rowcount == 0:
            raise InventarioInsuficienteException(
                "No hay suficientes unidades comprometidas para despachar. "
                "Revisa la coherencia del inventario."
            )


def ajustar_compromiso(diferencias: Dict[int, int]) -> None:
    """Aplica el cambio neto de una edición de pedido: una diferencia
    positiva compromete más unidades; una negativa libera."""
    aumentos = {p: d for p, d in diferencias.items() if d > 0}
    reducciones = {p: -d for p, d in diferencias.items() if d < 0}
    liberar_existencia_comprometida(reducciones)
    comprometer_existencias(aumentos)


def calcular_comprometido_esperado() -> Dict[int, int]:
    """Unidades que DEBERÍAN estar comprometidas por producto: la suma de las
    líneas de los pedidos confirmados (los despachados y cancelados ya no
    comprometen nada)."""
    filas = db.session.execute(
        select(DetallePedido.producto_id, func.sum(DetallePedido.cantidad))
        .join(Pedido, Pedido.id == DetallePedido.pedido_id)
        .where(Pedido.estado == ESTADO_CONFIRMADO)
        .group_by(DetallePedido.producto_id)
    ).all()
    return {producto_id: int(total) for producto_id, total in filas}


def verificar_coherencia_inventario() -> List[dict]:
    """HU04 - Compara lo comprometido en la tabla de productos con lo que
    suman los pedidos confirmados. Devuelve las diferencias (lista vacía si
    todo es coherente). Mitiga R-006 y sirve de red de seguridad en las
    pruebas de integración entre pedidos e inventario."""
    esperado = calcular_comprometido_esperado()
    diferencias = []
    for producto in Producto.query.all():
        deberia = esperado.get(producto.id, 0)
        if producto.existencia_comprometida != deberia:
            diferencias.append(
                {
                    "producto_id": producto.id,
                    "producto": producto.nombre,
                    "comprometida": producto.existencia_comprometida,
                    "esperada": deberia,
                }
            )
    return diferencias
