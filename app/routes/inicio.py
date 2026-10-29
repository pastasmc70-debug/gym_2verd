from flask import Blueprint, current_app, render_template

from .. import timeutils
from ..db import get_db
from .. import permisos
from ..services import backup_auto, dashboard, tienda

bp = Blueprint("inicio", __name__)


@bp.get("/")
def panel():
    cfg = current_app.config
    hoy = timeutils.hoy()
    db = get_db()
    datos = dashboard.resumen(db, hoy, cfg["DIAS_ALERTA"])
    tienda_mes = tienda.ingresos_del_mes(db, hoy) if cfg["MODULO_TIENDA"] else None
    adentro = dashboard.adentro_ahora(db, timeutils.ahora(), cfg["HORAS_ADENTRO"])
    copia = backup_auto.estado(db, cfg) if permisos.es_admin() else None  # recepción no puede arreglarlo: no se le muestra
    return render_template("inicio.html", datos=datos, hoy=hoy, dias_alerta=cfg["DIAS_ALERTA"], tienda_mes=tienda_mes,
                           adentro=adentro, horas_adentro=cfg["HORAS_ADENTRO"], copia=copia)
