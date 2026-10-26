"""Protege los datos de demostración (seed_demo.py) y los ejemplos del guion
de la presentación: si alguien cambia los datos o las reglas, esta prueba
avisa antes de que la demo falle delante del profesor."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app import create_app
from app.errores import InventarioInsuficienteException, PedidoPosiblementeDuplicadoException
from app.extensions import db
from app.inventario.servicios import (
    describir_stock_bajo,
    listar_stock_bajo,
    registrar_merma,
    verificar_coherencia_inventario,
)
from app.models import (
    ESTADO_CANCELADO,
    ESTADO_CONFIRMADO,
    ESTADO_DESPACHADO,
    MOTIVO_MERMA_VENCIMIENTO,
    Pedido,
    Producto,
    Usuario,
)
from app.pedidos.dtos import ItemPedidoDTO, PedidoDTO
from app.pedidos.servicios import (
    cancelar_pedido,
    despachar_pedido,
    editar_pedido,
    listar_pedidos_del_dia,
    registrar_pedido,
)
from app.reportes.servicios import productos_mas_vendidos, resumen_ventas
from app.tiempo import hoy_negocio
from seed_demo import cargar_datos_demo
from tests.conftest import ConfigPruebas


@pytest.fixture
def demo():
    app = create_app(ConfigPruebas)
    with app.app_context():
        db.create_all()
        cargar_datos_demo()
        yield app


def _producto(nombre):
    return Producto.query.filter_by(nombre=nombre).one()


def _dto(cliente, items, fecha=None):
    gestor = Usuario.query.filter_by(email="gestor@pulpas.com").one()
    return PedidoDTO(
        cliente_nombre=cliente,
        fecha_entrega=fecha or hoy_negocio(),
        items=[ItemPedidoDTO(_producto(n).id, c) for n, c in items],
        usuario_id=gestor.id,
    )


def _pedido(cliente, estado=ESTADO_CONFIRMADO):
    return Pedido.query.filter_by(cliente_nombre=cliente, estado=estado).one()


def test_la_demo_carga_datos_variados_y_coherentes(demo):
    estados = [p.estado for p in Pedido.query.all()]
    assert (estados.count(ESTADO_DESPACHADO), estados.count(ESTADO_CONFIRMADO), estados.count(ESTADO_CANCELADO)) == (13, 6, 2)
    assert verificar_coherencia_inventario() == []
    assert Usuario.query.filter_by(activo=False).count() == 1  # el ex empleado, para mostrar HU22
    # Dos productos en stock bajo para mostrar HU15 sin hacer nada
    assert {p.nombre for p in listar_stock_bajo()} == {"Pulpa de Mango", "Pulpa de Fresa"}


def test_pedidos_de_hoy_y_de_manana(demo):
    hoy = hoy_negocio()
    assert len(listar_pedidos_del_dia(hoy)) == 4
    assert len(listar_pedidos_del_dia(hoy + timedelta(days=1))) == 2


def test_los_reportes_tienen_historia(demo):
    hoy = hoy_negocio()
    resumen = resumen_ventas(hoy - timedelta(days=9), hoy)
    assert resumen.numero_pedidos == 13 and resumen.total_ventas > 0
    assert {f.forma_pago for f in resumen.por_forma_pago} == {"efectivo", "transferencia", "tarjeta"}
    ranking = productos_mas_vendidos(hoy - timedelta(days=9), hoy)
    assert [p.nombre for p in ranking][0] == "Pulpa de Mora" and len(ranking) == 6
    assert resumen_ventas(hoy, hoy).numero_pedidos == 1  # hay una venta hoy


def test_la_demo_no_activa_la_alerta_de_duplicado_sola(demo):
    # Los pedidos de hoy se registraron "hace horas": repetir uno exige que
    # el duplicado se provoque a propósito durante la presentación.
    dto = _dto("Tienda La Esquina", [("Pulpa de Mora", 10), ("Pulpa de Maracuyá", 6)])
    registrar_pedido(dto)


def test_guion_en_vivo_pedido_nuevo_duplicado_y_sin_inventario(demo):
    nuevo = registrar_pedido(_dto("Supermercado El Ahorro", [("Pulpa de Mora", 6), ("Pulpa de Maracuyá", 4)]))
    assert nuevo.total == Decimal("87000")
    assert _producto("Pulpa de Mora").existencia_disponible == 18

    with pytest.raises(PedidoPosiblementeDuplicadoException):  # repetirlo en vivo
        registrar_pedido(_dto("Supermercado El Ahorro", [("Pulpa de Mora", 6), ("Pulpa de Maracuyá", 4)]))

    with pytest.raises(InventarioInsuficienteException) as error:  # Fresa: solo quedan 5
        registrar_pedido(_dto("Cliente Nuevo", [("Pulpa de Fresa", 8)]))
    assert "disponible 5" in str(error.value)


def test_guion_en_vivo_alerta_de_stock_bajo_al_tomar_un_pedido(demo):
    registrar_pedido(_dto("Cliente Nuevo", [("Pulpa de Lulo", 14)]))  # 21 - 14 = 7, umbral 8
    assert describir_stock_bajo([_producto("Pulpa de Lulo").id]) == [
        "Pulpa de Lulo (Bolsa 500g): quedan 7, umbral 8"
    ]


def test_guion_en_vivo_editar_despachar_cancelar_y_merma(demo):
    fresa_antes = _producto("Pulpa de Fresa").existencia_disponible
    mora = _producto("Pulpa de Mora")

    la_esquina = _pedido("Tienda La Esquina")  # editar: Mora 10 -> 14
    editar_pedido(la_esquina.id, _dto("Tienda La Esquina", [("Pulpa de Mora", 14), ("Pulpa de Maracuyá", 6)]))
    assert mora.existencia_disponible == 20 and mora.existencia_comprometida == 49

    marta = _pedido("Doña Marta Rodríguez")  # despachar con tarjeta
    assert despachar_pedido(marta.id, "tarjeta").estado == ESTADO_DESPACHADO

    manana = [p for p in Pedido.query.filter_by(cliente_nombre="Panadería San José", estado=ESTADO_CONFIRMADO)][0]
    cancelar_pedido(manana.id)  # libera Mora 8 y Fresa 5
    assert _producto("Pulpa de Fresa").existencia_disponible == fresa_antes + 5

    registrar_merma(_producto("Pulpa de Guanábana").id, 2, MOTIVO_MERMA_VENCIMIENTO,
                    Usuario.query.filter_by(email="admin@pulpas.com").one().id, "Vencida")
    assert _producto("Pulpa de Guanábana").existencia_disponible == 17
    assert verificar_coherencia_inventario() == []
