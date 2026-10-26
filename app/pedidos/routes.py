from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.errores import (
    DatosInvalidosException,
    InventarioInsuficienteException,
    PedidoPosiblementeDuplicadoException,
)
from app.models import CANAL_WHATSAPP, CANALES, Producto
from app.pedidos.dtos import ItemPedidoDTO, PedidoDTO
from app.pedidos.servicios import listar_pedidos_del_dia, registrar_pedido
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


def _mostrar_formulario(valores: dict, duplicado=None):
    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    return render_template(
        "pedidos/nuevo.html",
        productos=productos,
        valores=valores,
        canales=CANALES,
        hoy=hoy_negocio().isoformat(),
        duplicado=duplicado,
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
    except (DatosInvalidosException, InventarioInsuficienteException) as error:
        flash(str(error), "error")
        return _mostrar_formulario(valores)

    flash(f"Pedido #{pedido.id} de {pedido.cliente_nombre} registrado y confirmado.", "success")
    return redirect(url_for("pedidos.nuevo"))


@pedidos_bp.route("/pedidos/hoy")
@login_required
def hoy():
    """HU01 - Consulta de pedidos del día."""
    return render_template(
        "pedidos/hoy.html",
        pedidos=listar_pedidos_del_dia(),
        fecha=hoy_negocio(),
    )
