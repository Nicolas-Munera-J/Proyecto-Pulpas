from typing import Dict, List

from sqlalchemy import func, select, update

from app.extensions import db
from app.models import (
    ESTADO_CONFIRMADO,
    DetallePedido,
    MOTIVOS_MERMA,
    MovimientoInventario,
    Pedido,
    Producto,
    TIPO_ENTRADA,
    TIPO_MERMA,
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
# HU15 - Alerta de existencias bajas
# --------------------------------------------------------------------------
def listar_stock_bajo() -> List[Producto]:
    """HU15 - Productos activos cuya existencia disponible llegó al umbral
    mínimo o está por debajo (Producto.stock_bajo)."""
    return [p for p in listar_existencias() if p.stock_bajo]


def describir_stock_bajo(producto_ids) -> List[str]:
    """HU15 - Texto de alerta para los productos de `producto_ids` que están
    en stock bajo. Se usa justo después de tomar un pedido o registrar una
    merma, que son los momentos en que baja la existencia disponible."""
    if not producto_ids:
        return []
    productos = (
        Producto.query.filter(Producto.id.in_(list(producto_ids)), Producto.activo.is_(True))
        .order_by(Producto.nombre)
        .all()
    )
    return [
        f"{p.nombre} ({p.presentacion}): quedan {p.existencia_disponible}, umbral {p.umbral_minimo}"
        for p in productos
        if p.stock_bajo
    ]


# --------------------------------------------------------------------------
# HU16 - Mermas o pérdidas de inventario
# --------------------------------------------------------------------------
def registrar_merma(producto_id: int, cantidad: int, motivo: str, usuario_id: int,
                    observacion: str = "") -> MovimientoInventario:
    """HU16 - Registra una pérdida por daño o vencimiento y la descuenta de
    la existencia DISPONIBLE.

    Solo se pueden descartar unidades disponibles: las comprometidas ya
    pertenecen a un pedido confirmado (si se perdieron, hay que editar o
    cancelar ese pedido primero). El UPDATE es condicional para que dos mermas
    simultáneas no dejen la existencia en negativo.
    """
    if motivo not in MOTIVOS_MERMA:
        raise DatosInvalidosException("Selecciona el motivo de la merma: daño o vencimiento.")
    if cantidad is None or cantidad <= 0:
        raise DatosInvalidosException("La cantidad de la merma debe ser mayor que cero.")
    observacion = (observacion or "").strip()
    if len(observacion) > 255:
        raise DatosInvalidosException("La observación no puede superar 255 caracteres.")

    producto = db.session.get(Producto, producto_id)
    if producto is None:
        raise DatosInvalidosException("El producto indicado no existe.")

    try:
        resultado = db.session.execute(
            update(Producto)
            .where(Producto.id == producto_id, Producto.existencia_disponible >= cantidad)
            .values(existencia_disponible=Producto.existencia_disponible - cantidad)
        )
        if resultado.rowcount == 0:
            raise InventarioInsuficienteException(
                f"No se puede registrar la merma: de {producto.nombre} ({producto.presentacion}) "
                f"solo hay {producto.existencia_disponible} unidades disponibles. Las unidades "
                "comprometidas por pedidos confirmados no se pueden descartar; edita o cancela "
                "el pedido primero."
            )
        movimiento = MovimientoInventario(
            producto_id=producto_id,
            tipo=TIPO_MERMA,
            cantidad=cantidad,
            motivo=motivo,
            observacion=observacion or None,
            usuario_id=usuario_id,
        )
        db.session.add(movimiento)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return movimiento


def listar_mermas(limite: int = 20) -> List[MovimientoInventario]:
    """Las mermas más recientes, para mostrarlas junto al formulario."""
    return (
        MovimientoInventario.query.filter_by(tipo=TIPO_MERMA)
        .order_by(MovimientoInventario.fecha.desc(), MovimientoInventario.id.desc())
        .limit(limite)
        .all()
    )


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
