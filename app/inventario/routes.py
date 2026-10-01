from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from app.models import Producto
from app.auth.decoradores import requiere_administrador
from app.errores import DatosInvalidosException
from app.inventario.servicios import registrar_entrada_inventario, listar_existencias

inventario_bp = Blueprint("inventario", __name__, template_folder="../templates/inventario")


@inventario_bp.route("/inventario")
@login_required
def existencias():
    """HU14 - Consulta de existencias actuales."""
    productos = listar_existencias()
    return render_template("inventario/existencias.html", productos=productos)


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
