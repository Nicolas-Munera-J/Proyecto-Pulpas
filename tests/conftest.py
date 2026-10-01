"""Configuración compartida de las pruebas.

Cada prueba recibe una aplicación nueva con una base de datos SQLite en
memoria, así que ninguna prueba depende de otra ni toca pulpas.db.
"""
import pytest

from app import create_app
from app.extensions import db
from app.models import (
    Usuario,
    Producto,
    ROL_ADMINISTRADOR,
    ROL_GESTOR_PEDIDOS,
)

EMAIL_ADMIN = "admin-prueba@pulpas.test"
PASSWORD_ADMIN = "clave-admin-prueba"
EMAIL_GESTOR = "gestor-prueba@pulpas.test"
PASSWORD_GESTOR = "clave-gestor-prueba"

NOMBRE_PRODUCTO = "Pulpa de Mora"
EXISTENCIA_INICIAL = 10


class ConfigPruebas:
    TESTING = True
    SECRET_KEY = "clave-solo-para-pruebas"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BCRYPT_LOG_ROUNDS = 4  # hash rápido: solo para que las pruebas no tarden


@pytest.fixture
def app():
    app = create_app(ConfigPruebas)

    with app.app_context():
        db.create_all()

        admin = Usuario(nombre="Admin Prueba", email=EMAIL_ADMIN, rol=ROL_ADMINISTRADOR)
        admin.establecer_password(PASSWORD_ADMIN)

        gestor = Usuario(nombre="Gestor Prueba", email=EMAIL_GESTOR, rol=ROL_GESTOR_PEDIDOS)
        gestor.establecer_password(PASSWORD_GESTOR)

        producto = Producto(
            nombre=NOMBRE_PRODUCTO,
            presentacion="Bolsa 500g",
            unidad_medida="unidad",
            precio=8500,
            existencia_disponible=EXISTENCIA_INICIAL,
            umbral_minimo=5,
        )

        db.session.add_all([admin, gestor, producto])
        db.session.commit()

    yield app

    with app.app_context():
        db.drop_all()


@pytest.fixture
def cliente(app):
    return app.test_client()
