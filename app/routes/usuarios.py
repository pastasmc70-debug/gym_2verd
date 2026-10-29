"""Cuentas de recepción: las administra el administrador. Todo lo que no figura en permisos.ENDPOINTS_RECEPCION
es solo del administrador, así que recepción no puede entrar acá."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from .. import permisos
from ..db import get_db
from ..services import usuarios
from ..services.errors import ErrorDeNegocio

bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")


@bp.get("/")
def lista():
    return render_template("usuarios/lista.html", cuentas=usuarios.listar(get_db()),
                           admin=current_app.config["ADMIN_USER"])


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    db, errores = get_db(), {}
    if request.method == "POST":
        datos, errores = usuarios.validar_nuevo(db, request.form, current_app.config["ADMIN_USER"])
        if not errores:
            usuarios.crear(db, datos["usuario"], datos["clave"], creado_por=permisos.usuario_actual())
            current_app.logger.info("Cuenta de recepción «%s» creada por %s", datos["usuario"], permisos.usuario_actual())
            flash(f"Cuenta «{datos['usuario']}» creada. Pasale el usuario y la clave a esa persona.", "success")
            return redirect(url_for("usuarios.lista"))
        flash("Revisá los campos marcados en rojo.", "danger")
    return render_template("usuarios/form.html", valores={"usuario": request.form.get("usuario", "")}, errores=errores)


@bp.route("/<int:usuario_id>/clave", methods=["GET", "POST"])
def clave(usuario_id):
    db = get_db()
    cuenta = usuarios.obtener(db, usuario_id)
    if cuenta is None:
        abort(404)
    errores = {}
    if request.method == "POST":
        try:
            usuarios.cambiar_clave(db, usuario_id, request.form.get("clave"), request.form.get("clave2"))
        except ErrorDeNegocio as e:
            errores["clave"] = str(e)
            flash("Revisá los campos marcados en rojo.", "danger")
        else:
            current_app.logger.info("Clave de «%s» cambiada por %s", cuenta["usuario"], permisos.usuario_actual())
            flash(f"Clave de «{cuenta['usuario']}» cambiada. Si tenía la sesión abierta, se le cierra.", "success")
            return redirect(url_for("usuarios.lista"))
    return render_template("usuarios/clave.html", cuenta=cuenta, errores=errores)


@bp.post("/<int:usuario_id>/<accion>")
def activar_o_desactivar(usuario_id, accion):
    if accion not in ("activar", "desactivar"):
        abort(404)
    db = get_db()
    cuenta = usuarios.obtener(db, usuario_id)
    if cuenta is None:
        abort(404)
    usuarios.cambiar_activo(db, usuario_id, accion == "activar")
    flash(f"Cuenta «{cuenta['usuario']}» {'activada' if accion == 'activar' else 'desactivada (no se borra: sus registros siguen a su nombre)'}.", "success")
    return redirect(url_for("usuarios.lista"))
