from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from .. import models, permisos, timeutils
from ..db import get_db
from ..services import attendance, memberships
from ..services.attendance import ReglasIngreso
from ..services.errors import ErrorDeNegocio
from . import socios as socios_routes

bp = Blueprint("asistencia", __name__, url_prefix="/asistencia")


def _pantalla(candidatos=None, q=""):
    hoy = timeutils.hoy()
    db = get_db()
    tarjeta = None
    pendiente = session.pop("tarjeta_ingreso", None)  # se muestra una sola vez, justo después de registrar
    if pendiente:
        tarjeta = attendance.tarjeta_ingreso(db, pendiente["socio_id"], hoy, current_app.config["DIAS_ALERTA"])
        if tarjeta:
            tarjeta["hora"] = pendiente["hora"]
    return render_template("asistencia.html", hoy=hoy, candidatos=candidatos, q=q, tarjeta=tarjeta,
                           ingresos=models.asistencias_del_dia(db, hoy),
                           sel=socios_routes.contexto_selector("ingreso", q, url_for("asistencia.pantalla")))


@bp.get("/")
def pantalla():
    return _pantalla()


@bp.post("/ingreso")
def ingreso():
    db, cfg = get_db(), current_app.config
    socio_id = request.form.get("socio_id", type=int)
    q = request.form.get("q", "").strip()

    if socio_id is None:
        if not q:
            flash("Ingresá un DNI o un nombre para buscar al socio.", "warning")
            return redirect(url_for("asistencia.pantalla"))
        encontrados = attendance.buscar_socios(db, q)
        if not encontrados:
            flash("No encontramos ningún socio con ese DNI o nombre.", "danger")
            return redirect(url_for("asistencia.pantalla"))
        if len(encontrados) > 1:
            hoy = timeutils.hoy()
            candidatos = [memberships.enriquecer(f, hoy, cfg["DIAS_ALERTA"]) for f in encontrados]
            return _pantalla(candidatos=candidatos, q=q)
        socio_id = encontrados[0]["id"]

    try:
        r = attendance.registrar_ingreso(db, socio_id, dias_alerta=cfg["DIAS_ALERTA"],
                                         reglas=ReglasIngreso.desde_config(cfg), usuario=permisos.usuario_actual())
    except ErrorDeNegocio as e:
        flash(str(e), "danger")
    else:
        session["tarjeta_ingreso"] = {"socio_id": r["socio"]["id"], "hora": timeutils.ahora().strftime("%H:%M")}
        flash(f"Ingreso registrado: {r['socio']['nombre']} ({r['socio']['plan_nombre']}).", "success")
        if r["aviso_clases"]:
            flash(r["aviso_clases"], "info")
        if r["aviso"]:
            flash(r["aviso"], "warning")
    return redirect(url_for("asistencia.pantalla"))
