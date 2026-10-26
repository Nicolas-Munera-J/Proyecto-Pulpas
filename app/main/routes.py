from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.inventario.servicios import listar_existencias, listar_stock_bajo
from app.pedidos.servicios import listar_pedidos_del_dia

main_bp = Blueprint("main", __name__, template_folder="../templates")


@main_bp.route("/")
@login_required
def dashboard():
    productos = listar_existencias()
    productos_stock_bajo = listar_stock_bajo()
    return render_template(
        "dashboard.html",
        productos=productos,
        productos_stock_bajo=productos_stock_bajo,
        pedidos_hoy=listar_pedidos_del_dia(),
    )
