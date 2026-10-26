from flask import Flask

from config import Config
from app.extensions import db, bcrypt, login_manager
from app.formato import moneda
from app.seguridad import obtener_token_csrf, validar_csrf
from app.tiempo import a_hora_negocio


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    from app.models import Usuario

    @login_manager.user_loader
    def cargar_usuario(usuario_id):
        usuario = db.session.get(Usuario, int(usuario_id))
        # HU22: si un administrador desactiva a alguien, su sesión abierta
        # deja de valer de inmediato (no solo su próximo inicio de sesión).
        return usuario if usuario is not None and usuario.activo else None

    app.before_request(validar_csrf)
    app.jinja_env.globals["csrf_token"] = obtener_token_csrf

    from app.auth.routes import auth_bp
    from app.main.routes import main_bp
    from app.productos.routes import productos_bp
    from app.inventario.routes import inventario_bp
    from app.pedidos.routes import pedidos_bp
    from app.reportes.routes import reportes_bp
    from app.usuarios.routes import usuarios_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(productos_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(usuarios_bp)

    app.add_template_filter(a_hora_negocio, "hora_local")
    app.add_template_filter(moneda, "moneda")

    return app
