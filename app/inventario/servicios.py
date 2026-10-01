from app.extensions import db
from app.models import Producto, MovimientoInventario, TIPO_ENTRADA
from app.errores import DatosInvalidosException


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
