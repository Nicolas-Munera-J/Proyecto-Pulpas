from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from app.models import MOTIVOS_MERMA, Producto
from app.auth.decoradores import requiere_administrador
from app.errores import DatosInvalidosException, ErrorDeNegocio
from app.inventario.servicios import (
    describir_stock_bajo,
    listar_existencias,
    listar_mermas,
    listar_stock_bajo,
    registrar_entrada_inventario,
    registrar_merma,
)

inventario_bp = Blueprint("inventario", __name__, template_folder="../templates/inventario")


@inventario_bp.route("/inventario")
@login_required
def existencias():
    """HU14 - Consulta de existencias actuales. Con ?solo_bajo=1 muestra
    únicamente los productos en stock bajo (HU15)."""
    solo_bajo = request.args.get("solo_bajo") == "1"
    productos = listar_stock_bajo() if solo_bajo else listar_existencias()
    return render_template("inventario/existencias.html", productos=productos, solo_bajo=solo_bajo)


@inventario_bp.route("/inventario/entradas", methods=["GET", "POST"])
@login_required
@requiere_administrador
def registrar_entrada():
    """HU08 - Registro de entradas de inventario."""
    if request.method == "POST":
        try:
            producto_id = int(request.form.get("producto_id"))
            cantidad = int(request.form.get("cantidad", 0))
            observacion = request.form.get("observacion", "").strip()

            movimiento = registrar_entrada_inventario(
                producto_id=producto_id,
                cantidad=cantidad,
                usuario_id=current_user.id,
                observacion=observacion,
            )
            flash(
                f"Entrada registrada: +{movimiento.cantidad} unidades de "
                f"{movimiento.producto.nombre}.",
                "success",
            )
            return redirect(url_for("inventario.registrar_entrada"))

        except (DatosInvalidosException, ValueError, TypeError) as error:
            flash(str(error) or "Datos inválidos.", "error")

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    return render_template("inventario/entradas.html", productos=productos)


@inventario_bp.route("/inventario/mermas", methods=["GET", "POST"])
@login_required
@requiere_administrador
def registrar_merma_vista():
    """HU16 - Registro de mermas o pérdidas de inventario (daño o vencimiento)."""
    if request.method == "POST":
        try:
            producto_id = int(request.form.get("producto_id"))
            cantidad = int(request.form.get("cantidad", 0))
        except (ValueError, TypeError):
            flash("Selecciona un producto e indica una cantidad numérica.", "error")
        else:
            try:
                merma = registrar_merma(
                    producto_id=producto_id,
                    cantidad=cantidad,
                    motivo=request.form.get("motivo", ""),
                    usuario_id=current_user.id,
                    observacion=request.form.get("observacion", ""),
                )
            except ErrorDeNegocio as error:
                flash(str(error), "error")
            else:
                mensaje = (
                    f"Merma registrada: -{merma.cantidad} unidades de {merma.producto.nombre} "
                    f"({MOTIVOS_MERMA[merma.motivo].lower()})."
                )
                alertas = describir_stock_bajo([merma.producto_id])
                if alertas:
                    mensaje += " Atención, existencia baja: " + "; ".join(alertas) + "."
                flash(mensaje, "warning" if alertas else "success")
                return redirect(url_for("inventario.registrar_merma_vista"))

    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    return render_template(
        "inventario/mermas.html",
        productos=productos,
        motivos=MOTIVOS_MERMA,
        mermas=listar_mermas(),
    )
