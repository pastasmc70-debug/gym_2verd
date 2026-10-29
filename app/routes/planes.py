import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import models
from ..db import get_db
from ..formatting import monto_form
from ..services.validation import validar_plan

bp = Blueprint("planes", __name__, url_prefix="/planes")


@bp.get("/")
def lista():
    db = get_db()
    planes = [dict(p, socios=models.cantidad_membresias_del_plan(db, p["id"])) for p in models.listar_planes(db)]
    return render_template("planes/lista.html", planes=planes)


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    db = get_db()
    errores = {}
    if request.method == "POST":
        datos, errores = validar_plan(db, request.form)
        if not errores:
            try:
                with db:
                    models.crear_plan(db, datos)
            except sqlite3.IntegrityError:
                errores["nombre"] = "Ya existe un plan con ese nombre."
            else:
                flash(f"Plan «{datos['nombre']}» creado.", "success")
                return redirect(url_for("planes.lista"))
        flash("Revisá los campos marcados en rojo.", "danger")
        return render_template("planes/form.html", valores=request.form, errores=errores, plan=None)
    return render_template("planes/form.html", valores={}, errores=errores, plan=None)


@bp.route("/<int:plan_id>/editar", methods=["GET", "POST"])
def editar(plan_id):
    db = get_db()
    plan = models.obtener_plan(db, plan_id)
    if plan is None:
        abort(404)
    errores = {}
    if request.method == "POST":
        datos, errores = validar_plan(db, request.form, plan_id=plan_id)
        if not errores:
            try:
                with db:
                    models.actualizar_plan(db, plan_id, datos)
            except sqlite3.IntegrityError:
                errores["nombre"] = "Ya existe un plan con ese nombre."
            else:
                flash("Plan actualizado. Las membresías ya vendidas conservan su vencimiento.", "success")
                return redirect(url_for("planes.lista"))
        flash("Revisá los campos marcados en rojo.", "danger")
        return render_template("planes/form.html", valores=request.form, errores=errores, plan=plan)
    valores = {
        "nombre": plan["nombre"], "precio": monto_form(plan["precio_centavos"]), "duracion_dias": plan["duracion_dias"],
        "clases_por_semana": plan["clases_por_semana"], "ilimitado": plan["clases_por_semana"] is None,
        "descuento_tipo": plan["descuento_anual_tipo"] or "",
        "descuento_valor": ("" if not plan["descuento_anual_tipo"] else plan["descuento_anual_valor"]
                            if plan["descuento_anual_tipo"] == "porcentaje" else monto_form(plan["descuento_anual_valor"])),
    }
    return render_template("planes/form.html", valores=valores, errores=errores, plan=plan)


@bp.post("/<int:plan_id>/<accion>")
def activar_o_desactivar(plan_id, accion):
    if accion not in ("activar", "desactivar"):
        abort(404)
    db = get_db()
    plan = models.obtener_plan(db, plan_id)
    if plan is None:
        abort(404)
    with db:
        models.cambiar_activo_plan(db, plan_id, accion == "activar")
    if accion == "activar":
        flash(f"Plan «{plan['nombre']}» activado: vuelve a aparecer al asignar planes.", "success")
    else:
        flash(f"Plan «{plan['nombre']}» desactivado. No se puede asignar a nuevos socios; "
              "los que ya lo tienen no se modifican.", "success")
    return redirect(url_for("planes.lista"))


@bp.post("/<int:plan_id>/eliminar")
def eliminar(plan_id):
    db = get_db()
    plan = models.obtener_plan(db, plan_id)
    if plan is None:
        abort(404)
    if models.cantidad_membresias_del_plan(db, plan_id):
        flash(f"No se puede eliminar «{plan['nombre']}» porque hay socios con ese plan. "
              "Podés editarlo o crear uno nuevo.", "danger")
    else:
        with db:
            models.borrar_plan(db, plan_id)
        flash(f"Plan «{plan['nombre']}» eliminado.", "success")
    return redirect(url_for("planes.lista"))
