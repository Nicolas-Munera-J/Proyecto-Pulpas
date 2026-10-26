"""Carga datos de DEMOSTRACIÓN para presentar el sistema con historia real:
productos, entradas de inventario, ventas de los últimos días, pedidos de hoy
y de mañana, pedidos cancelados, mermas y usuarios.

Todo se crea con las mismas funciones que usa la aplicación (registrar_pedido,
despachar_pedido, registrar_merma...), así que el inventario queda coherente
con los pedidos. Después solo se ajustan las fechas para que haya historia.

Uso:
    python seed_demo.py --reiniciar     # BORRA todo pulpas.db y carga la demo

Cuentas que quedan:
    admin@pulpas.com  / admin123      (Administrador)
    gestor@pulpas.com / gestor123     (Gestor de pedidos)
    camila@pulpas.com / camila123     (Gestor de pedidos)
    pedro@pulpas.com  / pedro123      (DESACTIVADO: ex empleado, para mostrar HU22)
"""
import argparse
import sys
from datetime import datetime, time, timedelta, timezone

from app import create_app
from app.extensions import db
from app.inventario.servicios import registrar_entrada_inventario, registrar_merma
from app.models import (
    CANAL_OTRO,
    CANAL_VERBAL,
    CANAL_WHATSAPP,
    FORMA_PAGO_EFECTIVO,
    FORMA_PAGO_TARJETA,
    FORMA_PAGO_TRANSFERENCIA,
    MOTIVO_MERMA_DANIO,
    MOTIVO_MERMA_VENCIMIENTO,
    ROL_ADMINISTRADOR,
    ROL_GESTOR_PEDIDOS,
    Producto,
    Usuario,
)
from app.pedidos.dtos import ItemPedidoDTO, PedidoDTO
from app.pedidos.servicios import cancelar_pedido, despachar_pedido, registrar_pedido
from app.tiempo import ZONA_HORARIA_NEGOCIO, ahora_utc, hoy_negocio

# nombre, presentación, precio, umbral mínimo, entradas [(días atrás, cantidad)]
PRODUCTOS = [
    ("Pulpa de Mora", "Bolsa 500g", 8500, 10, [(14, 100), (6, 50)]),
    ("Pulpa de Maracuyá", "Bolsa 500g", 9000, 10, [(14, 100)]),
    ("Pulpa de Mango", "Bolsa 1kg", 15000, 8, [(14, 40)]),
    ("Pulpa de Lulo", "Bolsa 500g", 9500, 8, [(14, 50)]),
    ("Pulpa de Fresa", "Bolsa 500g", 8000, 10, [(14, 40), (6, 20)]),
    ("Pulpa de Guanábana", "Bolsa 500g", 11000, 5, [(14, 30)]),
]
MORA, MARACUYA, MANGO, LULO, FRESA, GUANABANA = range(6)  # posición en PRODUCTOS

# Ventas ya despachadas: (días atrás, hora local, cliente, contacto, canal, [(producto, cantidad)], forma de pago)
VENTAS_PASADAS = [
    (9, "10:30", "Restaurante El Fogón", "310 555 0142", CANAL_WHATSAPP, [(MORA, 12), (MARACUYA, 10)], FORMA_PAGO_TRANSFERENCIA),
    (8, "09:15", "Panadería San José", "320 555 0177", CANAL_VERBAL, [(MORA, 8), (FRESA, 6)], FORMA_PAGO_EFECTIVO),
    (8, "16:40", "Doña Lucía Gómez", "300 555 0188", CANAL_WHATSAPP, [(LULO, 4), (GUANABANA, 3)], FORMA_PAGO_EFECTIVO),
    (7, "11:00", "Heladería Frutilandia", "315 555 0121", CANAL_WHATSAPP, [(MANGO, 10), (FRESA, 12), (MORA, 6)], FORMA_PAGO_TRANSFERENCIA),
    (6, "14:20", "Cafetería Aroma", "300 555 0133", CANAL_OTRO, [(MARACUYA, 8), (LULO, 6)], FORMA_PAGO_TARJETA),
    (5, "10:05", "Hotel Los Almendros", "311 555 0199", CANAL_WHATSAPP, [(MORA, 20), (MARACUYA, 15), (MANGO, 8), (GUANABANA, 4)], FORMA_PAGO_TRANSFERENCIA),
    (4, "09:45", "Juan Camilo Restrepo", "300 555 0155", CANAL_VERBAL, [(MORA, 4)], FORMA_PAGO_EFECTIVO),
    (3, "15:30", "Tienda La Esquina", "322 555 0111", CANAL_WHATSAPP, [(MORA, 10), (FRESA, 8)], FORMA_PAGO_EFECTIVO),
    (3, "17:10", "Restaurante El Fogón", "310 555 0142", CANAL_WHATSAPP, [(MARACUYA, 12), (LULO, 5)], FORMA_PAGO_TRANSFERENCIA),
    (2, "11:25", "Panadería San José", "320 555 0177", CANAL_VERBAL, [(MORA, 10), (MANGO, 4)], FORMA_PAGO_EFECTIVO),
    (1, "10:40", "Heladería Frutilandia", "315 555 0121", CANAL_WHATSAPP, [(FRESA, 15), (MANGO, 6), (MARACUYA, 6)], FORMA_PAGO_TARJETA),
    (1, "16:55", "Doña Lucía Gómez", "300 555 0188", CANAL_WHATSAPP, [(MORA, 5), (GUANABANA, 2)], FORMA_PAGO_EFECTIVO),
]

# Pedidos cancelados: (días atrás, hora local, cliente, contacto, canal, items)
PEDIDOS_CANCELADOS = [
    (4, "08:50", "Cafetería Aroma", "300 555 0133", CANAL_VERBAL, [(MORA, 6)]),
    (1, "12:15", "Juan Camilo Restrepo", "300 555 0155", CANAL_WHATSAPP, [(LULO, 3)]),
]

# Pedidos confirmados: (días hacia adelante, horas desde que se registró, cliente, contacto, canal, items)
PEDIDOS_PENDIENTES = [
    (0, 5, "Tienda La Esquina", "322 555 0111", CANAL_WHATSAPP, [(MORA, 10), (MARACUYA, 6)]),
    (0, 4, "Restaurante El Fogón", "310 555 0142", CANAL_WHATSAPP, [(MORA, 12), (LULO, 6), (GUANABANA, 2)]),
    (0, 3, "Doña Marta Rodríguez", "300 555 0166", CANAL_VERBAL, [(FRESA, 4), (MARACUYA, 3)]),
    (0, 2, "Cafetería Aroma", "300 555 0133", CANAL_OTRO, [(MANGO, 2), (LULO, 4)]),
    (1, 3, "Hotel Los Almendros", "311 555 0199", CANAL_WHATSAPP, [(MORA, 15), (MARACUYA, 10), (MANGO, 3)]),
    (1, 1, "Panadería San José", "320 555 0177", CANAL_VERBAL, [(MORA, 8), (FRESA, 5)]),
]

# Mermas: (días atrás, producto, cantidad, motivo, observación)
MERMAS = [
    (6, MORA, 3, MOTIVO_MERMA_DANIO, "Bolsas rotas en el transporte"),
    (3, FRESA, 5, MOTIVO_MERMA_VENCIMIENTO, "Lote vencido de la semana pasada"),
    (2, LULO, 2, MOTIVO_MERMA_DANIO, "Se congeló mal el lote"),
]


def _local_a_utc(dias_atras: int, hora: str) -> datetime:
    """Día (hoy - dias_atras) a la hora local "HH:MM" de Colombia, en UTC."""
    dia = hoy_negocio() - timedelta(days=dias_atras)
    horas, minutos = (int(x) for x in hora.split(":"))
    local = datetime.combine(dia, time(horas, minutos), tzinfo=ZONA_HORARIA_NEGOCIO)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _crear_usuario(nombre, email, password, rol, activo=True):
    usuario = Usuario(nombre=nombre, email=email, rol=rol, activo=activo)
    usuario.establecer_password(password)
    db.session.add(usuario)
    return usuario


def _registrar(cliente, contacto, canal, items, fecha_entrega, usuario_id, productos):
    dto = PedidoDTO(
        cliente_nombre=cliente,
        cliente_contacto=contacto,
        canal=canal,
        fecha_entrega=fecha_entrega,
        items=[ItemPedidoDTO(productos[p].id, c) for p, c in items],
        usuario_id=usuario_id,
    )
    return registrar_pedido(dto, confirmar_duplicado=True)


def cargar_datos_demo() -> dict:
    """Carga la demo en una base VACÍA (con las tablas ya creadas)."""
    admin = _crear_usuario("Administrador Demo", "admin@pulpas.com", "admin123", ROL_ADMINISTRADOR)
    gestor = _crear_usuario("Gestor Demo", "gestor@pulpas.com", "gestor123", ROL_GESTOR_PEDIDOS)
    camila = _crear_usuario("Camila Torres", "camila@pulpas.com", "camila123", ROL_GESTOR_PEDIDOS)
    _crear_usuario("Pedro Ramírez (ex empleado)", "pedro@pulpas.com", "pedro123", ROL_GESTOR_PEDIDOS, activo=False)
    productos = []
    for nombre, presentacion, precio, umbral, _ in PRODUCTOS:
        productos.append(Producto(nombre=nombre, presentacion=presentacion, unidad_medida="unidad",
                                  precio=precio, existencia_disponible=0, umbral_minimo=umbral))
    db.session.add_all(productos)
    db.session.commit()
    gestoras = [gestor.id, camila.id]

    # 1) Entradas de inventario (HU08), con fecha de hace unos días
    for indice, (_, _, _, _, entradas) in enumerate(PRODUCTOS):
        for dias_atras, cantidad in entradas:
            movimiento = registrar_entrada_inventario(
                productos[indice].id, cantidad, admin.id, "Compra a proveedor" if dias_atras > 10 else "Reposición semanal"
            )
            movimiento.fecha = _local_a_utc(dias_atras, "08:00")
    db.session.commit()

    # 2) Ventas ya despachadas, repartidas en los últimos días (HU02, HU05, HU11, HU17, HU18)
    for numero, (dias_atras, hora, cliente, contacto, canal, items, forma_pago) in enumerate(VENTAS_PASADAS):
        pedido = _registrar(cliente, contacto, canal, items, hoy_negocio(), gestoras[numero % 2], productos)
        despachar_pedido(pedido.id, forma_pago)
        pedido.fecha_entrega = hoy_negocio() - timedelta(days=dias_atras)
        pedido.fecha_despacho = _local_a_utc(dias_atras, hora)
        pedido.fecha_creacion = pedido.fecha_despacho - timedelta(hours=3)
    db.session.commit()

    # 3) Pedidos cancelados (HU06)
    for numero, (dias_atras, hora, cliente, contacto, canal, items) in enumerate(PEDIDOS_CANCELADOS):
        pedido = _registrar(cliente, contacto, canal, items, hoy_negocio(), gestoras[numero % 2], productos)
        cancelar_pedido(pedido.id)
        pedido.fecha_entrega = hoy_negocio() - timedelta(days=dias_atras)
        pedido.fecha_creacion = _local_a_utc(dias_atras, hora)
    db.session.commit()

    # 4) Mermas (HU16)
    for dias_atras, producto, cantidad, motivo, observacion in MERMAS:
        merma = registrar_merma(productos[producto].id, cantidad, motivo, admin.id, observacion)
        merma.fecha = _local_a_utc(dias_atras, "09:30")
    db.session.commit()

    # 5) Venta despachada hoy, para que el reporte de hoy no salga vacío
    pedido = _registrar("Juan Camilo Restrepo", "300 555 0155", CANAL_VERBAL, [(MORA, 3), (LULO, 2)],
                        hoy_negocio(), gestor.id, productos)
    despachar_pedido(pedido.id, FORMA_PAGO_EFECTIVO)

    # 6) Pedidos confirmados de hoy y de mañana (HU01, HU03, HU05, HU06)
    for numero, (dias_adelante, horas_atras, cliente, contacto, canal, items) in enumerate(PEDIDOS_PENDIENTES):
        pedido = _registrar(cliente, contacto, canal, items, hoy_negocio() + timedelta(days=dias_adelante),
                            gestoras[numero % 2], productos)
        pedido.fecha_creacion = ahora_utc() - timedelta(hours=horas_atras)  # fuera de la ventana de duplicados
    db.session.commit()

    return {
        "usuarios": Usuario.query.count(),
        "productos": Producto.query.count(),
        "ventas_pasadas": len(VENTAS_PASADAS) + 1,
        "pendientes": len(PEDIDOS_PENDIENTES),
        "cancelados": len(PEDIDOS_CANCELADOS),
        "mermas": len(MERMAS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga datos de demostración en pulpas.db")
    parser.add_argument("--reiniciar", action="store_true", help="BORRA toda la base de datos y carga la demo")
    parser.add_argument("--si", action="store_true", help="no pedir confirmación")
    argumentos = parser.parse_args()

    if not argumentos.reiniciar:
        print("Este script carga la demo desde cero y por eso borra la base de datos actual.")
        print("Si estás seguro, ejecuta:  python seed_demo.py --reiniciar")
        return 1
    if not argumentos.si and input("Esto BORRA todos los datos de pulpas.db. Escribe SI para continuar: ").strip() != "SI":
        print("Cancelado: no se cambió nada.")
        return 1

    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        resumen = cargar_datos_demo()

    print("Demo cargada:", ", ".join(f"{valor} {nombre}" for nombre, valor in resumen.items()))
    print(__doc__.split("Cuentas que quedan:")[1].rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
