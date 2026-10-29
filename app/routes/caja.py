from datetime import timedelta

from flask import Blueprint, current_app, render_template, request

from .. import timeutils
from ..db import get_db
from ..services import caja, tienda

bp = Blueprint("caja", __name__, url_prefix="/caja")


@bp.get("/")
def diaria():
    hoy = timeutils.hoy()
    fecha = timeutils.parse_fecha(request.args.get("fecha")) or hoy
    if fecha > hoy:
        fecha = hoy
    db = get_db()
    cuotas = caja.cuotas_del_dia(db, fecha)
    venta_tienda = tienda.caja_del_dia(db, fecha) if current_app.config["MODULO_TIENDA"] else None
    return render_template("caja/diaria.html", fecha=fecha, hoy=hoy, cuotas=cuotas, tienda=venta_tienda,
                           ayer=fecha - timedelta(days=1),
                           manana=(fecha + timedelta(days=1)) if fecha < hoy else None)
