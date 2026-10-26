"""Pruebas del Sprint 2: HU02 (registro con verificación de inventario),
HU09 (alerta de pedido duplicado) y HU01 (pedidos del día).

Criterios de aceptación (Dado / Cuando / Entonces) verificados:
- HU02: dado un producto con 10 unidades, cuando se pide 4, el pedido queda
  confirmado, 6 disponibles y 4 comprometidas. Si se piden 11, no se registra.
- HU09: dado un pedido reciente de un cliente, cuando se registra otro igual,
  el sistema advierte y solo lo registra si el gestor lo confirma.
- HU01: dado pedidos confirmados con distintas fechas de entrega, solo se
  listan los de hoy.
"""
from datetime import timedelta

import pytest

from app.errores import (
    DatosInvalidosException,
    InventarioInsuficienteException,
    PedidoPosiblementeDuplicadoException,
)
from app.models import (
    ESTADO_CANCELADO,
    ESTADO_CONFIRMADO,
    ESTADO_DESPACHADO,
    Pedido,
    Producto,
    Usuario,
)
from app.extensions import db
from app.pedidos.dtos import ItemPedidoDTO, PedidoDTO
from app.pedidos.servicios import (
    VENTANA_DUPLICADO_MINUTOS,
    detectar_pedido_duplicado,
    listar_pedidos_del_dia,
    registrar_pedido,
    verificar_inventario_disponible,
)
from app.tiempo import ahora_utc, hoy_negocio
from tests.conftest import (
    EMAIL_GESTOR,
    EXISTENCIA_INICIAL,
    EXISTENCIA_INICIAL_2,
    NOMBRE_PRODUCTO,
    NOMBRE_PRODUCTO_2,
    PASSWORD_GESTOR,
)


# --------------------------------------------------------------------------
# Ayudas
# --------------------------------------------------------------------------
def _ids(app):
    with app.app_context():
        mora = Producto.query.filter_by(nombre=NOMBRE_PRODUCTO).one().id
        maracuya = Producto.query.filter_by(nombre=NOMBRE_PRODUCTO_2).one().id
        gestor = Usuario.query.filter_by(email=EMAIL_GESTOR).one().id
        return mora, maracuya, gestor


def _dto(usuario_id, items, cliente="Doña Marta", fecha=None):
    return PedidoDTO(
        cliente_nombre=cliente,
        fecha_entrega=fecha or hoy_negocio(),
        items=[ItemPedidoDTO(producto_id=p, cantidad=c) for p, c in items],
        usuario_id=usuario_id,
    )


def _existencias(app, nombre):
    with app.app_context():
        p = Producto.query.filter_by(nombre=nombre).one()
        return p.existencia_disponible, p.existencia_comprometida


def _iniciar_sesion_gestor(cliente):
    r = cliente.post("/login", data={"email": EMAIL_GESTOR, "password": PASSWORD_GESTOR})
    assert r.status_code == 302


def _formulario(mora_id, cantidad="4", cliente="Doña Marta", extra=None):
    datos = {
        "cliente_nombre": cliente,
        "cliente_contacto": "300 000 0000",
        "canal": "whatsapp",
        "fecha_entrega": hoy_negocio().isoformat(),
        "producto_id": [str(mora_id)],
        "cantidad": [cantidad],
    }
    datos.update(extra or {})
    return datos


# --------------------------------------------------------------------------
# HU02 - Registro de pedido con verificación inmediata de inventario
# --------------------------------------------------------------------------
def test_pedido_con_inventario_suficiente_queda_confirmado_y_compromete(app):
    # Dado un producto con 10 unidades disponibles
    mora, _, gestor = _ids(app)

    # Cuando se registra un pedido de 4
    with app.app_context():
        pedido = registrar_pedido(_dto(gestor, [(mora, 4)]))
        assert pedido.estado == ESTADO_CONFIRMADO
        assert pedido.detalles[0].cantidad == 4

    # Entonces quedan 6 disponibles y 4 comprometidas (existencia física intacta)
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 4, 4)


def test_pedido_sin_inventario_suficiente_no_se_registra(app):
    mora, _, gestor = _ids(app)

    with app.app_context():
        with pytest.raises(InventarioInsuficienteException):
            registrar_pedido(_dto(gestor, [(mora, EXISTENCIA_INICIAL + 1)]))

    # No hay pedido ni estado de espera, y las existencias no cambiaron
    with app.app_context():
        assert Pedido.query.count() == 0
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)


def test_pedido_con_varios_productos_es_todo_o_nada(app):
    # Mora alcanza, Maracuyá no: no debe comprometerse ni la Mora.
    mora, maracuya, gestor = _ids(app)

    with app.app_context():
        with pytest.raises(InventarioInsuficienteException) as error:
            registrar_pedido(_dto(gestor, [(mora, 2), (maracuya, EXISTENCIA_INICIAL_2 + 1)]))
        assert len(error.value.faltantes) == 1

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)
    assert _existencias(app, NOMBRE_PRODUCTO_2) == (EXISTENCIA_INICIAL_2, 0)


def test_lineas_repetidas_del_mismo_producto_se_suman(app):
    # 6 + 6 = 12 > 10: cada línea sola pasaría, juntas no.
    mora, _, gestor = _ids(app)

    with app.app_context():
        with pytest.raises(InventarioInsuficienteException):
            registrar_pedido(_dto(gestor, [(mora, 6), (mora, 6)]))

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)


@pytest.mark.parametrize("cantidad_invalida", [0, -2])
def test_cantidades_no_positivas_se_rechazan(app, cantidad_invalida):
    mora, _, gestor = _ids(app)

    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            registrar_pedido(_dto(gestor, [(mora, cantidad_invalida)]))
        assert Pedido.query.count() == 0


def test_campos_obligatorios_se_validan_en_el_servidor(app):
    mora, _, gestor = _ids(app)

    with app.app_context():
        with pytest.raises(DatosInvalidosException):  # sin cliente
            registrar_pedido(_dto(gestor, [(mora, 1)], cliente="   "))
        with pytest.raises(DatosInvalidosException):  # sin productos
            registrar_pedido(_dto(gestor, []))
        with pytest.raises(DatosInvalidosException):  # fecha en el pasado
            registrar_pedido(_dto(gestor, [(mora, 1)], fecha=hoy_negocio() - timedelta(days=1)))
        assert Pedido.query.count() == 0


def test_producto_inactivo_o_inexistente_se_rechaza(app):
    mora, _, gestor = _ids(app)

    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            registrar_pedido(_dto(gestor, [(99999, 1)]))

        Producto.query.get(mora).activo = False
        db.session.commit()
        with pytest.raises(DatosInvalidosException):
            registrar_pedido(_dto(gestor, [(mora, 1)]))


def test_verificar_inventario_solo_consulta_y_no_compromete(app):
    # Chequeo de código limpio: sin efectos colaterales ocultos.
    mora, _, _ = _ids(app)

    with app.app_context():
        verificar_inventario_disponible({mora: 5})

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)


def test_gestor_registra_pedido_desde_la_interfaz(app, cliente):
    mora, _, _ = _ids(app)
    _iniciar_sesion_gestor(cliente)

    respuesta = cliente.post("/pedidos/nuevo", data=_formulario(mora), follow_redirects=True)

    assert respuesta.status_code == 200
    assert b"registrado y confirmado" in respuesta.data
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 4, 4)


def test_interfaz_informa_cuando_no_hay_inventario_y_no_registra(app, cliente):
    mora, _, _ = _ids(app)
    _iniciar_sesion_gestor(cliente)

    respuesta = cliente.post("/pedidos/nuevo", data=_formulario(mora, cantidad="50"))

    assert respuesta.status_code == 200
    assert "No hay inventario suficiente".encode() in respuesta.data
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)
    with app.app_context():
        assert Pedido.query.count() == 0


def test_interfaz_rechaza_cantidad_no_numerica(app, cliente):
    mora, _, _ = _ids(app)
    _iniciar_sesion_gestor(cliente)

    respuesta = cliente.post("/pedidos/nuevo", data=_formulario(mora, cantidad="abc"))

    assert respuesta.status_code == 200  # vuelve al formulario con el mensaje de error
    with app.app_context():
        assert Pedido.query.count() == 0


def test_sin_sesion_las_rutas_de_pedidos_redirigen_al_login(cliente):
    for ruta in ("/pedidos/nuevo", "/pedidos/hoy"):
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 302
        assert "/login" in respuesta.headers["Location"]


# --------------------------------------------------------------------------
# HU09 - Alerta de posible pedido duplicado
# --------------------------------------------------------------------------
def test_mismo_cliente_y_productos_en_la_ventana_se_marca_como_duplicado(app):
    mora, _, gestor = _ids(app)

    with app.app_context():
        primero = registrar_pedido(_dto(gestor, [(mora, 2)]))

        with pytest.raises(PedidoPosiblementeDuplicadoException) as alerta:
            registrar_pedido(_dto(gestor, [(mora, 2)], cliente="  doña   MARTA "))
        assert alerta.value.pedido_existente.id == primero.id
        assert Pedido.query.count() == 1

    # Al advertir no se tocó el inventario
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 2, 2)


def test_duplicado_confirmado_por_el_gestor_si_se_registra(app):
    mora, _, gestor = _ids(app)

    with app.app_context():
        registrar_pedido(_dto(gestor, [(mora, 2)]))
        segundo = registrar_pedido(_dto(gestor, [(mora, 2)]), confirmar_duplicado=True)
        assert segundo.id is not None
        assert Pedido.query.count() == 2

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 4, 4)


def test_no_es_duplicado_si_cambia_cliente_productos_ventana_o_estado(app):
    mora, maracuya, gestor = _ids(app)

    with app.app_context():
        base = registrar_pedido(_dto(gestor, [(mora, 1)]))

        assert detectar_pedido_duplicado(_dto(gestor, [(mora, 1)], cliente="Otro cliente")) is None
        assert detectar_pedido_duplicado(_dto(gestor, [(maracuya, 1)])) is None
        assert detectar_pedido_duplicado(_dto(gestor, [(mora, 1)])) is not None

        # Fuera de la ventana de tiempo
        base.fecha_creacion = ahora_utc() - timedelta(minutes=VENTANA_DUPLICADO_MINUTOS + 1)
        db.session.commit()
        assert detectar_pedido_duplicado(_dto(gestor, [(mora, 1)])) is None

        # Dentro de la ventana, pero cancelado
        base.fecha_creacion = ahora_utc()
        base.estado = ESTADO_CANCELADO
        db.session.commit()
        assert detectar_pedido_duplicado(_dto(gestor, [(mora, 1)])) is None


def test_interfaz_advierte_duplicado_y_solo_registra_si_se_confirma(app, cliente):
    mora, _, _ = _ids(app)
    _iniciar_sesion_gestor(cliente)
    cliente.post("/pedidos/nuevo", data=_formulario(mora, cantidad="2"))

    # Segundo envío idéntico: aparece la alerta y no se crea el pedido
    respuesta = cliente.post("/pedidos/nuevo", data=_formulario(mora, cantidad="2"))
    assert respuesta.status_code == 200
    assert b"Posible pedido duplicado" in respuesta.data
    with app.app_context():
        assert Pedido.query.count() == 1

    # El gestor confirma: ahora sí se registra
    confirmado = cliente.post(
        "/pedidos/nuevo",
        data=_formulario(mora, cantidad="2", extra={"confirmar_duplicado": "1"}),
        follow_redirects=True,
    )
    assert b"registrado y confirmado" in confirmado.data
    with app.app_context():
        assert Pedido.query.count() == 2


# --------------------------------------------------------------------------
# HU01 - Consulta de pedidos del día
# --------------------------------------------------------------------------
def test_pedidos_del_dia_solo_incluye_confirmados_con_entrega_hoy(app):
    mora, maracuya, gestor = _ids(app)
    manana = hoy_negocio() + timedelta(days=1)

    with app.app_context():
        de_hoy = registrar_pedido(_dto(gestor, [(mora, 1)], cliente="Cliente hoy"))
        registrar_pedido(_dto(gestor, [(mora, 1)], cliente="Cliente mañana", fecha=manana))
        cancelado = registrar_pedido(_dto(gestor, [(maracuya, 1)], cliente="Cliente cancelado"))
        despachado = registrar_pedido(_dto(gestor, [(maracuya, 2)], cliente="Cliente despachado"))
        cancelado.estado = ESTADO_CANCELADO
        despachado.estado = ESTADO_DESPACHADO
        db.session.commit()

        pedidos = listar_pedidos_del_dia()

        assert [p.id for p in pedidos] == [de_hoy.id]
        # Muestra cliente, productos, cantidades y estado
        assert pedidos[0].cliente_nombre == "Cliente hoy"
        assert pedidos[0].detalles[0].producto.nombre == NOMBRE_PRODUCTO
        assert pedidos[0].detalles[0].cantidad == 1
        assert pedidos[0].estado == ESTADO_CONFIRMADO


def test_pedidos_del_dia_vacio_cuando_no_hay_pedidos(app):
    with app.app_context():
        assert listar_pedidos_del_dia() == []


def test_vista_de_pedidos_del_dia_muestra_cliente_producto_y_estado(app, cliente):
    mora, _, _ = _ids(app)
    _iniciar_sesion_gestor(cliente)
    cliente.post("/pedidos/nuevo", data=_formulario(mora, cantidad="3", cliente="Tienda La Esquina"))

    respuesta = cliente.get("/pedidos/hoy")

    assert respuesta.status_code == 200
    assert b"Tienda La Esquina" in respuesta.data
    assert NOMBRE_PRODUCTO.encode() in respuesta.data
    assert b"Confirmado" in respuesta.data


def test_vista_de_pedidos_del_dia_sin_pedidos_muestra_mensaje(app, cliente):
    _iniciar_sesion_gestor(cliente)

    respuesta = cliente.get("/pedidos/hoy")

    assert respuesta.status_code == 200
    assert b"No hay pedidos confirmados" in respuesta.data
