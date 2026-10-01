from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from app.models import Usuario

auth_bp = Blueprint("auth", __name__, template_folder="../templates")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """HU20 - Autentica usuarios y restringe funciones según el rol."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Debes ingresar correo y contraseña.", "error")
            return render_template("login.html")

        usuario = Usuario.query.filter_by(email=email, activo=True).first()

        if usuario is None or not usuario.verificar_password(password):
            # Mensaje genérico a propósito: no revelar si el correo existe o no.
            flash("Credenciales inválidas.", "error")
            return render_template("login.html")

        login_user(usuario)
        return redirect(url_for("main.dashboard"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """HU21 - Finaliza la sesión y exige autenticación para volver a acceder
    a funciones protegidas (@login_required en cada ruta protegida)."""
    logout_user()
    flash("Sesión finalizada.", "info")
    return redirect(url_for("auth.login"))
