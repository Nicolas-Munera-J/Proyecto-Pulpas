from datetime import datetime
from flask_login import UserMixin
from app.extensions import db, bcrypt

# Roles del sistema (HU20/HU21/HU22)
ROL_ADMINISTRADOR = "administrador"
ROL_GESTOR_PEDIDOS = "gestor_pedidos"

# Tipos de movimiento de inventario (HU08, y HU16 más adelante)
TIPO_ENTRADA = "entrada"
TIPO_MERMA = "merma"


class Usuario(db.Model, UserMixin):
    """HU20 (login) / HU21 (logout) / HU22 (gestión de usuarios, Sprint 5)."""

    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(30), nullable=False, default=ROL_GESTOR_PEDIDOS)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    def establecer_password(self, password_plano: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password_plano).decode("utf-8")

    def verificar_password(self, password_plano: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password_plano)

    def es_administrador(self) -> bool:
        return self.rol == ROL_ADMINISTRADOR

    def __repr__(self):
        return f"<Usuario {self.email} ({self.rol})>"


class Producto(db.Model):
    """HU13 (catálogo) / HU14 (consulta de existencias) / HU04 (inventario comprometido)."""

    __tablename__ = "productos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    presentacion = db.Column(db.String(80), nullable=False)  # ej. "Bolsa 500g"
    unidad_medida = db.Column(db.String(20), nullable=False)  # ej. "unidad", "kg"
    precio = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    # El sistema diferencia existencia física (disponible + comprometida)
    # de existencia disponible para nuevos pedidos (sección 6.3 del documento).
    existencia_disponible = db.Column(db.Integer, nullable=False, default=0)
    existencia_comprometida = db.Column(db.Integer, nullable=False, default=0)

    umbral_minimo = db.Column(db.Integer, nullable=False, default=0)  # usado en HU15
    activo = db.Column(db.Boolean, nullable=False, default=True)

    movimientos = db.relationship("MovimientoInventario", backref="producto", lazy="dynamic")

    @property
    def existencia_total(self) -> int:
        return self.existencia_disponible + self.existencia_comprometida

    @property
    def stock_bajo(self) -> bool:
        return self.existencia_disponible <= self.umbral_minimo

    def __repr__(self):
        return f"<Producto {self.nombre} - disp:{self.existencia_disponible}>"


class MovimientoInventario(db.Model):
    """HU08 (registro de entradas). El estado 'Pendiente' de HU16 (mermas)
    se soportará sobre esta misma tabla más adelante, con tipo=TIPO_MERMA."""

    __tablename__ = "movimientos_inventario"

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # entrada | merma
    cantidad = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    observacion = db.Column(db.String(255), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)

    usuario = db.relationship("Usuario")
