from functools import wraps
from flask import abort
from flask_login import current_user
from app.models import ROL_ADMINISTRADOR


def requiere_administrador(vista):
    """Cada endpoint valida el rol en el servidor (sección 2.2 del chequeo
    de código seguro), no solo ocultando botones en la interfaz."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.rol != ROL_ADMINISTRADOR:
            abort(403)
        return vista(*args, **kwargs)

    return envoltura
