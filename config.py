import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # En producción, SECRET_KEY debe venir de una variable de entorno real,
    # nunca quedar escrita en el código fuente.
    SECRET_KEY = os.environ.get("SECRET_KEY", "clave-de-desarrollo-cambiar-en-produccion")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'pulpas.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
