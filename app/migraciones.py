"""Migración mínima para bases de datos ya creadas.

El proyecto no usa Alembic. db.create_all() crea las tablas que faltan pero
NO agrega columnas nuevas a tablas existentes, así que quien ya tenga un
pulpas.db de un sprint anterior necesita este paso (lo ejecuta seed.py).
"""
from sqlalchemy import inspect, text

# (tabla, columna, tipo SQL) agregadas después del Sprint 1 a tablas que ya existían.
COLUMNAS_NUEVAS = [
    ("pedidos", "forma_pago", "VARCHAR(20)"),  # Sprint 4 - HU11
    ("movimientos_inventario", "motivo", "VARCHAR(20)"),  # Sprint 5 - HU16
]


def agregar_columnas_faltantes(engine) -> list:
    """Agrega las columnas de COLUMNAS_NUEVAS que no existan. Devuelve las
    que agregó. Es idempotente: ejecutarla de nuevo no hace nada."""
    agregadas = []
    inspector = inspect(engine)
    for tabla, columna, tipo in COLUMNAS_NUEVAS:
        if tabla not in inspector.get_table_names():
            continue  # create_all() la creará completa
        existentes = {c["name"] for c in inspector.get_columns(tabla)}
        if columna not in existentes:
            with engine.begin() as conexion:
                conexion.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}"))
            agregadas.append(f"{tabla}.{columna}")
    return agregadas
