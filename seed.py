"""Crea las tablas de la base de datos y datos iniciales para poder
probar el sistema de inmediato: un administrador, un gestor de pedidos
y un par de productos de ejemplo.

Uso:
    python seed.py
"""
from app import create_app
from app.extensions import db
from app.models import Usuario, Producto, ROL_ADMINISTRADOR, ROL_GESTOR_PEDIDOS

app = create_app()

with app.app_context():
    db.create_all()

    if Usuario.query.filter_by(email="admin@pulpas.com").first() is None:
        admin = Usuario(nombre="Administrador Demo", email="admin@pulpas.com", rol=ROL_ADMINISTRADOR)
        admin.establecer_password("admin123")
        db.session.add(admin)

    if Usuario.query.filter_by(email="gestor@pulpas.com").first() is None:
        gestor = Usuario(nombre="Gestor Demo", email="gestor@pulpas.com", rol=ROL_GESTOR_PEDIDOS)
        gestor.establecer_password("gestor123")
        db.session.add(gestor)

    if Producto.query.count() == 0:
        db.session.add_all([
            Producto(nombre="Pulpa de Mora", presentacion="Bolsa 500g", unidad_medida="unidad",
                      precio=8500, existencia_disponible=20, umbral_minimo=5),
            Producto(nombre="Pulpa de Maracuyá", presentacion="Bolsa 500g", unidad_medida="unidad",
                      precio=9000, existencia_disponible=15, umbral_minimo=5),
            Producto(nombre="Pulpa de Mango", presentacion="Bolsa 1kg", unidad_medida="unidad",
                      precio=15000, existencia_disponible=3, umbral_minimo=5),
        ])

    db.session.commit()
    print("Base de datos inicializada.")
    print("Admin  -> admin@pulpas.com / admin123")
    print("Gestor -> gestor@pulpas.com / gestor123")
