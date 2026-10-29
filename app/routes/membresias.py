from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from .. import models, permisos, timeutils
from ..db import get_db
from ..services import memberships, payments
from ..services.errors import ErrorDeNegocio
from ..timeutils import fecha_ar
from . import socios as socios_routes

bp = Blueprint("membresias", __name__)


@bp.get("/membresias/nueva")
def elegir():
    """Asignar o renovar un plan: primero se elige al socio de la lista."""
    q = request.args.get("q", "").strip()
    return render_template("socios/elegir_para_plan.html", q=q,
                           sel=socios_routes.contexto_selector("membresia", q, url_for("membresias.elegir")))


@bp.route("/socios/<int:socio_id>/membresia", methods=["GET", "POST"])
def asignar(socio_id):
    db = get_db()
    socio = models.obtener_socio(db, socio_id)
    if socio is None:
        abort(404)
    planes = models.listar_planes(db, solo_activos=True)
    valores = {"fecha_inicio": timeutils.hoy().isoformat()}
    a_acumular = 0
    if request.method == "POST":
        valores = request.form
        plan_id = request.form.get("plan_id", type=int)
        inicio = timeutils.parse_fecha(request.form.get("fecha_inicio"))
        decision = request.form.get("acumular")          # "1" acumular, "0" no acumular, vacío: todavía no eligió
        try:
            if inicio is None:
                raise ErrorDeNegocio("La fecha de inicio no es válida.")
            if plan_id is None:
                raise ErrorDeNegocio("Elegí un plan.")
            a_acumular = memberships.dias_vigentes_a_acumular(db, socio_id, inicio)
            if a_acumular > 0 and decision not in ("0", "1"):
                # Tiene días vigentes: hay que avisarle y que elija qué hacer con ellos.
                return render_template("socios/membresia_form.html", socio=socio, planes=planes, valores=valores,
                                       a_acumular=a_acumular)
            r = memberships.asignar_plan(db, socio_id, plan_id, inicio, acumular=(decision == "1"),
                                         cargada_por=permisos.usuario_actual())
        except ErrorDeNegocio as e:
            flash(str(e), "danger")
        else:
            extra = (f" Se acumularon {r['dias_acumulados']} días de la membresía anterior."
                     if r["dias_acumulados"] else "")
            flash(f"Plan «{r['plan']['nombre']}» asignado. Vence el {fecha_ar(r['fecha_vencimiento'])}.{extra}", "success")
            return redirect(url_for("socios.detalle", socio_id=socio_id))
    return render_template("socios/membresia_form.html", socio=socio, planes=planes, valores=valores, a_acumular=0)


@bp.route("/membresias/<int:membresia_id>/anular", methods=["GET", "POST"])
def anular(membresia_id):
    db = get_db()
    m = models.obtener_membresia(db, membresia_id)
    if m is None:
        abort(404)
    socio = models.obtener_socio(db, m["socio_id"])
    error = None
    if request.method == "POST":
        try:
            payments.anular_membresia(db, membresia_id, request.form.get("motivo"), permisos.usuario_actual())
        except ErrorDeNegocio as e:
            error = str(e)
        else:
            flash("Membresía anulada.", "success")
            return redirect(url_for("socios.detalle", socio_id=m["socio_id"]))
    return render_template("socios/membresia_anular.html", m=m, socio=socio, error=error,
                           motivo=request.form.get("motivo", ""),
                           tiene_pagos=not payments.es_primer_pago(db, membresia_id))
