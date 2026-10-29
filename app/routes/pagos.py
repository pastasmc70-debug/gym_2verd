from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from .. import models, permisos, timeutils
from ..db import get_db
from ..formatting import monto_form, pesos
from ..services import memberships, payments
from . import socios as socios_routes
from ..services.errors import ErrorDeNegocio, RequiereConfirmacion
from ..services.validation import validar_pago
from ..timeutils import fecha_ar

bp = Blueprint("pagos", __name__, url_prefix="/pagos")


@bp.get("/")
def lista():
    return render_template("pagos/lista.html", pagos=models.pagos_recientes(get_db()))


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    db, cfg = get_db(), current_app.config
    socio_id = request.values.get("socio_id", type=int)

    if socio_id is None:  # primer paso: elegir al socio
        q = request.args.get("q", "").strip()
        return render_template("pagos/buscar.html", q=q, sel=socios_routes.contexto_selector("pago", q, url_for("pagos.nuevo")))

    fila = models.obtener_socio(db, socio_id)
    if fila is None:
        abort(404)
    hoy = timeutils.hoy()
    socio = memberships.enriquecer(fila, hoy, cfg["DIAS_ALERTA"])
    actual = models.membresia_actual(db, socio_id)
    estado = payments.reproducir(db, actual["id"]) if actual else None
    opciones = payments.opciones_de_periodos(actual, estado) if actual else []
    errores, confirmacion = {}, None

    def formulario(valores):
        return render_template("pagos/form.html", socio=socio, actual=actual, valores=valores, errores=errores,
                               estado=estado, opciones=opciones)

    if request.method == "POST" and not request.form.get("corregir"):
        form = request.form.to_dict()
        periodos = (form.get("periodos") or "1").strip()
        elegida = next((o for o in opciones if o["valor"] == periodos), None)
        if actual and elegida is None:
            errores["periodos"] = "Elegí cuántos períodos paga."
        elif elegida and not form.get("monto", "").strip():
            form["monto"] = monto_form(elegida["monto_centavos"])  # sin monto escrito: el calculado para esos períodos
        datos, errs = validar_pago(form, hoy)
        errores.update(errs)
        if not errores:
            try:
                r = payments.registrar_pago(
                    db, socio_id, datos["monto_centavos"], datos["fecha"], datos["metodo"], datos["nota"],
                    cargado_por=permisos.usuario_actual(), anual=periodos == "anual",
                    confirmar=bool(form.get("confirmar") or form.get("confirmar_parcial")))
            except RequiereConfirmacion as e:
                # No se guardó nada: pantalla de confirmación con lo que pasaría, y se pide confirmar de forma explícita.
                return render_template("pagos/confirmar.html", socio=socio, actual=actual, valores=form,
                                       tipo=e.codigo, datos=e.datos, vista=e.datos["vista"],
                                       monto_centavos=datos["monto_centavos"])
            except ErrorDeNegocio as e:
                flash(str(e), "danger")
            else:
                flash(_mensaje_de_pago(r), "warning" if r["es_parcial"] else "success")
                return redirect(url_for("socios.detalle", socio_id=socio_id, pago=r["pago_id"]))
        else:
            flash("Revisá los campos marcados en rojo.", "danger")
        return formulario(form)

    if request.method == "POST":  # "Corregir": vuelve al formulario con lo que se había escrito
        return formulario(request.form)

    valores = {"fecha": hoy.isoformat(), "metodo": "efectivo", "periodos": "1"}
    if actual:
        valores["monto"] = monto_form(opciones[0]["monto_centavos"])
    return formulario(valores)


def _mensaje_de_pago(r) -> str:
    if r["es_parcial"]:
        return (f"Pago parcial registrado. Todavía faltan {pesos(r['faltante_centavos'])} para completar "
                "el período; la membresía no se extendió.")
    if r["cubrio_periodo_inicial"] and r["periodos_cubiertos"] == 1:
        return f"Pago registrado. Cubre el período inicial del plan: vence el {fecha_ar(r['vencimiento_nuevo'])}."
    return (f"Pago registrado. Cubre {r['periodos_cubiertos']} "
            f"{'período' if r['periodos_cubiertos'] == 1 else 'períodos'}: "
            f"la membresía ahora vence el {fecha_ar(r['vencimiento_nuevo'])}.")


@bp.route("/<int:pago_id>/anular", methods=["GET", "POST"])
def anular(pago_id):
    db = get_db()
    pago = models.obtener_pago(db, pago_id)
    if pago is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            r = payments.anular_pago(db, pago_id, request.form.get("motivo"), permisos.usuario_actual())
        except ErrorDeNegocio as e:
            error = str(e)
        else:
            flash(f"Pago anulado. La membresía ahora vence el {fecha_ar(r['vencimiento'])}.", "success")
            return redirect(url_for("socios.detalle", socio_id=pago["socio_id"]))
    return render_template("pagos/anular.html", pago=pago, error=error, motivo=request.form.get("motivo", ""))
