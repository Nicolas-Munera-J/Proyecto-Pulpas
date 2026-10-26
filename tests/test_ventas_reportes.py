"""Pruebas del Sprint 4: HU10 (total automático), HU11 (forma de pago),
HU17 (ventas por periodo) y HU18 (productos más vendidos).

Criterios de aceptación (Dado / Cuando / Entonces) verificados:
- HU10: dado un pedido de 2 × $8.500 y 3 × $9.000, el total es $44.000.
- HU11: al despachar se exige una forma de pago; sin ella el pedido no sale.
- HU17: dado pedidos despachados en un periodo, el reporte muestra el total de
  ventas y el número de pedidos; solo cuentan los despachados.
- HU18: los productos se listan de mayor a menor cantidad vendida.
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text

from app.errores import DatosInvalidosException
from app.extensions import db
from app.formato import moneda
from app.migraciones import agregar_columnas_faltantes
from app.models import (
    ESTADO_CONFIRMADO,
    ESTADO_DESPACHADO,
    FORMA_PAGO_EFECTIVO,
    FORMA_PAGO_TRANSFERENCIA,
    Pedido,
    Producto,
)
from app.pedidos.servicios import cancelar_pedido, despachar_pedido, editar_pedido
from app.reportes.servicios import productos_mas_vendidos, resumen_ventas
from app.tiempo import hoy_negocio
from tests.conftest import (
    EMAIL_ADMIN,
    EXISTENCIA_INICIAL,
    NOMBRE_PRODUCTO,
    NOMBRE_PRODUCTO_2,
    PASSWORD_ADMIN,
)
from tests.test_ciclo_pedido import _crear
from tests.test_pedidos import _dto, _existencias, _formulario, _ids, _iniciar_sesion_gestor


# --------------------------------------------------------------------------
# Ayudas
# --------------------------------------------------------------------------
def _vender(app, items, cliente="Cliente", forma=FORMA_PAGO_EFECTIVO, despachado_utc=None):
    """Crea un pedido, lo despacha y (opcional) fija el momento del despacho."""
    pedido_id = _crear(app, items, cliente=cliente)
    with app.app_context():
        despachar_pedido(pedido_id, forma)
        if despachado_utc is not None:
            db.session.get(Pedido, pedido_id).fecha_despacho = despachado_utc
            db.session.commit()
    return pedido_id


def _iniciar_sesion_admin(cliente):
    r = cliente.post("/login", data={"email": EMAIL_ADMIN, "password": PASSWORD_ADMIN})
    assert r.status_code == 302


# --------------------------------------------------------------------------
# HU10 - Total automático del pedido
# --------------------------------------------------------------------------
def test_total_es_la_suma_de_cantidad_por_precio(app):
    mora, maracuya, _ = _ids(app)  # $8.500 y $9.000
    pedido_id = _crear(app, [(mora, 2), (maracuya, 3)])

    with app.app_context():
        pedido = db.session.get(Pedido, pedido_id)
        assert [d.subtotal for d in pedido.detalles] == [Decimal("17000"), Decimal("27000")]
        assert pedido.total == Decimal("44000")


def test_total_se_recalcula_al_editar_y_conserva_precio_de_lineas_existentes(app):
    mora, maracuya, gestor = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])

    with app.app_context():
        Producto.query.get(mora).precio = 10000  # el catálogo sube de precio
        db.session.commit()

        # Mora conserva $8.500; Maracuyá es una línea nueva y entra a $9.000.
        editar_pedido(pedido_id, _dto(gestor, [(mora, 3), (maracuya, 1)]))
        assert db.session.get(Pedido, pedido_id).total == Decimal("3") * 8500 + Decimal("9000")


def test_cambio_de_precio_en_el_catalogo_no_altera_pedidos_ya_tomados(app):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])

    with app.app_context():
        Producto.query.get(mora).precio = 99999
        db.session.commit()
        assert db.session.get(Pedido, pedido_id).total == Decimal("17000")


def test_formato_de_moneda_en_pesos_colombianos():
    assert moneda(44000) == "$ 44.000"
    assert moneda(Decimal("1234567.50")) == "$ 1.234.568"
    assert moneda(0) == "$ 0"
    assert moneda(None) == "$ 0"


def test_vista_de_pedidos_muestra_subtotales_y_total(app, cliente):
    mora, maracuya, _ = _ids(app)
    _crear(app, [(mora, 2), (maracuya, 3)])
    _iniciar_sesion_gestor(cliente)

    html = cliente.get("/pedidos/hoy").data.decode()

    assert "$ 17.000" in html and "$ 27.000" in html  # subtotales
    assert "$ 44.000" in html  # total


def test_formulario_entrega_los_precios_para_la_vista_previa_del_total(app, cliente):
    _iniciar_sesion_gestor(cliente)

    html = cliente.get("/pedidos/nuevo").data.decode()

    assert 'data-precio="8500' in html and 'id="totalPedido"' in html


# --------------------------------------------------------------------------
# HU11 - Forma de pago al despachar
# --------------------------------------------------------------------------
def test_despachar_registra_la_forma_de_pago(app):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])

    with app.app_context():
        pedido = despachar_pedido(pedido_id, FORMA_PAGO_TRANSFERENCIA)
        assert pedido.estado == ESTADO_DESPACHADO
        assert db.session.get(Pedido, pedido_id).forma_pago == FORMA_PAGO_TRANSFERENCIA


@pytest.mark.parametrize("forma_invalida", ["", None, "bitcoin"])
def test_despachar_sin_forma_de_pago_valida_se_rechaza_sin_cambios(app, forma_invalida):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])

    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            despachar_pedido(pedido_id, forma_invalida)
        pedido = db.session.get(Pedido, pedido_id)
        assert pedido.estado == ESTADO_CONFIRMADO
        assert pedido.forma_pago is None and pedido.fecha_despacho is None

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 2, 2)


def test_interfaz_despacha_con_forma_de_pago_y_rechaza_sin_ella(app, cliente):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])
    _iniciar_sesion_gestor(cliente)

    sin_pago = cliente.post(f"/pedidos/{pedido_id}/despachar", data={}, follow_redirects=True)
    assert b"forma de pago" in sin_pago.data
    with app.app_context():
        assert db.session.get(Pedido, pedido_id).estado == ESTADO_CONFIRMADO

    con_pago = cliente.post(
        f"/pedidos/{pedido_id}/despachar", data={"forma_pago": "tarjeta"}, follow_redirects=True
    )
    assert b"despachado." in con_pago.data
    with app.app_context():
        assert db.session.get(Pedido, pedido_id).forma_pago == "tarjeta"


def test_vista_de_pedidos_pide_la_forma_de_pago_al_despachar(app, cliente):
    mora, _, _ = _ids(app)
    _crear(app, [(mora, 1)])
    _iniciar_sesion_gestor(cliente)

    html = cliente.get("/pedidos/hoy").data.decode()

    assert 'name="forma_pago"' in html and "efectivo" in html and "transferencia" in html


# --------------------------------------------------------------------------
# HU17 - Reporte de ventas por periodo
# --------------------------------------------------------------------------
def test_resumen_cuenta_solo_pedidos_despachados(app):
    mora, maracuya, _ = _ids(app)
    _vender(app, [(mora, 2)], cliente="A", forma=FORMA_PAGO_EFECTIVO)  # $17.000
    _vender(app, [(maracuya, 1)], cliente="B", forma=FORMA_PAGO_TRANSFERENCIA)  # $9.000
    _crear(app, [(mora, 1)], cliente="Confirmado, sin despachar")
    cancelado = _crear(app, [(maracuya, 2)], cliente="Cancelado")
    with app.app_context():
        cancelar_pedido(cancelado)

    hoy = hoy_negocio()
    with app.app_context():
        resumen = resumen_ventas(hoy, hoy)

        assert resumen.numero_pedidos == 2
        assert resumen.total_ventas == Decimal("26000")
        assert [(f.forma_pago, f.numero_pedidos, f.total) for f in resumen.por_forma_pago] == [
            (FORMA_PAGO_EFECTIVO, 1, Decimal("17000")),
            (FORMA_PAGO_TRANSFERENCIA, 1, Decimal("9000")),
        ]


def test_resumen_solo_incluye_el_rango_de_fechas_pedido(app):
    mora, _, _ = _ids(app)
    # Mediodía en Bogotá = 17:00 UTC
    _vender(app, [(mora, 1)], cliente="Marzo 9", despachado_utc=datetime(2026, 3, 9, 17, 0))
    _vender(app, [(mora, 2)], cliente="Marzo 10", despachado_utc=datetime(2026, 3, 10, 17, 0))
    _vender(app, [(mora, 3)], cliente="Marzo 12", despachado_utc=datetime(2026, 3, 12, 17, 0))

    with app.app_context():
        resumen = resumen_ventas(datetime(2026, 3, 10).date(), datetime(2026, 3, 11).date())

        assert resumen.numero_pedidos == 1
        assert resumen.total_ventas == Decimal("17000")


def test_periodo_se_mide_en_hora_de_colombia_no_en_utc(app):
    mora, _, _ = _ids(app)
    d10, d11 = datetime(2026, 3, 10).date(), datetime(2026, 3, 11).date()
    # 23:30 del 10 de marzo en Bogotá = 04:30 UTC del 11. Sigue siendo venta del 10.
    _vender(app, [(mora, 1)], cliente="Noche", despachado_utc=datetime(2026, 3, 11, 4, 30))
    # 00:30 del 11 de marzo en Bogotá = 05:30 UTC del 11. Ya es venta del 11.
    _vender(app, [(mora, 2)], cliente="Madrugada", despachado_utc=datetime(2026, 3, 11, 5, 30))

    with app.app_context():
        assert resumen_ventas(d10, d10).total_ventas == Decimal("8500")
        assert resumen_ventas(d11, d11).total_ventas == Decimal("17000")


def test_resumen_sin_ventas_devuelve_ceros(app):
    hoy = hoy_negocio()
    with app.app_context():
        resumen = resumen_ventas(hoy, hoy)
        assert (resumen.numero_pedidos, resumen.total_ventas, resumen.por_forma_pago) == (
            0, Decimal("0"), [],
        )


def test_periodo_invalido_se_rechaza(app):
    hoy = hoy_negocio()
    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            resumen_ventas(hoy, hoy - timedelta(days=1))
        with pytest.raises(DatosInvalidosException):
            resumen_ventas(None, hoy)


def test_cambio_de_precio_no_altera_ventas_ya_realizadas(app):
    mora, _, _ = _ids(app)
    _vender(app, [(mora, 2)])

    with app.app_context():
        Producto.query.get(mora).precio = 50000
        db.session.commit()
        assert resumen_ventas(hoy_negocio(), hoy_negocio()).total_ventas == Decimal("17000")


def test_interfaz_reporte_de_ventas_para_administrador(app, cliente):
    mora, maracuya, _ = _ids(app)
    _vender(app, [(mora, 2), (maracuya, 3)])  # $44.000
    _iniciar_sesion_admin(cliente)
    hoy = hoy_negocio().isoformat()

    html = cliente.get(f"/reportes/ventas?desde={hoy}&hasta={hoy}").data.decode()
    assert "$ 44.000" in html and "Efectivo" in html

    assert cliente.get("/reportes/ventas").status_code == 200  # periodo predeterminado

    invalido = cliente.get(f"/reportes/ventas?desde={hoy}&hasta=2020-01-01")
    assert invalido.status_code == 200 and b"posterior" in invalido.data

    mal_escrita = cliente.get("/reportes/ventas?desde=ayer")
    assert mal_escrita.status_code == 200


def test_reportes_solo_para_administrador(app, cliente):
    rutas = ("/reportes/ventas", "/reportes/productos-mas-vendidos")

    for ruta in rutas:  # sin sesión
        r = cliente.get(ruta)
        assert r.status_code == 302 and "/login" in r.headers["Location"]

    _iniciar_sesion_gestor(cliente)
    for ruta in rutas:  # gestor de pedidos: el rol se valida en el servidor
        assert cliente.get(ruta).status_code == 403


# --------------------------------------------------------------------------
# HU18 - Productos más vendidos
# --------------------------------------------------------------------------
def test_ranking_ordena_de_mayor_a_menor_y_suma_varios_pedidos(app):
    mora, maracuya, _ = _ids(app)
    _vender(app, [(mora, 4)], cliente="A")
    _vender(app, [(mora, 3), (maracuya, 5)], cliente="B")

    hoy = hoy_negocio()
    with app.app_context():
        ranking = productos_mas_vendidos(hoy, hoy)

        assert [(p.nombre, p.cantidad) for p in ranking] == [
            (NOMBRE_PRODUCTO, 7),
            (NOMBRE_PRODUCTO_2, 5),
        ]
        assert ranking[0].ingresos == Decimal("7") * 8500


def test_ranking_excluye_confirmados_y_cancelados(app):
    mora, maracuya, _ = _ids(app)
    _vender(app, [(mora, 1)])
    _crear(app, [(maracuya, 5)], cliente="Sin despachar")
    cancelado = _crear(app, [(maracuya, 2)], cliente="Cancelado")
    with app.app_context():
        cancelar_pedido(cancelado)

    hoy = hoy_negocio()
    with app.app_context():
        assert [p.nombre for p in productos_mas_vendidos(hoy, hoy)] == [NOMBRE_PRODUCTO]


def test_ranking_con_empate_ordena_por_nombre(app):
    mora, maracuya, _ = _ids(app)
    _vender(app, [(mora, 2), (maracuya, 2)])

    hoy = hoy_negocio()
    with app.app_context():
        nombres = [p.nombre for p in productos_mas_vendidos(hoy, hoy)]
        assert nombres == [NOMBRE_PRODUCTO_2, NOMBRE_PRODUCTO]  # Maracuyá antes que Mora


def test_ranking_respeta_el_periodo_y_vacio_devuelve_lista_vacia(app):
    mora, _, _ = _ids(app)
    _vender(app, [(mora, 2)], despachado_utc=datetime(2026, 3, 10, 17, 0))

    with app.app_context():
        assert productos_mas_vendidos(datetime(2026, 3, 11).date(), datetime(2026, 3, 12).date()) == []
        assert len(productos_mas_vendidos(datetime(2026, 3, 10).date(), datetime(2026, 3, 10).date())) == 1


def test_interfaz_productos_mas_vendidos_para_administrador(app, cliente):
    mora, maracuya, _ = _ids(app)
    _vender(app, [(mora, 5), (maracuya, 2)])
    _iniciar_sesion_admin(cliente)
    hoy = hoy_negocio().isoformat()

    html = cliente.get(f"/reportes/productos-mas-vendidos?desde={hoy}&hasta={hoy}").data.decode()

    assert html.index(NOMBRE_PRODUCTO) < html.index(NOMBRE_PRODUCTO_2)  # Mora (5) antes que Maracuyá (2)
    assert "$ 42.500" in html  # 5 × $8.500


# --------------------------------------------------------------------------
# Migración de bases ya creadas (columna forma_pago)
# --------------------------------------------------------------------------
def test_migracion_agrega_la_columna_a_una_base_del_sprint_anterior(app):
    motor = create_engine("sqlite://")
    with motor.begin() as conexion:
        conexion.execute(text("CREATE TABLE pedidos (id INTEGER PRIMARY KEY, cliente_nombre TEXT)"))
        conexion.execute(text("INSERT INTO pedidos (cliente_nombre) VALUES ('Existente')"))

    assert agregar_columnas_faltantes(motor) == ["pedidos.forma_pago"]
    assert "forma_pago" in {c["name"] for c in inspect(motor).get_columns("pedidos")}
    with motor.connect() as conexion:  # no pierde los datos que ya había
        assert conexion.execute(text("SELECT cliente_nombre FROM pedidos")).scalar() == "Existente"

    assert agregar_columnas_faltantes(motor) == []  # idempotente


def test_migracion_no_hace_nada_si_la_tabla_aun_no_existe(app):
    assert agregar_columnas_faltantes(create_engine("sqlite://")) == []
