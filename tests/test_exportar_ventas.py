"""Pruebas de HU19 - Exportar el reporte de ventas.

Criterio de aceptación (Dado / Cuando / Entonces): dado un periodo con ventas,
cuando el administrador exporta el reporte, descarga un archivo CSV con el
resumen, el desglose por forma de pago y el detalle de cada pedido, con las
mismas cifras que muestra la pantalla de HU17.
"""
import csv
import io
from datetime import datetime

import pytest

from app.errores import DatosInvalidosException
from app.models import FORMA_PAGO_EFECTIVO, FORMA_PAGO_TRANSFERENCIA
from app.reportes.servicios import exportar_ventas_csv
from app.tiempo import hoy_negocio
from tests.test_pedidos import _ids, _iniciar_sesion_gestor
from tests.test_ventas_reportes import _iniciar_sesion_admin, _vender


def _filas(contenido: str):
    assert contenido.startswith("\ufeff")  # BOM: Excel muestra bien las tildes
    return list(csv.reader(io.StringIO(contenido[1:]), delimiter=";"))


def test_csv_incluye_resumen_desglose_y_detalle(app):
    mora, maracuya, _ = _ids(app)
    _vender(app, [(mora, 2)], cliente="Ana", forma=FORMA_PAGO_EFECTIVO)  # $17.000
    _vender(app, [(maracuya, 1)], cliente="Bruno", forma=FORMA_PAGO_TRANSFERENCIA)  # $9.000
    hoy = hoy_negocio()

    with app.app_context():
        filas = _filas(exportar_ventas_csv(hoy, hoy))

    assert ["Reporte de ventas"] in filas
    assert ["Desde", hoy.isoformat()] in filas and ["Hasta", hoy.isoformat()] in filas
    assert ["Total de ventas (COP)", "26000"] in filas
    assert ["Pedidos despachados", "2"] in filas
    assert ["efectivo", "1", "17000"] in filas and ["transferencia", "1", "9000"] in filas

    detalle = filas[filas.index(["Pedido", "Fecha de despacho", "Cliente", "Forma de pago", "Total (COP)"]) + 1:]
    assert [(f[2], f[3], f[4]) for f in detalle] == [
        ("Ana", "efectivo", "17000"),
        ("Bruno", "transferencia", "9000"),
    ]


def test_csv_respeta_periodo_y_hora_de_colombia(app):
    mora, _, _ = _ids(app)
    d10, d11 = datetime(2026, 3, 10).date(), datetime(2026, 3, 11).date()
    # 23:30 del 10 de marzo en Bogotá = 04:30 UTC del 11
    _vender(app, [(mora, 1)], cliente="Noche", despachado_utc=datetime(2026, 3, 11, 4, 30))
    _vender(app, [(mora, 2)], cliente="Fuera", despachado_utc=datetime(2026, 3, 20, 17, 0))

    with app.app_context():
        filas = _filas(exportar_ventas_csv(d10, d11))

    assert ["Pedidos despachados", "1"] in filas
    assert any(f[1:3] == ["2026-03-10 23:30", "Noche"] for f in filas if len(f) >= 3)
    assert not any("Fuera" in f for f in filas)


def test_csv_sin_ventas_solo_trae_encabezados_y_ceros(app):
    hoy = hoy_negocio()

    with app.app_context():
        filas = _filas(exportar_ventas_csv(hoy, hoy))

    assert ["Total de ventas (COP)", "0"] in filas and ["Pedidos despachados", "0"] in filas
    assert filas[-1] == ["Pedido", "Fecha de despacho", "Cliente", "Forma de pago", "Total (COP)"]


def test_csv_conserva_tildes_y_enie(app):
    mora, _, _ = _ids(app)
    _vender(app, [(mora, 1)], cliente="Peña Ñandú Gómez")
    hoy = hoy_negocio()

    with app.app_context():
        contenido = exportar_ventas_csv(hoy, hoy)

    assert "Peña Ñandú Gómez" in contenido


@pytest.mark.parametrize(
    "nombre_peligroso",
    ['=HYPERLINK("http://malo.example","clic")', "+cmd|' /C calc'!A0", "@SUM(1+1)", "-2+3"],
)
def test_csv_neutraliza_formulas_escritas_por_los_clientes(app, nombre_peligroso):
    # Si el nombre de un cliente empieza por = + - @, Excel lo ejecutaría como
    # fórmula al abrir el archivo (inyección de fórmulas / CSV injection).
    mora, _, _ = _ids(app)
    _vender(app, [(mora, 1)], cliente=nombre_peligroso)
    hoy = hoy_negocio()

    with app.app_context():
        filas = _filas(exportar_ventas_csv(hoy, hoy))

    clientes = [f[2] for f in filas if len(f) == 5 and f[0].isdigit()]
    assert clientes == ["'" + nombre_peligroso]


def test_csv_con_periodo_invalido_se_rechaza(app):
    hoy = hoy_negocio()
    with app.app_context():
        with pytest.raises(DatosInvalidosException):
            exportar_ventas_csv(hoy, datetime(2020, 1, 1).date())


def test_interfaz_descarga_el_archivo_csv(app, cliente):
    mora, _, _ = _ids(app)
    _vender(app, [(mora, 2)], cliente="Ana")
    _iniciar_sesion_admin(cliente)
    hoy = hoy_negocio().isoformat()

    r = cliente.get(f"/reportes/ventas/exportar?desde={hoy}&hasta={hoy}")

    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/csv")
    assert f'attachment; filename="ventas_{hoy}_a_{hoy}.csv"' == r.headers["Content-Disposition"]
    assert r.data.startswith(b"\xef\xbb\xbf")
    assert b"Total de ventas (COP);17000" in r.data


def test_pantalla_de_ventas_ofrece_el_enlace_de_descarga(app, cliente):
    _iniciar_sesion_admin(cliente)
    hoy = hoy_negocio().isoformat()

    html = cliente.get(f"/reportes/ventas?desde={hoy}&hasta={hoy}").data.decode()

    assert f"/reportes/ventas/exportar?desde={hoy}&amp;hasta={hoy}" in html or \
        f"/reportes/ventas/exportar?desde={hoy}&hasta={hoy}" in html


def test_interfaz_exportar_con_periodo_invalido_vuelve_al_reporte(app, cliente):
    _iniciar_sesion_admin(cliente)
    hoy = hoy_negocio().isoformat()

    r = cliente.get(f"/reportes/ventas/exportar?desde={hoy}&hasta=2020-01-01", follow_redirects=True)

    assert r.status_code == 200 and b"posterior" in r.data


def test_exportar_solo_para_administrador(app, cliente):
    sin_sesion = cliente.get("/reportes/ventas/exportar")
    assert sin_sesion.status_code == 302 and "/login" in sin_sesion.headers["Location"]

    _iniciar_sesion_gestor(cliente)
    assert cliente.get("/reportes/ventas/exportar").status_code == 403
