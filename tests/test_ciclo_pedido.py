"""Pruebas del Sprint 3: HU04 (inventario comprometido), HU03 (edición),
HU05 (despacho) y HU06 (cancelación).

Regla de oro verificada en casi todas: después de cualquier operación,
verificar_coherencia_inventario() devuelve una lista vacía, es decir, lo
comprometido en los productos siempre es igual a lo que suman los pedidos
confirmados (mitigación del riesgo R-006).

Criterios de aceptación (Dado / Cuando / Entonces):
- HU06: dado un pedido confirmado de 4 unidades (6 disponibles, 4 comprometidas),
  cuando se cancela, entonces quedan 10 disponibles y 0 comprometidas.
- HU05: dado un pedido confirmado, cuando se despacha, entonces queda despachado
  con fecha y hora y las unidades comprometidas salen del inventario.
- HU03: dado un pedido confirmado, cuando se edita y hay inventario para el nuevo
  total, se actualiza; si no alcanza, no cambia nada. Un pedido despachado o
  cancelado no se puede editar.
"""
from datetime import timedelta

import pytest

from app.errores import (
    DatosInvalidosException,
    InventarioInsuficienteException,
    TransicionDePedidoInvalidaException,
)
from app.extensions import db
from app.inventario.servicios import (
    ajustar_compromiso,
    liberar_existencia_comprometida,
    verificar_coherencia_inventario,
)
from app.models import (
    FORMA_PAGO_EFECTIVO,
    ESTADO_CANCELADO,
    ESTADO_CONFIRMADO,
    ESTADO_DESPACHADO,
    Pedido,
    Producto,
)
from app.pedidos.servicios import (
    cancelar_pedido,
    despachar_pedido,
    editar_pedido,
    listar_pedidos_del_dia,
    registrar_pedido,
)
from app.tiempo import hoy_negocio
from tests.test_pedidos import (
    EXISTENCIA_INICIAL,
    EXISTENCIA_INICIAL_2,
    NOMBRE_PRODUCTO,
    NOMBRE_PRODUCTO_2,
    _dto,
    _existencias,
    _formulario,
    _ids,
    _iniciar_sesion_gestor,
)


def _coherente(app):
    with app.app_context():
        assert verificar_coherencia_inventario() == []


def _crear(app, items, cliente="Doña Marta", fecha=None):
    """Registra un pedido y devuelve su id."""
    _, _, gestor = _ids(app)
    with app.app_context():
        return registrar_pedido(_dto(gestor, items, cliente=cliente, fecha=fecha)).id


# --------------------------------------------------------------------------
# HU06 - Cancelación
# --------------------------------------------------------------------------
def test_cancelar_libera_el_inventario_comprometido(app):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 4)])
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 4, 4)

    with app.app_context():
        pedido = cancelar_pedido(pedido_id)
        assert pedido.estado == ESTADO_CANCELADO

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)
    _coherente(app)


def test_cancelar_pedido_con_varios_productos_libera_todos(app):
    mora, maracuya, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 3), (maracuya, 5)])

    with app.app_context():
        cancelar_pedido(pedido_id)

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)
    assert _existencias(app, NOMBRE_PRODUCTO_2) == (EXISTENCIA_INICIAL_2, 0)
    _coherente(app)


def test_inventario_liberado_queda_disponible_para_otro_pedido(app):
    # HU04: lo que libera una cancelación se puede volver a vender.
    mora, _, gestor = _ids(app)
    pedido_id = _crear(app, [(mora, EXISTENCIA_INICIAL)], cliente="Cliente A")

    with app.app_context():
        with pytest.raises(InventarioInsuficienteException):
            registrar_pedido(_dto(gestor, [(mora, 1)], cliente="Cliente B"))
        cancelar_pedido(pedido_id)
        registrar_pedido(_dto(gestor, [(mora, 1)], cliente="Cliente B"))

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 1, 1)
    _coherente(app)


def test_no_se_puede_cancelar_dos_veces_ni_un_despachado(app):
    mora, _, _ = _ids(app)
    cancelado = _crear(app, [(mora, 2)], cliente="Uno")
    despachado = _crear(app, [(mora, 3)], cliente="Dos")

    with app.app_context():
        cancelar_pedido(cancelado)
        despachar_pedido(despachado, FORMA_PAGO_EFECTIVO)
        with pytest.raises(TransicionDePedidoInvalidaException):
            cancelar_pedido(cancelado)  # no libera por segunda vez
        with pytest.raises(TransicionDePedidoInvalidaException):
            cancelar_pedido(despachado)  # ya salió, no se devuelve inventario

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 3, 0)
    _coherente(app)


def test_cancelar_pedido_inexistente_se_rechaza(app):
    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            cancelar_pedido(99999)


# --------------------------------------------------------------------------
# HU05 - Despacho
# --------------------------------------------------------------------------
def test_despachar_registra_fecha_y_descuenta_lo_comprometido(app):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 4)])

    with app.app_context():
        pedido = despachar_pedido(pedido_id, FORMA_PAGO_EFECTIVO)
        assert pedido.estado == ESTADO_DESPACHADO
        assert pedido.fecha_despacho is not None

    # La pulpa salió: la disponible no cambia (ya estaba descontada) y la
    # comprometida vuelve a 0. Existencia física = 6.
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 4, 0)
    _coherente(app)


def test_no_se_puede_despachar_dos_veces_ni_un_cancelado(app):
    mora, _, _ = _ids(app)
    uno = _crear(app, [(mora, 2)], cliente="Uno")
    dos = _crear(app, [(mora, 3)], cliente="Dos")

    with app.app_context():
        despachar_pedido(uno, FORMA_PAGO_EFECTIVO)
        cancelar_pedido(dos)
        with pytest.raises(TransicionDePedidoInvalidaException):
            despachar_pedido(uno, FORMA_PAGO_EFECTIVO)  # no descuenta dos veces
        with pytest.raises(TransicionDePedidoInvalidaException):
            despachar_pedido(dos, FORMA_PAGO_EFECTIVO)

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 2, 0)
    _coherente(app)


def test_pedido_despachado_sale_de_los_pedidos_del_dia(app):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 1)])

    with app.app_context():
        assert [p.id for p in listar_pedidos_del_dia()] == [pedido_id]
        despachar_pedido(pedido_id, FORMA_PAGO_EFECTIVO)
        assert listar_pedidos_del_dia() == []


# --------------------------------------------------------------------------
# HU03 - Edición antes del despacho
# --------------------------------------------------------------------------
def test_editar_aumentando_cantidad_compromete_solo_la_diferencia(app):
    mora, _, gestor = _ids(app)
    pedido_id = _crear(app, [(mora, 4)])

    with app.app_context():
        editar_pedido(pedido_id, _dto(gestor, [(mora, 9)]))

    # Hay 10 en total: con 9 comprometidas queda 1 disponible. Si se hubiera
    # verificado el total (9) contra lo disponible (6) se habría rechazado mal.
    assert _existencias(app, NOMBRE_PRODUCTO) == (1, 9)
    _coherente(app)


def test_editar_reduciendo_cantidad_libera_la_diferencia(app):
    mora, _, gestor = _ids(app)
    pedido_id = _crear(app, [(mora, 6)])

    with app.app_context():
        editar_pedido(pedido_id, _dto(gestor, [(mora, 2)]))

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 2, 2)
    _coherente(app)


def test_editar_quitando_un_producto_y_agregando_otro(app):
    mora, maracuya, gestor = _ids(app)
    pedido_id = _crear(app, [(mora, 4)])

    with app.app_context():
        editar_pedido(pedido_id, _dto(gestor, [(maracuya, 3)]))
        pedido = db.session.get(Pedido, pedido_id)
        assert [(d.producto_id, d.cantidad) for d in pedido.detalles] == [(maracuya, 3)]

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)
    assert _existencias(app, NOMBRE_PRODUCTO_2) == (EXISTENCIA_INICIAL_2 - 3, 3)
    _coherente(app)


def test_editar_sin_inventario_para_el_nuevo_total_no_cambia_nada(app):
    mora, maracuya, gestor = _ids(app)
    pedido_id = _crear(app, [(mora, 4), (maracuya, 2)], cliente="Original")

    with app.app_context():
        with pytest.raises(InventarioInsuficienteException) as error:
            # Maracuyá se reduce (liberaría), pero Mora pide 7 más y solo hay 6.
            editar_pedido(pedido_id, _dto(gestor, [(mora, 11), (maracuya, 1)], cliente="Nuevo"))
        assert "necesitas" in str(error.value)

        # Todo o nada: ni el cliente, ni las líneas, ni el inventario cambiaron
        pedido = db.session.get(Pedido, pedido_id)
        assert pedido.cliente_nombre == "Original"
        assert sorted((d.producto_id, d.cantidad) for d in pedido.detalles) == sorted(
            [(mora, 4), (maracuya, 2)]
        )

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 4, 4)
    assert _existencias(app, NOMBRE_PRODUCTO_2) == (EXISTENCIA_INICIAL_2 - 2, 2)
    _coherente(app)


def test_editar_solo_datos_del_cliente_no_toca_el_inventario(app):
    mora, _, gestor = _ids(app)
    pedido_id = _crear(app, [(mora, 4)], cliente="Marta")
    manana = hoy_negocio() + timedelta(days=1)

    with app.app_context():
        dto = _dto(gestor, [(mora, 4)], cliente="Marta Lucía", fecha=manana)
        dto.canal = "verbal"
        pedido = editar_pedido(pedido_id, dto)
        assert (pedido.cliente_nombre, pedido.canal, pedido.fecha_entrega) == (
            "Marta Lucía", "verbal", manana,
        )

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 4, 4)
    _coherente(app)


def test_editar_conserva_el_precio_de_las_lineas_existentes(app):
    mora, _, gestor = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])

    with app.app_context():
        Producto.query.get(mora).precio = 99999  # el catálogo cambia después
        db.session.commit()
        editar_pedido(pedido_id, _dto(gestor, [(mora, 3)]))
        assert float(db.session.get(Pedido, pedido_id).detalles[0].precio_unitario) == 8500.0


def test_no_se_puede_editar_un_pedido_despachado_ni_cancelado(app):
    mora, _, gestor = _ids(app)
    despachado = _crear(app, [(mora, 2)], cliente="Uno")
    cancelado = _crear(app, [(mora, 1)], cliente="Dos")

    with app.app_context():
        despachar_pedido(despachado, FORMA_PAGO_EFECTIVO)
        cancelar_pedido(cancelado)
        for pedido_id in (despachado, cancelado):
            with pytest.raises(TransicionDePedidoInvalidaException):
                editar_pedido(pedido_id, _dto(gestor, [(mora, 5)]))

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 2, 0)
    _coherente(app)


def test_editar_valida_datos_en_el_servidor(app):
    mora, _, gestor = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])

    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            editar_pedido(pedido_id, _dto(gestor, [(mora, 0)]))
        with pytest.raises(DatosInvalidosException):
            editar_pedido(pedido_id, _dto(gestor, [(mora, 2)], cliente=""))
        with pytest.raises(DatosInvalidosException):
            editar_pedido(pedido_id, _dto(gestor, []))
        with pytest.raises(DatosInvalidosException):
            editar_pedido(pedido_id, _dto(gestor, [(mora, 2)], fecha=hoy_negocio() - timedelta(days=1)))

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 2, 2)
    _coherente(app)


def test_editar_pedido_atrasado_es_posible_si_no_se_cambia_la_fecha(app):
    mora, _, gestor = _ids(app)
    ayer = hoy_negocio() - timedelta(days=1)
    pedido_id = _crear(app, [(mora, 2)])

    with app.app_context():
        db.session.get(Pedido, pedido_id).fecha_entrega = ayer  # quedó sin despachar
        db.session.commit()
        editar_pedido(pedido_id, _dto(gestor, [(mora, 3)], fecha=ayer))

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 3, 3)
    _coherente(app)


# --------------------------------------------------------------------------
# HU04 - Inventario comprometido
# --------------------------------------------------------------------------
def test_secuencia_completa_mantiene_el_inventario_coherente(app):
    mora, maracuya, gestor = _ids(app)

    a = _crear(app, [(mora, 3), (maracuya, 2)], cliente="A")
    b = _crear(app, [(mora, 2)], cliente="B")
    c = _crear(app, [(maracuya, 4)], cliente="C")
    _coherente(app)

    with app.app_context():
        editar_pedido(a, _dto(gestor, [(mora, 5)], cliente="A"))
        despachar_pedido(b, FORMA_PAGO_EFECTIVO)
        cancelar_pedido(c)
    _coherente(app)

    # A: 5 mora comprometidas. B salió (2 mora). C canceló (maracuya libre).
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 5 - 2, 5)
    assert _existencias(app, NOMBRE_PRODUCTO_2) == (EXISTENCIA_INICIAL_2, 0)


def test_verificar_coherencia_detecta_una_diferencia(app):
    mora, _, _ = _ids(app)
    _crear(app, [(mora, 4)])

    with app.app_context():
        Producto.query.get(mora).existencia_comprometida = 7  # alguien manipuló el dato
        db.session.commit()
        diferencias = verificar_coherencia_inventario()

    assert diferencias == [
        {"producto_id": mora, "producto": NOMBRE_PRODUCTO, "comprometida": 7, "esperada": 4}
    ]


def test_liberar_mas_de_lo_comprometido_se_rechaza_sin_dejar_negativos(app):
    mora, _, _ = _ids(app)

    with app.app_context():
        with pytest.raises(InventarioInsuficienteException):
            liberar_existencia_comprometida({mora: 1})
        with pytest.raises(InventarioInsuficienteException):
            ajustar_compromiso({mora: -1})

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)


def test_existencias_muestra_lo_comprometido(app, cliente):
    mora, _, _ = _ids(app)
    _crear(app, [(mora, 4)])
    _iniciar_sesion_gestor(cliente)

    html = cliente.get("/inventario").data.decode()

    assert "Comprometido" in html
    fila = html[html.index(NOMBRE_PRODUCTO):]
    assert "<td>6</td>" in fila and "<td>4</td>" in fila and "<td>10</td>" in fila


# --------------------------------------------------------------------------
# Interfaz (HTTP)
# --------------------------------------------------------------------------
def test_interfaz_cancelar_y_despachar(app, cliente):
    mora, _, _ = _ids(app)
    a = _crear(app, [(mora, 2)], cliente="Cliente A")
    b = _crear(app, [(mora, 3)], cliente="Cliente B")
    _iniciar_sesion_gestor(cliente)

    r = cliente.post(f"/pedidos/{a}/cancelar", follow_redirects=True)
    assert b"cancelado. Inventario liberado" in r.data

    r = cliente.post(
        f"/pedidos/{b}/despachar", data={"forma_pago": FORMA_PAGO_EFECTIVO}, follow_redirects=True
    )
    assert b"despachado." in r.data

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 3, 0)
    _coherente(app)


def test_interfaz_accion_repetida_muestra_error_y_no_mueve_inventario(app, cliente):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])
    _iniciar_sesion_gestor(cliente)

    cliente.post(f"/pedidos/{pedido_id}/despachar", data={"forma_pago": FORMA_PAGO_EFECTIVO})
    r = cliente.post(f"/pedidos/{pedido_id}/cancelar", follow_redirects=True)

    assert b"ya est" in r.data and b"despachado" in r.data
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 2, 0)


def test_interfaz_editar_muestra_datos_y_guarda_cambios(app, cliente):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 4)], cliente="Tienda Sol")
    _iniciar_sesion_gestor(cliente)

    formulario = cliente.get(f"/pedidos/{pedido_id}/editar")
    assert formulario.status_code == 200
    assert b"Tienda Sol" in formulario.data
    assert f"Editar pedido #{pedido_id}".encode() in formulario.data

    r = cliente.post(
        f"/pedidos/{pedido_id}/editar",
        data=_formulario(mora, cantidad="7", cliente="Tienda Sol Norte"),
        follow_redirects=True,
    )
    assert b"actualizado" in r.data
    assert b"Tienda Sol Norte" in r.data
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 7, 7)
    _coherente(app)


def test_interfaz_editar_sin_inventario_vuelve_al_formulario_sin_cambios(app, cliente):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 4)])
    _iniciar_sesion_gestor(cliente)

    r = cliente.post(f"/pedidos/{pedido_id}/editar", data=_formulario(mora, cantidad="50"))

    assert r.status_code == 200
    assert b"necesitas" in r.data
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 4, 4)


def test_interfaz_no_permite_editar_pedido_cancelado(app, cliente):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])
    with app.app_context():
        cancelar_pedido(pedido_id)
    _iniciar_sesion_gestor(cliente)

    r = cliente.get(f"/pedidos/{pedido_id}/editar", follow_redirects=True)
    assert b"no se puede editar" in r.data

    r = cliente.post(f"/pedidos/{pedido_id}/editar", data=_formulario(mora), follow_redirects=True)
    assert b"cancelado" in r.data
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)


def test_interfaz_pedido_inexistente_da_404(app, cliente):
    _iniciar_sesion_gestor(cliente)
    assert cliente.get("/pedidos/9999/editar").status_code == 404
    assert cliente.post("/pedidos/9999/despachar", data={"forma_pago": FORMA_PAGO_EFECTIVO}).status_code == 404
    assert cliente.post("/pedidos/9999/cancelar").status_code == 404


def test_sin_sesion_las_acciones_de_pedido_redirigen_al_login(cliente):
    for ruta in ("/pedidos/1/despachar", "/pedidos/1/cancelar"):
        r = cliente.post(ruta)
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    r = cliente.get("/pedidos/1/editar")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_vista_diaria_permite_consultar_otra_fecha(app, cliente):
    mora, _, _ = _ids(app)
    manana = hoy_negocio() + timedelta(days=1)
    _crear(app, [(mora, 1)], cliente="Cliente de mañana", fecha=manana)
    _iniciar_sesion_gestor(cliente)

    hoy = cliente.get("/pedidos/hoy")
    assert b"Cliente de ma" not in hoy.data

    otro_dia = cliente.get(f"/pedidos/hoy?fecha={manana.isoformat()}")
    assert b"Cliente de ma" in otro_dia.data

    invalida = cliente.get("/pedidos/hoy?fecha=no-es-fecha")
    assert invalida.status_code == 200  # cae a hoy sin romperse
