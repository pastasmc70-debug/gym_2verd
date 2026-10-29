from flask import Blueprint, current_app, render_template

from .. import models, timeutils
from ..db import get_db
from ..services import dashboard
from ..services.whatsapp import link_whatsapp

bp = Blueprint("alertas", __name__, url_prefix="/alertas")


@bp.get("/")
def lista():
    cfg = current_app.config
    socios = dashboard.socios_con_alerta(get_db(), timeutils.hoy(), cfg["DIAS_ALERTA"])
    for s in socios:
        s["whatsapp"] = link_whatsapp(s, cfg["GYM_NOMBRE"])
    vencidos = [s for s in socios if s["estado_membresia"] == models.VENCIDA]
    por_vencer = [s for s in socios if s["estado_membresia"] == models.POR_VENCER]
    return render_template("alertas.html", vencidos=vencidos, por_vencer=por_vencer,
                           dias_alerta=cfg["DIAS_ALERTA"])
