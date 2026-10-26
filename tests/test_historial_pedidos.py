"""Pruebas de HU07 - Búsqueda y consulta del historial de pedidos.

Criterio de aceptación (Dado / Cuando / Entonces): dado pedidos de distintas
fechas, estados y canales, cuando se filtra por alguno de ellos (o por el
nombre del cliente), solo aparecen los que cumplen TODOS los filtros dados.
"""
from datetime import date, timedelta

import pytest

from app.errores import DatosInvalidosException
from app.extensions import db
from app.models import (
    CANAL_OTRO,
    CANAL_VERBAL,
    CANAL_WHATSAPP,
    ESTADO_CANCELADO,
    ESTADO_CONFIRMADO,
    ESTADO_DESPACHADO,
    FORMA_PAGO_TRANSFERENCIA,
    Producto,
)
from app.pedidos.consultas import PEDIDOS_POR_PAGINA, FiltrosHistorial, buscar_pedidos
from app.pedidos.servicios import cancelar_pedido, despachar_pedido, registrar_pedido
from app.tiempo import hoy_negocio
from tests.test_pedidos import _dto, _ids, _iniciar_sesion_gestor


def _pedido(app, cliente, fecha=None, canal=CANAL_WHATSAPP, cantidad=1):
    mora, _, gestor = _ids(app)
    with app.app_context():
        dto = _dto(gestor, [(mora, cantidad)], cliente=cliente, fecha=fecha)
        dto.canal = canal
        return registrar_pedido(dto).id


def _nombres(pagina):
    return [p.cliente_nombre for p in pagina.pedidos]


@pytest.fixture
def historial(app):
    """Cuatro pedidos variados, del más lejano al más cercano en entrega."""
    hoy = hoy_negocio()
    ids = {
        "ana": _pedido(app, "Ana Gómez", hoy + timedelta(days=1), CANAL_WHATSAPP),
        "bruno": _pedido(app, "Bruno Peña", hoy + timedelta(days=3), CANAL_VERBAL),
        "carla": _pedido(app, "Carla 100% Frutas", hoy + timedelta(days=5), CANAL_OTRO),
        "diego": _pedido(app, "Diego Ana", hoy + timedelta(days=7), CANAL_WHATSAPP),
    }
    with app.app_context():
        despachar_pedido(ids["bruno"], FORMA_PAGO_TRANSFERENCIA)
        cancelar_pedido(ids["carla"])
    return ids


def test_sin_filtros_lista_todos_del_mas_reciente_al_mas_antiguo(app, historial):
    with app.app_context():
        resultado = buscar_pedidos(FiltrosHistorial())
        assert resultado.total == 4
        assert _nombres(resultado) == ["Diego Ana", "Carla 100% Frutas", "Bruno Peña", "Ana Gómez"]


def test_filtra_por_estado(app, historial):
    with app.app_context():
        assert _nombres(buscar_pedidos(FiltrosHistorial(estado=ESTADO_DESPACHADO))) == ["Bruno Peña"]
        assert _nombres(buscar_pedidos(FiltrosHistorial(estado=ESTADO_CANCELADO))) == ["Carla 100% Frutas"]
        assert buscar_pedidos(FiltrosHistorial(estado=ESTADO_CONFIRMADO)).total == 2


def test_filtra_por_canal(app, historial):
    with app.app_context():
        assert _nombres(buscar_pedidos(FiltrosHistorial(canal=CANAL_VERBAL))) == ["Bruno Peña"]
        assert buscar_pedidos(FiltrosHistorial(canal=CANAL_WHATSAPP)).total == 2


def test_filtra_por_rango_de_fecha_de_entrega_con_limites_inclusivos(app, historial):
    hoy = hoy_negocio()
    with app.app_context():
        filtros = FiltrosHistorial(desde=hoy + timedelta(days=3), hasta=hoy + timedelta(days=5))
        assert _nombres(buscar_pedidos(filtros)) == ["Carla 100% Frutas", "Bruno Peña"]
        # Solo "desde" o solo "hasta" también funcionan
        assert buscar_pedidos(FiltrosHistorial(desde=hoy + timedelta(days=6))).total == 1
        assert buscar_pedidos(FiltrosHistorial(hasta=hoy + timedelta(days=1))).total == 1


def test_busca_por_nombre_sin_importar_mayusculas_y_en_cualquier_parte(app, historial):
    with app.app_context():
        # "ana" está en "Ana Gómez" y en "Diego Ana"
        assert sorted(_nombres(buscar_pedidos(FiltrosHistorial(cliente="ANA")))) == [
            "Ana Gómez", "Diego Ana",
        ]
        assert _nombres(buscar_pedidos(FiltrosHistorial(cliente="  bruno  "))) == ["Bruno Peña"]
        assert buscar_pedidos(FiltrosHistorial(cliente="nadie")).total == 0


def test_los_comodines_de_sql_se_buscan_como_texto(app, historial):
    with app.app_context():
        # "%" no debe significar "cualquier cosa": solo coincide con "100% Frutas"
        assert _nombres(buscar_pedidos(FiltrosHistorial(cliente="%"))) == ["Carla 100% Frutas"]
        # "_" tampoco es "cualquier carácter": ningún nombre lo contiene
        assert buscar_pedidos(FiltrosHistorial(cliente="_")).total == 0


def test_los_filtros_se_combinan(app, historial):
    hoy = hoy_negocio()
    with app.app_context():
        filtros = FiltrosHistorial(
            cliente="ana", canal=CANAL_WHATSAPP, estado=ESTADO_CONFIRMADO, desde=hoy + timedelta(days=2)
        )
        assert _nombres(buscar_pedidos(filtros)) == ["Diego Ana"]


@pytest.mark.parametrize(
    "filtros",
    [
        FiltrosHistorial(estado="inexistente"),
        FiltrosHistorial(canal="paloma mensajera"),
        FiltrosHistorial(desde=date(2026, 5, 2), hasta=date(2026, 5, 1)),
        FiltrosHistorial(cliente="x" * 500),
    ],
)
def test_filtros_invalidos_se_rechazan(app, filtros):
    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            buscar_pedidos(filtros)


def test_paginacion(app):
    with app.app_context():
        for producto in Producto.query.all():
            producto.existencia_disponible += 100
        db.session.commit()
    for numero in range(PEDIDOS_POR_PAGINA + 5):
        _pedido(app, f"Cliente {numero:02d}")

    with app.app_context():
        primera = buscar_pedidos(FiltrosHistorial(), pagina=1)
        segunda = buscar_pedidos(FiltrosHistorial(), pagina=2)
        assert (primera.total, primera.total_paginas) == (PEDIDOS_POR_PAGINA + 5, 2)
        assert len(primera.pedidos) == PEDIDOS_POR_PAGINA and len(segunda.pedidos) == 5
        assert not {p.id for p in primera.pedidos} & {p.id for p in segunda.pedidos}

        # Páginas fuera de rango se ajustan en lugar de romper
        assert buscar_pedidos(FiltrosHistorial(), pagina=99).pagina == 2
        assert buscar_pedidos(FiltrosHistorial(), pagina=0).pagina == 1
        assert buscar_pedidos(FiltrosHistorial(cliente="nadie")).total_paginas == 1


def test_interfaz_historial_muestra_pedidos_total_y_forma_de_pago(app, cliente, historial):
    _iniciar_sesion_gestor(cliente)

    html = cliente.get("/pedidos/historial").data.decode()

    assert "Bruno Peña" in html and "Transferencia" in html
    assert "$ 8.500" in html
    assert "4 pedidos encontrados" in html


def test_interfaz_filtra_y_conserva_los_filtros_en_el_formulario(app, cliente, historial):
    _iniciar_sesion_gestor(cliente)

    html = cliente.get("/pedidos/historial?estado=cancelado&cliente=carla").data.decode()

    assert "Carla 100% Frutas" in html and "Bruno Peña" not in html
    assert "1 pedido encontrado" in html
    assert 'value="carla"' in html


def test_interfaz_solo_ofrece_editar_pedidos_confirmados(app, cliente, historial):
    _iniciar_sesion_gestor(cliente)

    html = cliente.get("/pedidos/historial").data.decode()

    assert html.count("/editar") == 2  # Ana y Diego siguen confirmados


def test_interfaz_tolera_fechas_mal_escritas_y_rangos_invalidos(app, cliente, historial):
    _iniciar_sesion_gestor(cliente)

    mal = cliente.get("/pedidos/historial?desde=ayer")
    assert mal.status_code == 200 and b"4 pedidos" in mal.data

    rango = cliente.get("/pedidos/historial?desde=2026-05-02&hasta=2026-05-01")
    assert rango.status_code == 200 and b"posterior" in rango.data

    estado = cliente.get("/pedidos/historial?estado=raro&pagina=abc")
    assert estado.status_code == 200


def test_historial_exige_sesion(cliente):
    r = cliente.get("/pedidos/historial")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
