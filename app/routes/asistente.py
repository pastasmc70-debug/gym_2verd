"""Asistente de primera vez: 4 pasos para dejar el sistema listo. Solo existe mientras no haya administrador."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from .. import permisos
from ..db import get_db
from ..formatting import monto_form
from ..services import configuracion
from ..services.errors import ErrorDeNegocio

bp = Blueprint("asistente", __name__, url_prefix="/asistente")

PASOS = 4


def _primer_paso(estado: dict) -> int:
    """El primer paso que todavía no se completó (no se puede saltear ninguno)."""
    if "nombre" not in estado:
        return 1
    if "usuario" not in estado or "clave_hash" not in estado:
        return 2
    if "planes" not in estado:
        return 3
    return 4


def _valores_planes(estado: dict) -> dict:
    guardados = estado.get("planes") or [{"nombre": "Mensual", "precio_centavos": None, "duracion_dias": 30}]
    valores = {}
    for i, p in enumerate(guardados, start=1):
        valores[f"p{i}_nombre"] = p["nombre"]
        valores[f"p{i}_precio"] = monto_form(p["precio_centavos"]) if p["precio_centavos"] else ""
        valores[f"p{i}_duracion"] = p["duracion_dias"]
    return valores


@bp.get("/")
def inicio():
    return redirect(url_for("asistente.paso", n=_primer_paso(session.get("asistente", {}))))


@bp.route("/<int:n>", methods=["GET", "POST"])
def paso(n):
    if not 1 <= n <= PASOS:
        abort(404)
    estado = dict(session.get("asistente", {}))
    if n > _primer_paso(estado):
        return redirect(url_for("asistente.paso", n=_primer_paso(estado)))
    cfg, db = current_app.config, get_db()
    errores, valores = {}, {}

    if n == 1:
        valores = {"nombre": estado.get("nombre", "")}
    elif n == 2:
        valores = {"usuario": estado.get("usuario", "")}
    elif n == 3:
        valores = _valores_planes(estado)

    if request.method == "POST":
        if n == 1:
            nombre, error = configuracion.validar_nombre(request.form.get("nombre"))
            valores = {"nombre": nombre}
            if error:
                errores["nombre"] = error
            else:
                estado["nombre"] = nombre
        elif n == 2:
            datos, errores = configuracion.validar_administrador(request.form, cfg.get("RECEPCION_USER"))
            valores = {"usuario": datos["usuario"]}  # la clave nunca vuelve a la pantalla
            if not errores:
                estado["usuario"] = datos["usuario"]
                estado["clave_hash"] = configuracion.hash_de(request.form["clave"], cfg.get("HASH_METODO"))
        elif n == 3:
            planes, errores = configuracion.validar_planes(db, request.form)
            valores = dict(request.form)
            if not errores:
                estado["planes"] = [dict(nombre=p["nombre"], precio_centavos=p["precio_centavos"],
                                         duracion_dias=p["duracion_dias"]) for p in planes]
        else:
            if request.form.get("tienda") not in ("1", "0"):
                errores["tienda"] = "Elegí si querés activar la tienda o no."
            else:
                try:
                    configuracion.completar_asistente(
                        db, cfg, nombre=estado["nombre"], usuario=estado["usuario"], clave_hash=estado["clave_hash"],
                        planes=estado["planes"], tienda=request.form["tienda"] == "1")
                except ErrorDeNegocio as e:
                    session.pop("asistente", None)
                    flash(str(e), "danger")
                    return redirect(url_for("auth.login"))
                configuracion.aplicar(cfg, db)
                permisos.iniciar_sesion(permisos.ADMIN, estado["usuario"])
                flash("¡Listo! El sistema quedó configurado. Ya podés empezar a cargar socios.", "success")
                return redirect(url_for("inicio.panel"))

        if errores:
            flash("Revisá los campos marcados en rojo.", "danger")
        else:
            session["asistente"] = estado
            return redirect(url_for("asistente.paso", n=n + 1))

    return render_template("asistente/paso.html", n=n, pasos=PASOS, valores=valores, errores=errores,
                           resumen=estado, CLAVE_MIN=configuracion.CLAVE_MIN,
                           filas=range(1, configuracion.PLANES_EN_ASISTENTE + 1))
