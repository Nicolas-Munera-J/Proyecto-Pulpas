from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.errores import (
    DatosInvalidosException,
    ErrorDeNegocio,
    PedidoPosiblementeDuplicadoException,
    TransicionDePedidoInvalidaException,
)
from app.extensions import db
from app.inventario.servicios import describir_stock_bajo
from app.models import (
    CANAL_WHATSAPP,
    CANALES,
    ESTADO_CONFIRMADO,
    ESTADOS_PEDIDO,
    FORMAS_PAGO,
    Pedido,
    Producto,
)
from app.pedidos.consultas import FiltrosHistorial, buscar_pedidos
from app.pedidos.dtos import ItemPedidoDTO, PedidoDTO
from app.pedidos.servicios import (
    cancelar_pedido,
    cantidades_del_pedido,
    despachar_pedido,
    editar_pedido,
    listar_pedidos_del_dia,
    registrar_pedido,
)
from app.tiempo import a_hora_negocio, hoy_negocio

pedidos_bp = Blueprint("pedidos", __name__, template_folder="../templates/pedidos")


def _valores_iniciales() -> dict:
    return {
        "cliente_nombre": "",
        "cliente_contacto": "",
        "canal": CANAL_WHATSAPP,
        "fecha_entrega": hoy_negocio().isoformat(),
        "lineas": [{"producto_id": "", "cantidad": ""}],
    }


def _leer_valores(form) -> dict:
    """Conserva lo que escribió el gestor para no obligarlo a digitar todo
    de nuevo cuando hay un error o una alerta de duplicado."""
    lineas = [
        {"producto_id": producto_id, "cantidad": cantidad}
        for producto_id, cantidad in zip(form.getlist("producto_id"), form.getlist("cantidad"))
        if producto_id or cantidad.strip()
    ]
    return {
        "cliente_nombre": form.get("cliente_nombre", ""),
        "cliente_contacto": form.get("cliente_contacto", ""),
        "canal": form.get("canal", CANAL_WHATSAPP),
        "fecha_entrega": form.get("fecha_entrega", ""),
        "lineas": lineas or [{"producto_id": "", "cantidad": ""}],
    }


def _construir_dto(valores: dict) -> PedidoDTO:
    try:
        fecha_entrega = date.fromisoformat(valores["fecha_entrega"])
    except ValueError:
        raise DatosInvalidosException("La fecha de entrega no es válida.")

    try:
        items = [
            ItemPedidoDTO(producto_id=int(linea["producto_id"]), cantidad=int(linea["cantidad"]))
            for linea in valores["lineas"]
            if linea["producto_id"] or linea["cantidad"].strip()
        ]
    except ValueError:
        raise DatosInvalidosException(
            "Cada línea debe tener un producto y una cantidad numérica."
        )

    return PedidoDTO(
        cliente_nombre=valores["cliente_nombre"],
        cliente_contacto=valores["cliente_contacto"],
        canal=valores["canal"],
        fecha_entrega=fecha_entrega,
        items=items,
        usuario_id=current_user.id,
    )


def _valores_desde_pedido(pedido: Pedido) -> dict:
    return {
        "cliente_nombre": pedido.cliente_nombre,
        "cliente_contacto": pedido.cliente_contacto or "",
        "canal": pedido.canal,
        "fecha_entrega": pedido.fecha_entrega.isoformat(),
        "lineas": [
            {"producto_id": str(d.producto_id), "cantidad": str(d.cantidad)}
            for d in pedido.detalles
        ],
    }


def _con_alerta_de_stock(mensaje: str, pedido: Pedido):
    """HU15 - Si al tomar o editar el pedido algún producto quedó en stock
    bajo, la alerta va en el MISMO aviso (varios avisos seguidos se pisarían
    entre sí en pantalla)."""
    alertas = describir_stock_bajo({d.producto_id for d in pedido.detalles})
    if not alertas:
        return mensaje, "success"
    return mensaje + " Atención, existencia baja: " + "; ".join(alertas) + ".", "warning"


def _mostrar_formulario(valores: dict, duplicado=None, pedido=None):
    """Formulario compartido por "nuevo pedido" (pedido=None) y "editar"."""
    consulta = Producto.query
    reservado = {}
    precios_del_pedido = {}
    fecha_minima = hoy_negocio()
    if pedido is not None:
        # En edición, un producto del pedido que luego se desactivó debe seguir
        # apareciendo, o el formulario no podría guardarse.
        reservado = cantidades_del_pedido(pedido)
        # Las líneas que ya tiene el pedido conservan su precio original (HU10).
        precios_del_pedido = {d.producto_id: d.precio_unitario for d in pedido.detalles}
        consulta = consulta.filter(
            or_(Producto.activo.is_(True), Producto.id.in_(list(reservado)))
        )
        fecha_minima = min(fecha_minima, pedido.fecha_entrega)
    else:
        consulta = consulta.filter_by(activo=True)

    return render_template(
        "pedidos/nuevo.html",
        productos=consulta.order_by(Producto.nombre).all(),
        valores=valores,
        canales=CANALES,
        hoy=fecha_minima.isoformat(),
        duplicado=duplicado,
        pedido=pedido,
        reservado=reservado,
        precios_del_pedido=precios_del_pedido,
    )


@pedidos_bp.route("/pedidos/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    """HU02 - Registro de pedido con verificación inmediata de inventario.
    HU09 - Alerta de posible pedido duplicado."""
    if request.method == "GET":
        return _mostrar_formulario(_valores_iniciales())

    valores = _leer_valores(request.form)
    confirmar_duplicado = request.form.get("confirmar_duplicado") == "1"

    try:
        pedido = registrar_pedido(_construir_dto(valores), confirmar_duplicado)
    except PedidoPosiblementeDuplicadoException as alerta:
        existente = alerta.pedido_existente
        duplicado = {
            "cliente": existente.cliente_nombre,
            "registrado": a_hora_negocio(existente.fecha_creacion).strftime("%H:%M"),
            "productos": [f"{d.cantidad} x {d.producto.nombre}" for d in existente.detalles],
        }
        return _mostrar_formulario(valores, duplicado)
    except ErrorDeNegocio as error:
        flash(str(error), "error")
        return _mostrar_formulario(valores)

    mensaje, categoria = _con_alerta_de_stock(
        f"Pedido #{pedido.id} de {pedido.cliente_nombre} registrado y confirmado.", pedido
    )
    flash(mensaje, categoria)
    return redirect(url_for("pedidos.nuevo"))


@pedidos_bp.route("/pedidos/hoy")
@login_required
def hoy():
    """HU01 - Consulta de pedidos del día. Con ?fecha=AAAA-MM-DD permite ver
    otro día, para poder editar, despachar o cancelar pedidos futuros."""
    try:
        fecha = date.fromisoformat(request.args.get("fecha", ""))
    except ValueError:
        fecha = hoy_negocio()
    return render_template(
        "pedidos/hoy.html",
        pedidos=listar_pedidos_del_dia(fecha),
        fecha=fecha,
        es_hoy=fecha == hoy_negocio(),
        formas_pago=FORMAS_PAGO,
    )


def _volver_a_pedidos(pedido: Pedido):
    return redirect(url_for("pedidos.hoy", fecha=pedido.fecha_entrega.isoformat()))


@pedidos_bp.route("/pedidos/<int:pedido_id>/editar", methods=["GET", "POST"])
@login_required
def editar(pedido_id):
    """HU03 - Edición de un pedido antes de ser despachado."""
    pedido = db.get_or_404(Pedido, pedido_id)

    if request.method == "GET":
        if pedido.estado != ESTADO_CONFIRMADO:
            flash(f"El pedido #{pedido.id} ya está {pedido.estado} y no se puede editar.", "error")
            return _volver_a_pedidos(pedido)
        return _mostrar_formulario(_valores_desde_pedido(pedido), pedido=pedido)

    valores = _leer_valores(request.form)
    try:
        editar_pedido(pedido_id, _construir_dto(valores))
    except TransicionDePedidoInvalidaException as error:
        flash(str(error), "error")
        return _volver_a_pedidos(pedido)
    except ErrorDeNegocio as error:
        flash(str(error), "error")
        return _mostrar_formulario(valores, pedido=pedido)

    mensaje, categoria = _con_alerta_de_stock(f"Pedido #{pedido_id} actualizado.", pedido)
    flash(mensaje, categoria)
    return _volver_a_pedidos(pedido)


def _ejecutar_accion(pedido_id: int, accion, mensaje_exito: str):
    """Despachar y cancelar comparten el mismo flujo: buscar, ejecutar la
    regla de negocio y volver a la lista del día del pedido."""
    pedido = db.get_or_404(Pedido, pedido_id)
    try:
        accion(pedido_id)
    except ErrorDeNegocio as error:
        flash(str(error), "error")
    else:
        flash(mensaje_exito.format(id=pedido_id, cliente=pedido.cliente_nombre), "success")
    return _volver_a_pedidos(pedido)


@pedidos_bp.route("/pedidos/<int:pedido_id>/despachar", methods=["POST"])
@login_required
def despachar(pedido_id):
    """HU05 - Marcar pedido como despachado."""
    forma_pago = request.form.get("forma_pago", "")
    return _ejecutar_accion(
        pedido_id,
        lambda id_pedido: despachar_pedido(id_pedido, forma_pago),
        "Pedido #{id} de {cliente} despachado.",
    )


@pedidos_bp.route("/pedidos/<int:pedido_id>/cancelar", methods=["POST"])
@login_required
def cancelar(pedido_id):
    """HU06 - Cancelación de un pedido (libera el inventario comprometido)."""
    return _ejecutar_accion(
        pedido_id, cancelar_pedido, "Pedido #{id} de {cliente} cancelado. Inventario liberado."
    )


@pedidos_bp.route("/pedidos/historial")
@login_required
def historial():
    """HU07 - Búsqueda y consulta del historial de pedidos por fecha de
    entrega, estado, canal o nombre del cliente."""
    argumentos = request.args
    fechas, parametros = {}, {}
    for nombre in ("desde", "hasta"):
        texto = argumentos.get(nombre, "").strip()
        if not texto:
            continue
        try:
            fechas[nombre] = date.fromisoformat(texto)
            parametros[nombre] = texto
        except ValueError:
            flash(f"La fecha '{nombre}' no es válida y se ignoró.", "error")
    for nombre in ("estado", "canal", "cliente"):
        if argumentos.get(nombre, "").strip():
            parametros[nombre] = argumentos[nombre].strip()

    filtros = FiltrosHistorial(
        desde=fechas.get("desde"),
        hasta=fechas.get("hasta"),
        estado=parametros.get("estado", ""),
        canal=parametros.get("canal", ""),
        cliente=parametros.get("cliente", ""),
    )
    try:
        pagina = int(argumentos.get("pagina", "1"))
    except ValueError:
        pagina = 1

    try:
        resultado = buscar_pedidos(filtros, pagina)
    except ErrorDeNegocio as error:
        flash(str(error), "error")
        resultado = None

    return render_template(
        "pedidos/historial.html",
        filtros=filtros,
        parametros=parametros,
        resultado=resultado,
        estados=ESTADOS_PEDIDO,
        canales=CANALES,
    )
