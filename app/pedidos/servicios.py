"""Lógica de negocio de pedidos: HU02, HU09, HU01 (Sprint 2) y HU03, HU05, HU06 (Sprint 3).

Cada función hace una sola cosa. En particular verificar_inventario_disponible()
solo CONSULTA; quien compromete las existencias es registrar_pedido(), a
través de comprometer_existencias() del módulo de inventario (sin efectos colaterales ocultos).
"""
from datetime import timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy import update
from sqlalchemy.orm import selectinload

from app.errores import (
    DatosInvalidosException,
    InventarioInsuficienteException,
    PedidoPosiblementeDuplicadoException,
    TransicionDePedidoInvalidaException,
)
from app.extensions import db
from app.inventario.servicios import (
    ajustar_compromiso,
    comprometer_existencias,
    consumir_existencia_comprometida,
    liberar_existencia_comprometida,
)
from app.models import (
    CANALES,
    ESTADO_CANCELADO,
    ESTADO_CONFIRMADO,
    ESTADO_DESPACHADO,
    DetallePedido,
    Pedido,
    Producto,
)
from app.pedidos.dtos import ItemPedidoDTO, PedidoDTO
from app.tiempo import ahora_utc, hoy_negocio

# HU09 - Heurística de "proximidad horaria" (pendiente de validar con el cliente):
# un pedido es posible duplicado si el mismo cliente, con el mismo conjunto de
# productos, ya tiene un pedido NO cancelado registrado dentro de esta ventana.
VENTANA_DUPLICADO_MINUTOS = 30

LONGITUD_MAXIMA_CLIENTE = 120
LONGITUD_MAXIMA_CONTACTO = 80


# --------------------------------------------------------------------------
# Validación y preparación de datos
# --------------------------------------------------------------------------
def validar_datos_pedido(pedido: PedidoDTO, fecha_original=None) -> None:
    """HU02/HU03 - Valida campos obligatorios y cantidades mayores que cero.

    Se ejecuta en el servidor: el formulario del navegador no es suficiente.
    `fecha_original` se usa al editar: si la fecha de entrega no cambió, no se
    rechaza aunque ya haya pasado (un pedido atrasado sigue siendo editable).
    """
    nombre = (pedido.cliente_nombre or "").strip()
    if not nombre:
        raise DatosInvalidosException("El nombre del cliente es obligatorio.")
    if len(nombre) > LONGITUD_MAXIMA_CLIENTE:
        raise DatosInvalidosException(
            f"El nombre del cliente no puede superar {LONGITUD_MAXIMA_CLIENTE} caracteres."
        )
    if len((pedido.cliente_contacto or "").strip()) > LONGITUD_MAXIMA_CONTACTO:
        raise DatosInvalidosException(
            f"El contacto no puede superar {LONGITUD_MAXIMA_CONTACTO} caracteres."
        )
    if pedido.canal not in CANALES:
        raise DatosInvalidosException("El canal del pedido no es válido.")
    if pedido.fecha_entrega is None:
        raise DatosInvalidosException("La fecha de entrega es obligatoria.")
    if pedido.fecha_entrega != fecha_original and pedido.fecha_entrega < hoy_negocio():
        raise DatosInvalidosException("La fecha de entrega no puede estar en el pasado.")
    if not pedido.items:
        raise DatosInvalidosException("El pedido debe incluir al menos un producto.")
    for item in pedido.items:
        if item.cantidad is None or item.cantidad <= 0:
            raise DatosInvalidosException("Todas las cantidades deben ser mayores que cero.")


def agrupar_cantidades_por_producto(items: Iterable[ItemPedidoDTO]) -> Dict[int, int]:
    """Suma las líneas repetidas del mismo producto.

    Sin esto, dos líneas de 6 unidades de un producto con 10 disponibles
    pasarían la verificación una por una y comprometerían 12.
    """
    cantidades: Dict[int, int] = {}
    for item in items:
        cantidades[item.producto_id] = cantidades.get(item.producto_id, 0) + item.cantidad
    return cantidades


def _normalizar_nombre(nombre: str) -> str:
    return " ".join(nombre.split()).casefold()


# --------------------------------------------------------------------------
# Inventario (solo consulta)
# --------------------------------------------------------------------------
def verificar_inventario_disponible(
    cantidades: Dict[int, int], adicional: bool = False
) -> Dict[int, Producto]:
    """HU02/HU03 - Consulta si hay existencia disponible para cada producto.

    Solo consulta: no descuenta ni compromete nada. Devuelve los productos
    por id para que el llamador no tenga que volver a buscarlos. Con
    `adicional=True` las cantidades son unidades EXTRA (edición de un pedido)
    y el mensaje lo dice así.
    """
    productos = {
        p.id: p for p in Producto.query.filter(Producto.id.in_(list(cantidades))).all()
    }
    faltantes: List[dict] = []

    for producto_id, solicitada in cantidades.items():
        producto = productos.get(producto_id)
        if producto is None or not producto.activo:
            raise DatosInvalidosException(
                "Uno de los productos seleccionados no existe o está inactivo."
            )
        if producto.existencia_disponible < solicitada:
            faltantes.append(
                {
                    "producto": f"{producto.nombre} ({producto.presentacion})",
                    "solicitada": solicitada,
                    "disponible": producto.existencia_disponible,
                }
            )

    if faltantes:
        detalle = "; ".join(
            (
                f"{f['producto']}: necesitas {f['solicitada']} más, disponible {f['disponible']}"
                if adicional
                else f"{f['producto']}: pediste {f['solicitada']}, disponible {f['disponible']}"
            )
            for f in faltantes
        )
        raise InventarioInsuficienteException(
            f"No hay inventario suficiente. {detalle}.", faltantes
        )
    return productos


# --------------------------------------------------------------------------
# HU09 - Pedido posiblemente duplicado
# --------------------------------------------------------------------------
def detectar_pedido_duplicado(pedido: PedidoDTO) -> Optional[Pedido]:
    """Devuelve el pedido reciente que se parece al nuevo, o None.

    Criterio: mismo cliente + mismo conjunto de productos + registrado dentro
    de VENTANA_DUPLICADO_MINUTOS + que no esté cancelado. Las cantidades no
    se comparan a propósito: la alerta es solo una advertencia, y es mejor
    avisar de más que dejar pasar un pedido repetido.
    """
    limite = ahora_utc() - timedelta(minutes=VENTANA_DUPLICADO_MINUTOS)
    nombre = _normalizar_nombre(pedido.cliente_nombre)
    productos_nuevos = {item.producto_id for item in pedido.items}

    recientes = (
        Pedido.query.options(selectinload(Pedido.detalles))
        .filter(Pedido.estado != ESTADO_CANCELADO, Pedido.fecha_creacion >= limite)
        .order_by(Pedido.fecha_creacion.desc())
        .all()
    )
    for existente in recientes:
        if _normalizar_nombre(existente.cliente_nombre) != nombre:
            continue
        if {d.producto_id for d in existente.detalles} == productos_nuevos:
            return existente
    return None


# --------------------------------------------------------------------------
# HU02 - Registro de pedido
# --------------------------------------------------------------------------
def registrar_pedido(pedido: PedidoDTO, confirmar_duplicado: bool = False) -> Pedido:
    """HU02 - Registra un pedido solo si hay inventario suficiente.

    Si hay existencias, el pedido queda directamente CONFIRMADO y las unidades
    quedan comprometidas. Si no alcanzan, se lanza InventarioInsuficienteException
    y no se guarda nada: no existe un estado intermedio de espera (decisión de
    negocio, sección 6.1 del documento).

    HU09: si parece duplicado y el gestor aún no lo confirmó, se lanza
    PedidoPosiblementeDuplicadoException antes de tocar el inventario.
    """
    validar_datos_pedido(pedido)
    cantidades = agrupar_cantidades_por_producto(pedido.items)

    if not confirmar_duplicado:
        existente = detectar_pedido_duplicado(pedido)
        if existente is not None:
            raise PedidoPosiblementeDuplicadoException(
                f"Ya hay un pedido reciente de {existente.cliente_nombre} con los mismos productos.",
                existente,
            )

    productos = verificar_inventario_disponible(cantidades)

    nuevo = Pedido(
        cliente_nombre=" ".join(pedido.cliente_nombre.split()),
        cliente_contacto=(pedido.cliente_contacto or "").strip() or None,
        canal=pedido.canal,
        estado=ESTADO_CONFIRMADO,
        fecha_entrega=pedido.fecha_entrega,
        usuario_id=pedido.usuario_id,
    )
    for producto_id, cantidad in cantidades.items():
        nuevo.detalles.append(
            DetallePedido(
                producto_id=producto_id,
                cantidad=cantidad,
                precio_unitario=productos[producto_id].precio,
            )
        )

    try:
        db.session.add(nuevo)
        comprometer_existencias(cantidades)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return nuevo


# --------------------------------------------------------------------------
# HU01 - Pedidos del día
# --------------------------------------------------------------------------
def listar_pedidos_del_dia(fecha=None) -> List[Pedido]:
    """HU01 - Pedidos confirmados cuya fecha de entrega es la del día.

    Carga detalles y productos de una vez (selectinload) para evitar una
    consulta por pedido y cumplir RNF01 (carga en menos de 3 segundos).
    """
    fecha = fecha or hoy_negocio()
    return (
        Pedido.query.options(
            selectinload(Pedido.detalles).selectinload(DetallePedido.producto)
        )
        .filter(Pedido.estado == ESTADO_CONFIRMADO, Pedido.fecha_entrega == fecha)
        .order_by(Pedido.fecha_creacion)
        .all()
    )


# --------------------------------------------------------------------------
# Ciclo del pedido (sección 6.2): confirmado -> despachado | cancelado
# --------------------------------------------------------------------------
def cantidades_del_pedido(pedido: Pedido) -> Dict[int, int]:
    """Unidades por producto que tiene un pedido."""
    return agrupar_cantidades_por_producto(
        ItemPedidoDTO(d.producto_id, d.cantidad) for d in pedido.detalles
    )


def _obtener_pedido_confirmado(pedido_id: int, accion: str) -> Pedido:
    """Devuelve el pedido solo si sigue confirmado. Un pedido despachado o
    cancelado no admite más acciones (sección 6.2 del documento)."""
    pedido = db.session.get(Pedido, pedido_id)
    if pedido is None:
        raise DatosInvalidosException("El pedido indicado no existe.")
    if pedido.estado != ESTADO_CONFIRMADO:
        raise TransicionDePedidoInvalidaException(
            f"No se puede {accion} el pedido #{pedido.id}: ya está {pedido.estado}."
        )
    return pedido


def _cambiar_estado_desde_confirmado(pedido_id: int, nuevo_estado: str, **campos) -> None:
    """Cambia el estado solo si el pedido SIGUE confirmado en la base de datos.

    El UPDATE condicional evita que dos clics simultáneos (o dos usuarios)
    despachen o cancelen dos veces el mismo pedido y muevan el inventario
    por duplicado.
    """
    resultado = db.session.execute(
        update(Pedido)
        .where(Pedido.id == pedido_id, Pedido.estado == ESTADO_CONFIRMADO)
        .values(estado=nuevo_estado, **campos)
    )
    if resultado.rowcount == 0:
        raise TransicionDePedidoInvalidaException(
            f"El pedido #{pedido_id} ya no está confirmado; actualiza la página."
        )


# ---- HU03 - Edición antes del despacho -----------------------------------
def editar_pedido(pedido_id: int, datos: PedidoDTO) -> Pedido:
    """HU03 - Modifica un pedido confirmado y aún no despachado.

    El inventario se ajusta por DIFERENCIA entre lo que el pedido ya tiene
    comprometido y el nuevo total: solo se exige disponibilidad para las
    unidades adicionales (las que ya estaban reservadas no se cuentan dos
    veces). Si no alcanza, no cambia nada.
    """
    pedido = _obtener_pedido_confirmado(pedido_id, "editar")
    validar_datos_pedido(datos, fecha_original=pedido.fecha_entrega)

    nuevas = agrupar_cantidades_por_producto(datos.items)
    actuales = cantidades_del_pedido(pedido)
    diferencias = {
        producto_id: nuevas.get(producto_id, 0) - actuales.get(producto_id, 0)
        for producto_id in set(nuevas) | set(actuales)
    }
    diferencias = {p: d for p, d in diferencias.items() if d != 0}

    adicionales = {p: d for p, d in diferencias.items() if d > 0}
    productos = (
        verificar_inventario_disponible(adicionales, adicional=True) if adicionales else {}
    )

    pedido.cliente_nombre = " ".join(datos.cliente_nombre.split())
    pedido.cliente_contacto = (datos.cliente_contacto or "").strip() or None
    pedido.canal = datos.canal
    pedido.fecha_entrega = datos.fecha_entrega

    for detalle in list(pedido.detalles):
        if detalle.producto_id in nuevas:
            detalle.cantidad = nuevas[detalle.producto_id]  # conserva su precio original
        else:
            pedido.detalles.remove(detalle)
    for producto_id, cantidad in nuevas.items():
        if producto_id not in actuales:
            pedido.detalles.append(
                DetallePedido(
                    producto_id=producto_id,
                    cantidad=cantidad,
                    precio_unitario=productos[producto_id].precio,
                )
            )

    try:
        ajustar_compromiso(diferencias)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return pedido


# ---- HU05 - Despacho -------------------------------------------------------
def despachar_pedido(pedido_id: int) -> Pedido:
    """HU05 - Pasa un pedido confirmado a despachado y registra fecha y hora.

    Las unidades salen físicamente del negocio, así que dejan de estar
    comprometidas (la existencia disponible no cambia: ya estaba descontada).
    """
    pedido = _obtener_pedido_confirmado(pedido_id, "despachar")
    cantidades = cantidades_del_pedido(pedido)

    try:
        _cambiar_estado_desde_confirmado(
            pedido.id, ESTADO_DESPACHADO, fecha_despacho=ahora_utc()
        )
        consumir_existencia_comprometida(cantidades)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return pedido


# ---- HU06 - Cancelación ----------------------------------------------------
def cancelar_pedido(pedido_id: int) -> Pedido:
    """HU06 - Pasa un pedido confirmado a cancelado y libera sus existencias
    comprometidas para que vuelvan a estar disponibles."""
    pedido = _obtener_pedido_confirmado(pedido_id, "cancelar")
    cantidades = cantidades_del_pedido(pedido)

    try:
        _cambiar_estado_desde_confirmado(pedido.id, ESTADO_CANCELADO)
        liberar_existencia_comprometida(cantidades)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return pedido
