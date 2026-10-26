from datetime import date

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.auth.decoradores import requiere_administrador
from app.errores import ErrorDeNegocio
from app.reportes.servicios import exportar_ventas_csv, productos_mas_vendidos, resumen_ventas
from app.tiempo import hoy_negocio

reportes_bp = Blueprint("reportes", __name__, template_folder="../templates/reportes")


def _leer_periodo(argumentos):
    """Periodo de la URL (?desde=...&hasta=...). Por defecto, del primer día
    del mes actual hasta hoy. Una fecha mal escrita se ignora con un aviso."""
    hoy = hoy_negocio()
    predeterminado = {"desde": hoy.replace(day=1), "hasta": hoy}
    periodo = {}
    for nombre in ("desde", "hasta"):
        texto = argumentos.get(nombre)
        try:
            periodo[nombre] = date.fromisoformat(texto) if texto else predeterminado[nombre]
        except ValueError:
            flash(f"La fecha '{nombre}' no es válida; se usó la predeterminada.", "error")
            periodo[nombre] = predeterminado[nombre]
    return periodo["desde"], periodo["hasta"]


@reportes_bp.route("/reportes/ventas")
@login_required
@requiere_administrador
def ventas():
    """HU17 - Reporte de ventas por periodo."""
    desde, hasta = _leer_periodo(request.args)
    try:
        resumen = resumen_ventas(desde, hasta)
    except ErrorDeNegocio as error:
        flash(str(error), "error")
        resumen = None
    return render_template("reportes/ventas.html", desde=desde, hasta=hasta, resumen=resumen)


@reportes_bp.route("/reportes/productos-mas-vendidos")
@login_required
@requiere_administrador
def productos():
    """HU18 - Productos más vendidos en un periodo."""
    desde, hasta = _leer_periodo(request.args)
    try:
        ranking = productos_mas_vendidos(desde, hasta)
    except ErrorDeNegocio as error:
        flash(str(error), "error")
        ranking = None
    return render_template("reportes/productos.html", desde=desde, hasta=hasta, ranking=ranking)


@reportes_bp.route("/reportes/ventas/exportar")
@login_required
@requiere_administrador
def exportar_ventas():
    """HU19 - Descarga el reporte de ventas del periodo como archivo CSV."""
    desde, hasta = _leer_periodo(request.args)
    try:
        contenido = exportar_ventas_csv(desde, hasta)
    except ErrorDeNegocio as error:
        flash(str(error), "error")
        return redirect(url_for("reportes.ventas"))

    nombre_archivo = f"ventas_{desde.isoformat()}_a_{hasta.isoformat()}.csv"
    return Response(
        contenido.encode("utf-8"),
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )
