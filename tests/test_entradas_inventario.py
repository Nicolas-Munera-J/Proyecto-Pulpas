"""Pruebas de HU08 – Registro de entradas de inventario.

Criterio de aceptación (Dado / Cuando / Entonces) que se verifica en la
primera prueba: dado un producto con 10 unidades disponibles, cuando el
administrador registra una entrada de 5, entonces la existencia queda en 15.
"""
import pytest

from app.errores import DatosInvalidosException
from app.inventario.servicios import registrar_entrada_inventario
from app.models import MovimientoInventario, Producto, Usuario, TIPO_ENTRADA
from tests.conftest import (
    EMAIL_ADMIN,
    EMAIL_GESTOR,
    EXISTENCIA_INICIAL,
    NOMBRE_PRODUCTO,
    PASSWORD_ADMIN,
    PASSWORD_GESTOR,
)


def _iniciar_sesion(cliente, email, password):
    respuesta = cliente.post("/login", data={"email": email, "password": password})
    assert respuesta.status_code == 302  # login correcto redirige al dashboard


def _ids(app):
    with app.app_context():
        producto = Producto.query.filter_by(nombre=NOMBRE_PRODUCTO).one()
        admin = Usuario.query.filter_by(email=EMAIL_ADMIN).one()
        return producto.id, admin.id


def _existencia_disponible(app):
    with app.app_context():
        return Producto.query.filter_by(nombre=NOMBRE_PRODUCTO).one().existencia_disponible


# 1. Criterio de aceptación de HU08 ----------------------------------------
def test_entrada_incrementa_existencia_y_registra_movimiento(app):
    # Dado un producto con 10 unidades disponibles
    producto_id, admin_id = _ids(app)

    # Cuando el administrador registra una entrada de 5 unidades
    with app.app_context():
        movimiento = registrar_entrada_inventario(
            producto_id=producto_id, cantidad=5, usuario_id=admin_id,
            observacion="Compra semanal",
        )
        assert movimiento.tipo == TIPO_ENTRADA
        assert movimiento.cantidad == 5

    # Entonces la existencia disponible queda en 15 y hay un movimiento guardado
    assert _existencia_disponible(app) == EXISTENCIA_INICIAL + 5
    with app.app_context():
        assert MovimientoInventario.query.count() == 1


# 2. Validación de negocio: cantidades no positivas ---------------------------
@pytest.mark.parametrize("cantidad_invalida", [0, -3])
def test_entrada_con_cantidad_no_positiva_se_rechaza(app, cantidad_invalida):
    producto_id, admin_id = _ids(app)

    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            registrar_entrada_inventario(
                producto_id=producto_id, cantidad=cantidad_invalida, usuario_id=admin_id,
            )

    # La existencia no cambió y no quedó ningún movimiento registrado
    assert _existencia_disponible(app) == EXISTENCIA_INICIAL
    with app.app_context():
        assert MovimientoInventario.query.count() == 0


# 3. Producto inexistente ------------------------------------------------------
def test_entrada_para_producto_inexistente_se_rechaza(app):
    _, admin_id = _ids(app)

    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            registrar_entrada_inventario(producto_id=99999, cantidad=5, usuario_id=admin_id)


# 4. De punta a punta por la interfaz: el administrador registra una entrada ---
def test_administrador_registra_entrada_desde_la_interfaz(app, cliente):
    producto_id, _ = _ids(app)
    _iniciar_sesion(cliente, EMAIL_ADMIN, PASSWORD_ADMIN)

    respuesta = cliente.post(
        "/inventario/entradas",
        data={"producto_id": producto_id, "cantidad": "7", "observacion": "Lote de prueba"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert b"Entrada registrada" in respuesta.data  # confirmación que ve el usuario
    assert _existencia_disponible(app) == EXISTENCIA_INICIAL + 7


# 5. Autorización por rol en el servidor (sección 2.2 del chequeo de seguridad)
def test_gestor_de_pedidos_no_puede_registrar_entradas(app, cliente):
    producto_id, _ = _ids(app)
    _iniciar_sesion(cliente, EMAIL_GESTOR, PASSWORD_GESTOR)

    respuesta = cliente.post(
        "/inventario/entradas",
        data={"producto_id": producto_id, "cantidad": "7"},
    )

    assert respuesta.status_code == 403
    assert _existencia_disponible(app) == EXISTENCIA_INICIAL


def test_sin_sesion_se_redirige_al_login(cliente):
    respuesta = cliente.get("/inventario/entradas")

    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]
