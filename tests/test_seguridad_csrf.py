"""Pruebas de la protección CSRF (app/seguridad.py).

Por defecto las pruebas la desactivan (CSRF_ACTIVADO = False en conftest.py)
para no repetir el token en cada petición; aquí se activa a propósito.

Escenario que se evita: un administrador con sesión iniciada visita una página
maliciosa que envía en secreto un formulario al sistema (crear un usuario
administrador, despachar o cancelar un pedido). Sin el token secreto de la
sesión, el servidor rechaza la petición.
"""
import re

import pytest

from app.extensions import db
from app.models import ESTADO_CONFIRMADO, ROL_ADMINISTRADOR, Pedido, Usuario
from tests.conftest import EMAIL_ADMIN, EMAIL_GESTOR, PASSWORD_ADMIN, PASSWORD_GESTOR
from tests.test_ciclo_pedido import _crear
from tests.test_pedidos import _ids

PATRON_TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture
def con_csrf(app):
    app.config["CSRF_ACTIVADO"] = True
    return app


def _token(cliente, ruta="/login"):
    html = cliente.get(ruta).data.decode()
    coincidencia = PATRON_TOKEN.search(html)
    assert coincidencia, f"{ruta} no trae token CSRF"
    return coincidencia.group(1)


def _login(cliente, email, password):
    r = cliente.post("/login", data={"email": email, "password": password, "csrf_token": _token(cliente)})
    assert r.status_code == 302
    return _token(cliente, "/pedidos/nuevo")  # token de la sesión ya iniciada (página con formulario)


def test_post_sin_token_se_rechaza_con_400(con_csrf, cliente):
    r = cliente.post("/login", data={"email": EMAIL_GESTOR, "password": PASSWORD_GESTOR})
    assert r.status_code == 400 and b"CSRF" in r.data


def test_post_con_token_falso_se_rechaza(con_csrf, cliente):
    _token(cliente)  # la sesión ya tiene un token real
    r = cliente.post("/login", data={"email": EMAIL_GESTOR, "password": PASSWORD_GESTOR, "csrf_token": "falso"})
    assert r.status_code == 400


def test_login_funciona_con_el_token_correcto(con_csrf, cliente):
    _login(cliente, EMAIL_GESTOR, PASSWORD_GESTOR)
    assert cliente.get("/pedidos/hoy").status_code == 200


def test_las_peticiones_de_lectura_no_necesitan_token(con_csrf, cliente):
    assert cliente.get("/login").status_code == 200


def test_despachar_o_cancelar_sin_token_no_cambia_nada(con_csrf, app, cliente):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])
    _login(cliente, EMAIL_GESTOR, PASSWORD_GESTOR)

    assert cliente.post(f"/pedidos/{pedido_id}/despachar", data={"forma_pago": "efectivo"}).status_code == 400
    assert cliente.post(f"/pedidos/{pedido_id}/cancelar").status_code == 400

    with app.app_context():
        assert db.session.get(Pedido, pedido_id).estado == ESTADO_CONFIRMADO


def test_despachar_con_token_si_funciona(con_csrf, app, cliente):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])
    token = _login(cliente, EMAIL_GESTOR, PASSWORD_GESTOR)

    r = cliente.post(f"/pedidos/{pedido_id}/despachar", data={"forma_pago": "efectivo", "csrf_token": token})

    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Pedido, pedido_id).estado == "despachado"


def test_el_token_tambien_se_acepta_en_la_cabecera(con_csrf, app, cliente):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 1)])
    token = _login(cliente, EMAIL_GESTOR, PASSWORD_GESTOR)

    r = cliente.post(f"/pedidos/{pedido_id}/cancelar", headers={"X-CSRFToken": token})

    assert r.status_code == 302


def test_no_se_puede_crear_un_administrador_sin_token(con_csrf, app, cliente):
    # El ataque más grave que habilitaría HU22 sin esta protección.
    _login(cliente, EMAIL_ADMIN, PASSWORD_ADMIN)

    r = cliente.post(
        "/usuarios/nuevo",
        data={"nombre": "Intruso", "email": "intruso@pulpas.test", "rol": ROL_ADMINISTRADOR, "password": "clave-segura-123"},
    )

    assert r.status_code == 400
    with app.app_context():
        assert Usuario.query.filter_by(email="intruso@pulpas.test").first() is None


def test_el_token_es_estable_en_la_sesion_y_distinto_entre_sesiones(con_csrf, app):
    uno, dos = app.test_client(), app.test_client()

    assert _token(uno) == _token(uno)
    assert _token(uno) != _token(dos)
    # El token de otra sesión no sirve
    r = dos.post("/login", data={"email": EMAIL_GESTOR, "password": PASSWORD_GESTOR, "csrf_token": _token(uno)})
    assert r.status_code == 400


def test_todos_los_formularios_post_llevan_el_token(con_csrf, app, cliente):
    """Red de seguridad: si alguien agrega un formulario nuevo sin el token,
    esta prueba falla en lugar de que el botón deje de funcionar en producción."""
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 1)])

    html_login = cliente.get("/login").data.decode()
    assert html_login.count('method="POST"') == html_login.count('name="csrf_token"') == 1

    _login(cliente, EMAIL_ADMIN, PASSWORD_ADMIN)
    paginas = [
        "/productos/nuevo", "/inventario/entradas", "/inventario/mermas", "/pedidos/nuevo",
        "/pedidos/hoy", f"/pedidos/{pedido_id}/editar", "/usuarios", "/usuarios/nuevo",
    ]
    for ruta in paginas:
        html = cliente.get(ruta).data.decode()
        formularios = html.count('method="POST"')
        assert formularios >= 1, ruta
        assert formularios == html.count('name="csrf_token"'), f"{ruta}: formulario POST sin token CSRF"
