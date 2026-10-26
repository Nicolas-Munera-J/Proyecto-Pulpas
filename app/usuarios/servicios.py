"""HU22 - Gestión de usuarios del sistema (solo Administrador).

Reglas:
- Los usuarios NO se borran, se desactivan: pedidos y movimientos de
  inventario guardan quién los registró y ese historial debe conservarse.
- Un usuario desactivado no puede iniciar sesión y su sesión abierta deja de
  valer en la siguiente petición (ver user_loader en app/__init__.py).
- Siempre debe quedar al menos un administrador activo, y nadie puede
  desactivar su propia cuenta, para que el sistema no quede sin quién lo
  administre.
- Las contraseñas se guardan solo como hash (RNF03), nunca en texto plano.
"""
import re
from typing import List

from sqlalchemy.exc import IntegrityError

from app.errores import DatosInvalidosException, OperacionNoPermitidaException
from app.extensions import db
from app.models import ROL_ADMINISTRADOR, ROLES, Usuario

LONGITUD_MINIMA_PASSWORD = 8
LONGITUD_MAXIMA_NOMBRE = 120
LONGITUD_MAXIMA_EMAIL = 120
_PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def listar_usuarios() -> List[Usuario]:
    """Activos primero, luego por nombre."""
    return Usuario.query.order_by(Usuario.activo.desc(), Usuario.nombre).all()


def _contar_administradores_activos() -> int:
    return Usuario.query.filter_by(rol=ROL_ADMINISTRADOR, activo=True).count()


def _obtener_usuario(usuario_id: int) -> Usuario:
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        raise DatosInvalidosException("El usuario indicado no existe.")
    return usuario


def _es_ultimo_administrador_activo(usuario: Usuario) -> bool:
    return (
        usuario.activo
        and usuario.rol == ROL_ADMINISTRADOR
        and _contar_administradores_activos() <= 1
    )


def crear_usuario(nombre: str, email: str, password: str, rol: str) -> Usuario:
    """Crea un usuario activo con el rol indicado."""
    nombre = (nombre or "").strip()
    email = (email or "").strip().lower()

    if not nombre:
        raise DatosInvalidosException("El nombre es obligatorio.")
    if len(nombre) > LONGITUD_MAXIMA_NOMBRE:
        raise DatosInvalidosException(f"El nombre no puede superar {LONGITUD_MAXIMA_NOMBRE} caracteres.")
    if not email or len(email) > LONGITUD_MAXIMA_EMAIL or not _PATRON_EMAIL.match(email):
        raise DatosInvalidosException("Ingresa un correo electrónico válido.")
    if rol not in ROLES:
        raise DatosInvalidosException("Selecciona un rol válido.")
    if len(password or "") < LONGITUD_MINIMA_PASSWORD:
        raise DatosInvalidosException(
            f"La contraseña debe tener al menos {LONGITUD_MINIMA_PASSWORD} caracteres."
        )
    if Usuario.query.filter_by(email=email).first() is not None:
        raise DatosInvalidosException("Ya existe un usuario con ese correo.")

    usuario = Usuario(nombre=nombre, email=email, rol=rol, activo=True)
    usuario.establecer_password(password)
    try:
        db.session.add(usuario)
        db.session.commit()
    except IntegrityError:  # dos altas simultáneas con el mismo correo
        db.session.rollback()
        raise DatosInvalidosException("Ya existe un usuario con ese correo.")
    return usuario


def cambiar_rol(usuario_id: int, nuevo_rol: str) -> Usuario:
    """Asigna un rol a un usuario."""
    if nuevo_rol not in ROLES:
        raise DatosInvalidosException("Selecciona un rol válido.")
    usuario = _obtener_usuario(usuario_id)
    if usuario.rol == nuevo_rol:
        return usuario
    if nuevo_rol != ROL_ADMINISTRADOR and _es_ultimo_administrador_activo(usuario):
        raise OperacionNoPermitidaException(
            "No se puede quitar el rol al único administrador activo: el sistema quedaría sin administrador."
        )
    usuario.rol = nuevo_rol
    db.session.commit()
    return usuario


def desactivar_usuario(usuario_id: int, actor_id: int) -> Usuario:
    """Desactiva un usuario (no lo borra)."""
    usuario = _obtener_usuario(usuario_id)
    if usuario.id == actor_id:
        raise OperacionNoPermitidaException("No puedes desactivar tu propia cuenta.")
    if not usuario.activo:
        raise OperacionNoPermitidaException("El usuario ya está desactivado.")
    if _es_ultimo_administrador_activo(usuario):
        raise OperacionNoPermitidaException(
            "No se puede desactivar al único administrador activo: el sistema quedaría sin administrador."
        )
    usuario.activo = False
    db.session.commit()
    return usuario


def activar_usuario(usuario_id: int) -> Usuario:
    """Vuelve a activar un usuario desactivado."""
    usuario = _obtener_usuario(usuario_id)
    if usuario.activo:
        raise OperacionNoPermitidaException("El usuario ya está activo.")
    usuario.activo = True
    db.session.commit()
    return usuario
