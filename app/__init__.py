from flask import Flask

from config import Config
from app.extensions import db, bcrypt, login_manager
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
        return Usuario.query.get(int(usuario_id))

    from app.auth.routes import auth_bp
    from app.main.routes import main_bp
    from app.productos.routes import productos_bp
    from app.inventario.routes import inventario_bp
    from app.pedidos.routes import pedidos_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(productos_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(pedidos_bp)

    app.add_template_filter(a_hora_negocio, "hora_local")

    return app
