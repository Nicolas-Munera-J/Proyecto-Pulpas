"""Pruebas de HU22 - Gestión de usuarios del sistema.

Criterios de aceptación (Dado / Cuando / Entonces):
- Dado un administrador, cuando crea un usuario con rol y contraseña, el usuario
  puede iniciar sesión y solo accede a lo que su rol permite.
- Cuando desactiva un usuario, ya no puede iniciar sesión y su sesión abierta
  deja de valer. El historial que registró se conserva.
- El sistema nunca queda sin un administrador activo.
"""
import pytest

from app.errores import DatosInvalidosException, OperacionNoPermitidaException
from app.extensions import db
from app.models import ROL_ADMINISTRADOR, ROL_GESTOR_PEDIDOS, Pedido, Usuario
from app.usuarios.servicios import (
    LONGITUD_MINIMA_PASSWORD,
    activar_usuario,
    cambiar_rol,
    crear_usuario,
    desactivar_usuario,
    listar_usuarios,
)
from tests.conftest import EMAIL_ADMIN, EMAIL_GESTOR, PASSWORD_GESTOR
from tests.test_ciclo_pedido import _crear
from tests.test_pedidos import _ids, _iniciar_sesion_gestor
from tests.test_ventas_reportes import _iniciar_sesion_admin

CLAVE_VALIDA = "clave-segura-123"


def _id_de(app, email):
    with app.app_context():
        return Usuario.query.filter_by(email=email).one().id


def _crear_admin_extra(app, email="admin2@pulpas.test"):
    with app.app_context():
        return crear_usuario("Segundo Admin", email, CLAVE_VALIDA, ROL_ADMINISTRADOR).id


def _intentar_login(cliente, email, password):
    return cliente.post("/login", data={"email": email, "password": password}, follow_redirects=False)


# --------------------------------------------------------------------------
# Crear usuarios
# --------------------------------------------------------------------------
def test_crear_usuario_normaliza_el_correo_y_guarda_solo_el_hash(app):
    with app.app_context():
        usuario = crear_usuario("  Laura Ríos ", "  Laura@Pulpas.TEST ", CLAVE_VALIDA, ROL_GESTOR_PEDIDOS)

        assert usuario.nombre == "Laura Ríos" and usuario.email == "laura@pulpas.test"
        assert usuario.activo is True and usuario.rol == ROL_GESTOR_PEDIDOS
        assert usuario.password_hash != CLAVE_VALIDA and CLAVE_VALIDA not in usuario.password_hash
        assert usuario.verificar_password(CLAVE_VALIDA) is True
        assert usuario.verificar_password("otra-clave") is False


@pytest.mark.parametrize(
    "nombre, email, password, rol",
    [
        ("", "a@b.co", CLAVE_VALIDA, ROL_GESTOR_PEDIDOS),  # sin nombre
        ("   ", "a@b.co", CLAVE_VALIDA, ROL_GESTOR_PEDIDOS),
        ("Ana", "sin-arroba", CLAVE_VALIDA, ROL_GESTOR_PEDIDOS),  # correo inválido
        ("Ana", "ana@dominio", CLAVE_VALIDA, ROL_GESTOR_PEDIDOS),
        ("Ana", "", CLAVE_VALIDA, ROL_GESTOR_PEDIDOS),
        ("Ana", "a@b.co", "x" * (LONGITUD_MINIMA_PASSWORD - 1), ROL_GESTOR_PEDIDOS),  # clave corta
        ("Ana", "a@b.co", "", ROL_GESTOR_PEDIDOS),
        ("Ana", "a@b.co", CLAVE_VALIDA, "superusuario"),  # rol inexistente
        ("Ana", "a@b.co", CLAVE_VALIDA, ""),
        ("x" * 121, "a@b.co", CLAVE_VALIDA, ROL_GESTOR_PEDIDOS),
    ],
)
def test_crear_usuario_con_datos_invalidos_se_rechaza(app, nombre, email, password, rol):
    with app.app_context():
        antes = Usuario.query.count()
        with pytest.raises(DatosInvalidosException):
            crear_usuario(nombre, email, password, rol)
        assert Usuario.query.count() == antes


def test_no_se_puede_repetir_un_correo_aunque_cambien_las_mayusculas(app):
    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            crear_usuario("Otro", EMAIL_GESTOR.upper(), CLAVE_VALIDA, ROL_GESTOR_PEDIDOS)


def test_usuario_creado_puede_iniciar_sesion_y_su_rol_limita_el_acceso(app, cliente):
    with app.app_context():
        crear_usuario("Nueva Gestora", "nueva@pulpas.test", CLAVE_VALIDA, ROL_GESTOR_PEDIDOS)

    assert _intentar_login(cliente, "nueva@pulpas.test", CLAVE_VALIDA).status_code == 302
    assert cliente.get("/pedidos/hoy").status_code == 200
    assert cliente.get("/usuarios").status_code == 403  # gestor: sin gestión de usuarios


# --------------------------------------------------------------------------
# Cambiar rol
# --------------------------------------------------------------------------
def test_cambiar_rol_a_administrador_y_de_vuelta(app, cliente):
    gestor = _id_de(app, EMAIL_GESTOR)

    with app.app_context():
        assert cambiar_rol(gestor, ROL_ADMINISTRADOR).rol == ROL_ADMINISTRADOR
        assert cambiar_rol(gestor, ROL_GESTOR_PEDIDOS).rol == ROL_GESTOR_PEDIDOS  # hay otro admin


def test_cambiar_rol_con_valor_invalido_o_usuario_inexistente(app):
    gestor = _id_de(app, EMAIL_GESTOR)

    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            cambiar_rol(gestor, "dueño")
        with pytest.raises(DatosInvalidosException):
            cambiar_rol(99999, ROL_ADMINISTRADOR)
        assert db.session.get(Usuario, gestor).rol == ROL_GESTOR_PEDIDOS


def test_no_se_puede_quitar_el_rol_al_unico_administrador_activo(app):
    admin = _id_de(app, EMAIL_ADMIN)

    with app.app_context():
        with pytest.raises(OperacionNoPermitidaException):
            cambiar_rol(admin, ROL_GESTOR_PEDIDOS)
        assert db.session.get(Usuario, admin).rol == ROL_ADMINISTRADOR

        # Con un segundo administrador activo, ya se puede
        _crear_admin_extra(app)
        assert cambiar_rol(admin, ROL_GESTOR_PEDIDOS).rol == ROL_GESTOR_PEDIDOS


# --------------------------------------------------------------------------
# Desactivar y activar
# --------------------------------------------------------------------------
def test_usuario_desactivado_no_puede_iniciar_sesion(app, cliente):
    admin, gestor = _id_de(app, EMAIL_ADMIN), _id_de(app, EMAIL_GESTOR)

    with app.app_context():
        assert desactivar_usuario(gestor, admin).activo is False

    r = _intentar_login(cliente, EMAIL_GESTOR, PASSWORD_GESTOR)
    assert r.status_code == 200 and b"Credenciales" in r.data  # no entra, y no revela el motivo


def test_desactivar_cierra_la_sesion_que_ya_estaba_abierta(app, cliente):
    admin, gestor = _id_de(app, EMAIL_ADMIN), _id_de(app, EMAIL_GESTOR)
    _iniciar_sesion_gestor(cliente)
    assert cliente.get("/pedidos/hoy").status_code == 200

    with app.app_context():
        desactivar_usuario(gestor, admin)

    r = cliente.get("/pedidos/hoy")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_desactivar_no_borra_el_historial_del_usuario(app):
    mora, _, gestor = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])

    with app.app_context():
        desactivar_usuario(gestor, _id_de(app, EMAIL_ADMIN))
        pedido = db.session.get(Pedido, pedido_id)
        assert pedido is not None and pedido.usuario.activo is False


def test_no_puedes_desactivar_tu_propia_cuenta(app):
    admin = _id_de(app, EMAIL_ADMIN)
    with app.app_context():
        with pytest.raises(OperacionNoPermitidaException):
            desactivar_usuario(admin, admin)


def test_no_se_puede_desactivar_al_ultimo_administrador_activo(app):
    admin = _id_de(app, EMAIL_ADMIN)
    segundo = _crear_admin_extra(app)

    with app.app_context():
        desactivar_usuario(admin, segundo)  # queda solo el segundo
        with pytest.raises(OperacionNoPermitidaException):
            desactivar_usuario(segundo, admin)  # actor distinto, pero es el último
        assert db.session.get(Usuario, segundo).activo is True


def test_reactivar_usuario_le_devuelve_el_acceso(app, cliente):
    admin, gestor = _id_de(app, EMAIL_ADMIN), _id_de(app, EMAIL_GESTOR)

    with app.app_context():
        desactivar_usuario(gestor, admin)
        with pytest.raises(OperacionNoPermitidaException):
            desactivar_usuario(gestor, admin)  # ya estaba desactivado
        activar_usuario(gestor)
        with pytest.raises(OperacionNoPermitidaException):
            activar_usuario(gestor)  # ya estaba activo

    assert _intentar_login(cliente, EMAIL_GESTOR, PASSWORD_GESTOR).status_code == 302


def test_listar_usuarios_pone_primero_a_los_activos(app):
    admin, gestor = _id_de(app, EMAIL_ADMIN), _id_de(app, EMAIL_GESTOR)

    with app.app_context():
        desactivar_usuario(gestor, admin)
        assert [u.activo for u in listar_usuarios()] == [True, False]


# --------------------------------------------------------------------------
# Interfaz (HTTP)
# --------------------------------------------------------------------------
def test_interfaz_administrador_ve_la_lista_de_usuarios(app, cliente):
    _iniciar_sesion_admin(cliente)

    html = cliente.get("/usuarios").data.decode()

    assert EMAIL_ADMIN in html and EMAIL_GESTOR in html
    assert "(tú)" in html


def test_interfaz_crea_un_usuario(app, cliente):
    _iniciar_sesion_admin(cliente)

    r = cliente.post(
        "/usuarios/nuevo",
        data={"nombre": "Marta Gil", "email": "marta@pulpas.test", "rol": ROL_GESTOR_PEDIDOS, "password": CLAVE_VALIDA},
        follow_redirects=True,
    )

    assert b"creado como Gestor de pedidos" in r.data and b"marta@pulpas.test" in r.data


def test_interfaz_correo_repetido_muestra_error_y_conserva_lo_escrito(app, cliente):
    _iniciar_sesion_admin(cliente)

    r = cliente.post(
        "/usuarios/nuevo",
        data={"nombre": "Otra Persona", "email": EMAIL_GESTOR, "rol": ROL_GESTOR_PEDIDOS, "password": CLAVE_VALIDA},
    )

    assert r.status_code == 200 and b"Ya existe un usuario" in r.data
    assert b'value="Otra Persona"' in r.data and CLAVE_VALIDA.encode() not in r.data


def test_interfaz_cambiar_rol_desactivar_y_activar(app, cliente):
    gestor = _id_de(app, EMAIL_GESTOR)
    _iniciar_sesion_admin(cliente)

    r = cliente.post(f"/usuarios/{gestor}/rol", data={"rol": ROL_ADMINISTRADOR}, follow_redirects=True)
    assert b"Rol de Gestor Prueba actualizado" in r.data

    r = cliente.post(f"/usuarios/{gestor}/desactivar", follow_redirects=True)
    assert b"desactivado" in r.data
    with app.app_context():
        assert db.session.get(Usuario, gestor).activo is False

    r = cliente.post(f"/usuarios/{gestor}/activar", follow_redirects=True)
    assert b"activado" in r.data


def test_interfaz_no_ofrece_ni_permite_desactivarse_a_si_mismo(app, cliente):
    admin = _id_de(app, EMAIL_ADMIN)
    _iniciar_sesion_admin(cliente)

    assert f"/usuarios/{admin}/desactivar" not in cliente.get("/usuarios").data.decode()

    r = cliente.post(f"/usuarios/{admin}/desactivar", follow_redirects=True)
    assert b"No puedes desactivar tu propia cuenta" in r.data
    with app.app_context():
        assert db.session.get(Usuario, admin).activo is True


def test_interfaz_usuario_inexistente_da_404(app, cliente):
    _iniciar_sesion_admin(cliente)
    for accion in ("rol", "desactivar", "activar"):
        assert cliente.post(f"/usuarios/9999/{accion}", data={"rol": ROL_ADMINISTRADOR}).status_code == 404


def test_gestion_de_usuarios_solo_para_administrador(app, cliente):
    gestor = _id_de(app, EMAIL_GESTOR)

    for ruta in ("/usuarios", "/usuarios/nuevo"):  # sin sesión
        r = cliente.get(ruta)
        assert r.status_code == 302 and "/login" in r.headers["Location"]

    _iniciar_sesion_gestor(cliente)
    assert cliente.get("/usuarios").status_code == 403
    assert cliente.get("/usuarios/nuevo").status_code == 403
    # El gestor tampoco puede darse permisos de administrador ni crear cuentas
    assert cliente.post(f"/usuarios/{gestor}/rol", data={"rol": ROL_ADMINISTRADOR}).status_code == 403
    assert cliente.post("/usuarios/nuevo", data={
        "nombre": "Intruso", "email": "intruso@pulpas.test", "rol": ROL_ADMINISTRADOR, "password": CLAVE_VALIDA,
    }).status_code == 403

    with app.app_context():
        assert db.session.get(Usuario, gestor).rol == ROL_GESTOR_PEDIDOS
        assert Usuario.query.filter_by(email="intruso@pulpas.test").first() is None
