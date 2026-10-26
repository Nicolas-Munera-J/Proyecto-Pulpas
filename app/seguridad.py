"""Protección CSRF para los formularios que modifican datos.

Sin esto, una página maliciosa podría hacer que el navegador de un usuario con
sesión iniciada envíe un formulario al sistema sin que se dé cuenta (por
ejemplo despachar un pedido, o crear un administrador en HU22). Cada sesión
recibe un token secreto; los formularios lo incluyen y el servidor lo exige en
toda petición que no sea de solo lectura.
"""
import hmac
import secrets

from flask import abort, current_app, request, session

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def obtener_token_csrf() -> str:
    """Token de la sesión actual (se crea la primera vez que se pide)."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validar_csrf() -> None:
    """Se ejecuta antes de cada petición: rechaza con 400 las que modifican
    datos y no traen el token correcto."""
    if not current_app.config.get("CSRF_ACTIVADO", True):
        return
    if request.method in METODOS_SEGUROS:
        return

    esperado = session.get("_csrf_token", "")
    recibido = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
    if not esperado or not hmac.compare_digest(esperado, recibido):
        abort(400, description="Token CSRF inválido o ausente. Recarga la página e inténtalo de nuevo.")
