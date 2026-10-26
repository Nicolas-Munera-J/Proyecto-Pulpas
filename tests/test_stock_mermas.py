"""Pruebas de HU15 (alerta de existencias bajas) y HU16 (mermas).

Criterios de aceptación (Dado / Cuando / Entonces):
- HU15: dado un producto con umbral 5, cuando su existencia disponible llega a
  5 o menos, se resalta como stock bajo y se avisa al tomar el pedido.
- HU16: dado un producto con 10 disponibles, cuando se registra una merma de 3
  por daño, quedan 7 disponibles y la pérdida queda registrada con su motivo;
  no se puede descartar más de lo disponible.
"""
import pytest
from sqlalchemy import create_engine, inspect, text

from app.errores import DatosInvalidosException, InventarioInsuficienteException
from app.extensions import db
from app.inventario.servicios import (
    describir_stock_bajo,
    listar_mermas,
    listar_stock_bajo,
    registrar_entrada_inventario,
    registrar_merma,
    verificar_coherencia_inventario,
)
from app.migraciones import agregar_columnas_faltantes
from app.models import (
    MOTIVO_MERMA_DANIO,
    MOTIVO_MERMA_VENCIMIENTO,
    TIPO_MERMA,
    UMBRAL_STOCK_BAJO_PREDETERMINADO,
    MovimientoInventario,
    Producto,
    Usuario,
)
from tests.conftest import (
    EMAIL_ADMIN,
    EXISTENCIA_INICIAL,
    NOMBRE_PRODUCTO,
    NOMBRE_PRODUCTO_2,
)
from tests.test_ciclo_pedido import _crear
from tests.test_pedidos import _existencias, _formulario, _ids, _iniciar_sesion_gestor
from tests.test_ventas_reportes import _iniciar_sesion_admin


def _admin_id(app):
    with app.app_context():
        return Usuario.query.filter_by(email=EMAIL_ADMIN).one().id


def _csrf_off(app):
    assert app.config["CSRF_ACTIVADO"] is False


# --------------------------------------------------------------------------
# HU15 - Alerta de existencias bajas
# --------------------------------------------------------------------------
def test_stock_bajo_cuando_la_disponible_llega_al_umbral(app):
    mora, _, _ = _ids(app)  # umbral 5, disponible 10
    with app.app_context():
        producto = db.session.get(Producto, mora)
        assert producto.stock_bajo is False
        producto.existencia_disponible = 6
        assert producto.stock_bajo is False
        producto.existencia_disponible = 5  # justo en el umbral
        assert producto.stock_bajo is True
        producto.existencia_disponible = 0
        assert producto.stock_bajo is True


def test_listar_stock_bajo_incluye_solo_productos_activos_en_alerta(app):
    mora, maracuya, _ = _ids(app)
    with app.app_context():
        assert listar_stock_bajo() == []
        db.session.get(Producto, mora).existencia_disponible = 2
        db.session.get(Producto, maracuya).existencia_disponible = 1
        db.session.get(Producto, maracuya).activo = False  # los inactivos no alertan
        db.session.commit()

        assert [p.nombre for p in listar_stock_bajo()] == [NOMBRE_PRODUCTO]
        assert describir_stock_bajo([mora, maracuya]) == [
            f"{NOMBRE_PRODUCTO} (Bolsa 500g): quedan 2, umbral 5"
        ]
        assert describir_stock_bajo([]) == []


def test_tomar_un_pedido_que_deja_stock_bajo_avisa_en_el_mismo_mensaje(app, cliente):
    mora, _, _ = _ids(app)
    _iniciar_sesion_gestor(cliente)

    # 10 - 6 = 4, por debajo del umbral 5
    r = cliente.post("/pedidos/nuevo", data=_formulario(mora, cantidad="6"), follow_redirects=True)

    assert b"registrado y confirmado" in r.data
    assert b"existencia baja" in r.data and NOMBRE_PRODUCTO.encode() in r.data
    assert b"quedan 4" in r.data


def test_pedido_que_no_llega_al_umbral_no_genera_alerta(app, cliente):
    mora, _, _ = _ids(app)
    _iniciar_sesion_gestor(cliente)

    r = cliente.post("/pedidos/nuevo", data=_formulario(mora, cantidad="2"), follow_redirects=True)

    assert b"registrado y confirmado" in r.data and b"existencia baja" not in r.data


def test_editar_un_pedido_que_deja_stock_bajo_tambien_avisa(app, cliente):
    mora, _, _ = _ids(app)
    pedido_id = _crear(app, [(mora, 2)])
    _iniciar_sesion_gestor(cliente)

    r = cliente.post(
        f"/pedidos/{pedido_id}/editar", data=_formulario(mora, cantidad="8"), follow_redirects=True
    )

    assert b"actualizado" in r.data and b"existencia baja" in r.data


def test_existencias_puede_filtrar_solo_stock_bajo(app, cliente):
    mora, _, _ = _ids(app)
    _crear(app, [(mora, 6)])  # Mora queda en 4 (bajo); Maracuyá sigue en 8
    _iniciar_sesion_gestor(cliente)

    todas = cliente.get("/inventario").data.decode()
    assert NOMBRE_PRODUCTO in todas and NOMBRE_PRODUCTO_2 in todas

    solo_bajo = cliente.get("/inventario?solo_bajo=1").data.decode()
    assert NOMBRE_PRODUCTO in solo_bajo and NOMBRE_PRODUCTO_2 not in solo_bajo


def test_inicio_lista_los_productos_en_stock_bajo(app, cliente):
    mora, _, _ = _ids(app)
    _crear(app, [(mora, 6)])
    _iniciar_sesion_gestor(cliente)

    html = cliente.get("/").data.decode()

    assert "Productos con existencia baja" in html and "disponible: 4, umbral: 5" in html


def test_producto_nuevo_propone_el_umbral_predeterminado(app, cliente):
    _iniciar_sesion_admin(cliente)

    formulario = cliente.get("/productos/nuevo").data.decode()
    assert f'name="umbral_minimo" min="0" value="{UMBRAL_STOCK_BAJO_PREDETERMINADO}"' in formulario

    # Si el formulario no trae umbral, se usa el predeterminado (no 0)
    cliente.post(
        "/productos/nuevo",
        data={"nombre": "Pulpa de Lulo", "presentacion": "Bolsa 500g", "unidad_medida": "unidad", "precio": "9500"},
    )
    with app.app_context():
        lulo = Producto.query.filter_by(nombre="Pulpa de Lulo").one()
        assert lulo.umbral_minimo == UMBRAL_STOCK_BAJO_PREDETERMINADO


# --------------------------------------------------------------------------
# HU16 - Mermas
# --------------------------------------------------------------------------
def test_merma_descuenta_disponible_y_registra_el_movimiento(app):
    mora, _, _ = _ids(app)
    admin = _admin_id(app)

    with app.app_context():
        merma = registrar_merma(mora, 3, MOTIVO_MERMA_DANIO, admin, "Bolsas rotas")
        assert merma.tipo == TIPO_MERMA and merma.motivo == MOTIVO_MERMA_DANIO
        assert merma.cantidad == 3 and merma.observacion == "Bolsas rotas"
        assert merma.usuario_id == admin

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 3, 0)


def test_merma_por_vencimiento_sin_observacion(app):
    mora, _, _ = _ids(app)

    with app.app_context():
        merma = registrar_merma(mora, 1, MOTIVO_MERMA_VENCIMIENTO, _admin_id(app))
        assert merma.motivo == MOTIVO_MERMA_VENCIMIENTO and merma.observacion is None


@pytest.mark.parametrize(
    "cantidad, motivo",
    [(0, MOTIVO_MERMA_DANIO), (-2, MOTIVO_MERMA_DANIO), (None, MOTIVO_MERMA_DANIO),
     (1, ""), (1, "robo"), (1, None)],
)
def test_merma_con_datos_invalidos_se_rechaza_sin_cambios(app, cantidad, motivo):
    mora, _, _ = _ids(app)

    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            registrar_merma(mora, cantidad, motivo, _admin_id(app))
        assert MovimientoInventario.query.count() == 0

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)


def test_merma_de_producto_inexistente_o_con_observacion_larga_se_rechaza(app):
    mora, _, _ = _ids(app)

    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            registrar_merma(99999, 1, MOTIVO_MERMA_DANIO, _admin_id(app))
        with pytest.raises(DatosInvalidosException):
            registrar_merma(mora, 1, MOTIVO_MERMA_DANIO, _admin_id(app), "x" * 256)


def test_no_se_puede_descartar_mas_de_lo_disponible_ni_lo_comprometido(app):
    mora, _, _ = _ids(app)
    _crear(app, [(mora, 6)])  # 4 disponibles, 6 comprometidas
    admin = _admin_id(app)

    with app.app_context():
        with pytest.raises(InventarioInsuficienteException) as error:
            registrar_merma(mora, 5, MOTIVO_MERMA_DANIO, admin)
        assert "comprometidas" in str(error.value)
        assert MovimientoInventario.query.count() == 0

        registrar_merma(mora, 4, MOTIVO_MERMA_DANIO, admin)  # justo lo disponible sí

    assert _existencias(app, NOMBRE_PRODUCTO) == (0, 6)


def test_la_merma_no_rompe_la_coherencia_del_inventario(app):
    mora, maracuya, _ = _ids(app)
    _crear(app, [(mora, 3), (maracuya, 2)])

    with app.app_context():
        registrar_merma(mora, 2, MOTIVO_MERMA_DANIO, _admin_id(app))
        registrar_merma(maracuya, 1, MOTIVO_MERMA_VENCIMIENTO, _admin_id(app))
        assert verificar_coherencia_inventario() == []


def test_listar_mermas_trae_solo_mermas_las_mas_recientes_primero(app):
    mora, _, _ = _ids(app)
    admin = _admin_id(app)

    with app.app_context():
        registrar_entrada_inventario(mora, 5, admin)  # una entrada no es merma
        primera = registrar_merma(mora, 1, MOTIVO_MERMA_DANIO, admin)
        segunda = registrar_merma(mora, 2, MOTIVO_MERMA_VENCIMIENTO, admin)

        assert [m.id for m in listar_mermas()] == [segunda.id, primera.id]
        assert len(listar_mermas(limite=1)) == 1


def test_interfaz_administrador_registra_merma_y_la_ve_en_la_lista(app, cliente):
    mora, _, _ = _ids(app)
    _iniciar_sesion_admin(cliente)

    r = cliente.post(
        "/inventario/mermas",
        data={"producto_id": mora, "cantidad": "2", "motivo": MOTIVO_MERMA_DANIO, "observacion": "Se cayó la caja"},
        follow_redirects=True,
    )

    assert b"Merma registrada" in r.data
    html = r.data.decode()
    assert "Se cayó la caja" in html and "Daño" in html
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL - 2, 0)


def test_interfaz_merma_que_deja_stock_bajo_avisa(app, cliente):
    mora, _, _ = _ids(app)
    _iniciar_sesion_admin(cliente)

    r = cliente.post(
        "/inventario/mermas",
        data={"producto_id": mora, "cantidad": "7", "motivo": MOTIVO_MERMA_VENCIMIENTO},
        follow_redirects=True,
    )

    assert b"Merma registrada" in r.data and b"existencia baja" in r.data


def test_interfaz_merma_rechaza_exceso_y_datos_invalidos(app, cliente):
    mora, _, _ = _ids(app)
    _iniciar_sesion_admin(cliente)

    exceso = cliente.post(
        "/inventario/mermas", data={"producto_id": mora, "cantidad": "50", "motivo": MOTIVO_MERMA_DANIO}
    )
    assert exceso.status_code == 200 and b"No se puede registrar la merma" in exceso.data

    no_numerica = cliente.post(
        "/inventario/mermas", data={"producto_id": mora, "cantidad": "abc", "motivo": MOTIVO_MERMA_DANIO}
    )
    assert no_numerica.status_code == 200

    sin_motivo = cliente.post("/inventario/mermas", data={"producto_id": mora, "cantidad": "1"})
    assert b"motivo" in sin_motivo.data

    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)


def test_mermas_solo_para_administrador(app, cliente):
    mora, _, _ = _ids(app)

    sin_sesion = cliente.get("/inventario/mermas")
    assert sin_sesion.status_code == 302 and "/login" in sin_sesion.headers["Location"]

    _iniciar_sesion_gestor(cliente)
    assert cliente.get("/inventario/mermas").status_code == 403
    r = cliente.post("/inventario/mermas", data={"producto_id": mora, "cantidad": "1", "motivo": MOTIVO_MERMA_DANIO})
    assert r.status_code == 403
    assert _existencias(app, NOMBRE_PRODUCTO) == (EXISTENCIA_INICIAL, 0)


def test_migracion_agrega_motivo_a_movimientos_de_una_base_anterior(app):
    motor = create_engine("sqlite://")
    with motor.begin() as conexion:
        conexion.execute(text("CREATE TABLE movimientos_inventario (id INTEGER PRIMARY KEY, tipo TEXT)"))
        conexion.execute(text("INSERT INTO movimientos_inventario (tipo) VALUES ('entrada')"))

    assert agregar_columnas_faltantes(motor) == ["movimientos_inventario.motivo"]
    assert "motivo" in {c["name"] for c in inspect(motor).get_columns("movimientos_inventario")}
    with motor.connect() as conexion:
        assert conexion.execute(text("SELECT tipo FROM movimientos_inventario")).scalar() == "entrada"
