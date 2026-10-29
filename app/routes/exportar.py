from flask import Blueprint, Response, current_app, render_template

from .. import timeutils
from ..db import get_db
from ..services import exports

bp = Blueprint("exportar", __name__, url_prefix="/exportar")


def _respuesta_csv(contenido: str, nombre: str) -> Response:
    resp = Response(contenido.encode("utf-8"), mimetype="text/csv")
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre}_{timeutils.hoy().isoformat()}.csv"'
    return resp


@bp.get("/")
def pagina():
    return render_template("exportar.html")


@bp.get("/socios.csv")
def socios():
    return _respuesta_csv(exports.socios_csv(get_db(), timeutils.hoy(), current_app.config["DIAS_ALERTA"]), "socios")


@bp.get("/pagos.csv")
def pagos():
    return _respuesta_csv(exports.pagos_csv(get_db()), "pagos")
