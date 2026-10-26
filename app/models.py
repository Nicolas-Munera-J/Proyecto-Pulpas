from datetime import datetime
from flask_login import UserMixin
from app.extensions import db, bcrypt
from app.tiempo import ahora_utc

# Roles del sistema (HU20/HU21/HU22)
ROL_ADMINISTRADOR = "administrador"
ROL_GESTOR_PEDIDOS = "gestor_pedidos"

# Tipos de movimiento de inventario (HU08, y HU16 más adelante)
TIPO_ENTRADA = "entrada"
TIPO_MERMA = "merma"

# Estados del pedido (sección 6.2: confirmado -> despachado | cancelado).
# No existe un estado intermedio de espera: si no hay inventario, el pedido no se toma.
ESTADO_CONFIRMADO = "confirmado"
ESTADO_DESPACHADO = "despachado"
ESTADO_CANCELADO = "cancelado"

# Medio por el que llegó el pedido (se filtra en HU07, Sprint 5).
CANAL_WHATSAPP = "whatsapp"
CANAL_VERBAL = "verbal"
CANAL_OTRO = "otro"
CANALES = (CANAL_WHATSAPP, CANAL_VERBAL, CANAL_OTRO)


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


class Pedido(db.Model):
    """HU02 (registro) / HU01 (pedidos del día) / HU09 (duplicados).

    Solo se guarda el nombre y un contacto opcional del cliente: el mínimo
    necesario para despachar (Ley 1581 de 2012). No hay tabla de clientes
    porque ninguna historia priorizada la necesita.
    """

    __tablename__ = "pedidos"

    id = db.Column(db.Integer, primary_key=True)
    cliente_nombre = db.Column(db.String(120), nullable=False, index=True)
    cliente_contacto = db.Column(db.String(80), nullable=True)
    canal = db.Column(db.String(20), nullable=False, default=CANAL_WHATSAPP)
    estado = db.Column(db.String(20), nullable=False, default=ESTADO_CONFIRMADO, index=True)
    fecha_entrega = db.Column(db.Date, nullable=False, index=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    # La usa HU05 (Sprint 3). Se crea ya para no tener que alterar la tabla después.
    fecha_despacho = db.Column(db.DateTime, nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)

    usuario = db.relationship("Usuario")
    detalles = db.relationship(
        "DetallePedido",
        back_populates="pedido",
        cascade="all, delete-orphan",
        order_by="DetallePedido.id",
    )

    def __repr__(self):
        return f"<Pedido {self.id} {self.cliente_nombre} ({self.estado})>"


class DetallePedido(db.Model):
    """Línea de un pedido: un producto y su cantidad.

    precio_unitario guarda el precio vigente al registrar, para que un cambio
    posterior en el catálogo no altere pedidos ya tomados (lo usa HU10, Sprint 4).
    """

    __tablename__ = "detalles_pedido"

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedidos.id"), nullable=False, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    pedido = db.relationship("Pedido", back_populates="detalles")
    producto = db.relationship("Producto")
