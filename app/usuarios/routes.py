from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.auth.decoradores import requiere_administrador
from app.errores import ErrorDeNegocio
from app.extensions import db
from app.models import ROLES, Usuario
from app.usuarios import servicios

usuarios_bp = Blueprint("usuarios", __name__, template_folder="../templates/usuarios")


@usuarios_bp.route("/usuarios")
@login_required
@requiere_administrador
def listar():
    """HU22 - Lista de usuarios del sistema."""
    return render_template(
        "usuarios/lista.html",
        usuarios=servicios.listar_usuarios(),
        roles=ROLES,
        minimo_password=servicios.LONGITUD_MINIMA_PASSWORD,
    )


@usuarios_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@requiere_administrador
def crear():
    """HU22 - Crear un usuario y asignarle un rol."""
    valores = {"nombre": "", "email": "", "rol": ""}
    if request.method == "POST":
        valores = {
            "nombre": request.form.get("nombre", ""),
            "email": request.form.get("email", ""),
            "rol": request.form.get("rol", ""),
        }
        try:
            usuario = servicios.crear_usuario(
                valores["nombre"],
                valores["email"],
                request.form.get("password", ""),
                valores["rol"],
            )
        except ErrorDeNegocio as error:
            flash(str(error), "error")
        else:
            flash(f"Usuario {usuario.nombre} creado como {ROLES[usuario.rol]}.", "success")
            return redirect(url_for("usuarios.listar"))

    return render_template(
        "usuarios/form.html",
        roles=ROLES,
        valores=valores,
        minimo_password=servicios.LONGITUD_MINIMA_PASSWORD,
    )


def _ejecutar(usuario_id: int, accion, mensaje_exito: str):
    """Cambiar rol, desactivar y activar comparten el mismo flujo."""
    usuario = db.get_or_404(Usuario, usuario_id)
    try:
        accion()
    except ErrorDeNegocio as error:
        flash(str(error), "error")
    else:
        flash(mensaje_exito.format(nombre=usuario.nombre), "success")
    return redirect(url_for("usuarios.listar"))


@usuarios_bp.route("/usuarios/<int:usuario_id>/rol", methods=["POST"])
@login_required
@requiere_administrador
def cambiar_rol(usuario_id):
    nuevo_rol = request.form.get("rol", "")
    return _ejecutar(
        usuario_id,
        lambda: servicios.cambiar_rol(usuario_id, nuevo_rol),
        "Rol de {nombre} actualizado.",
    )


@usuarios_bp.route("/usuarios/<int:usuario_id>/desactivar", methods=["POST"])
@login_required
@requiere_administrador
def desactivar(usuario_id):
    return _ejecutar(
        usuario_id,
        lambda: servicios.desactivar_usuario(usuario_id, current_user.id),
        "Usuario {nombre} desactivado. Ya no puede iniciar sesión.",
    )


@usuarios_bp.route("/usuarios/<int:usuario_id>/activar", methods=["POST"])
@login_required
@requiere_administrador
def activar(usuario_id):
    return _ejecutar(
        usuario_id,
        lambda: servicios.activar_usuario(usuario_id),
        "Usuario {nombre} activado.",
    )
