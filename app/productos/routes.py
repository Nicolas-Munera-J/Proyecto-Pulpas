from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required

from app.extensions import db
from app.models import Producto
from app.auth.decoradores import requiere_administrador
from app.errores import DatosInvalidosException

productos_bp = Blueprint("productos", __name__, template_folder="../templates/productos")


@productos_bp.route("/productos")
@login_required
def listar():
    productos = Producto.query.order_by(Producto.nombre).all()
    return render_template("productos/list.html", productos=productos)


@productos_bp.route("/productos/nuevo", methods=["GET", "POST"])
@login_required
@requiere_administrador
def crear():
    """HU13 - Permite al administrador registrar productos con nombre,
    presentación y unidad de medida."""
    if request.method == "POST":
        try:
            nombre = request.form.get("nombre", "").strip()
            presentacion = request.form.get("presentacion", "").strip()
            unidad_medida = request.form.get("unidad_medida", "").strip()
            precio = request.form.get("precio", "0")
            umbral_minimo = request.form.get("umbral_minimo", "0")

            if not nombre or not presentacion or not unidad_medida:
                raise DatosInvalidosException("Nombre, presentación y unidad de medida son obligatorios.")

            producto = Producto(
                nombre=nombre,
                presentacion=presentacion,
                unidad_medida=unidad_medida,
                precio=float(precio),
                umbral_minimo=int(umbral_minimo),
            )
            db.session.add(producto)
            db.session.commit()
            flash(f"Producto '{nombre}' creado correctamente.", "success")
            return redirect(url_for("productos.listar"))

        except (DatosInvalidosException, ValueError) as error:
            flash(str(error) or "Datos inválidos.", "error")

    return render_template("productos/form.html")
