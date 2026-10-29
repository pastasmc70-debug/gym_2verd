"""Pantalla «Configuración» del administrador. Lo que se guarda acá pisa a las variables de entorno GYM_*."""
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..services import backup_auto, configuracion

bp = Blueprint("configuracion", __name__, url_prefix="/configuracion")


def _valores_actuales(cfg) -> dict:
    valores = {"gym_nombre": cfg["GYM_NOMBRE"], "horas_adentro": cfg["HORAS_ADENTRO"], "backup_carpeta": cfg.get("BACKUP_DIR") or ""}
    for clave in configuracion.BOOLEANOS:
        valores[clave] = bool(cfg[configuracion.AJUSTES[clave][0]])
    return valores


@bp.route("/", methods=["GET", "POST"])
def pantalla():
    cfg, db = current_app.config, get_db()
    errores = {}
    valores = _valores_actuales(cfg)
    if request.method == "POST":
        guardar, errores = configuracion.validar_ajustes(request.form, cfg)
        carpeta, error_carpeta = backup_auto.validar_carpeta(request.form.get("backup_carpeta"), cfg["UPLOAD_DIR"])
        if error_carpeta:
            errores["backup_carpeta"] = error_carpeta
        guardar["backup_carpeta"] = carpeta
        if not errores:
            if request.form.get("kiosco_clave"):
                guardar["kiosco_clave_hash"] = configuracion.hash_de(request.form["kiosco_clave"], cfg.get("HASH_METODO"))
            configuracion.guardar(db, guardar)
            configuracion.aplicar(cfg, db)
            flash("Configuración guardada.", "success")
            if cfg.get("BACKUP_DIR"):  # carpeta nueva: se hace la copia de hoy enseguida, así se ve que funciona
                copia = backup_auto.ejecutar(db, cfg)
                if copia and copia["ok"]:
                    flash(f"Se hizo la copia de seguridad en {cfg['BACKUP_DIR']}.", "success")
                elif copia:
                    flash(f"No se pudo hacer la copia de seguridad: {copia['error']}", "warning")
            return redirect(url_for("configuracion.pantalla"))
        flash("Revisá los campos marcados en rojo.", "danger")
        valores = {"gym_nombre": request.form.get("gym_nombre", ""), "horas_adentro": request.form.get("horas_adentro", ""),
                   "backup_carpeta": request.form.get("backup_carpeta", ""),
                   **{c: bool(request.form.get(c)) for c in configuracion.BOOLEANOS}}
    return render_template("configuracion/pantalla.html", valores=valores, errores=errores,
                           kiosco_con_clave=bool(cfg.get("KIOSCO_CLAVE_HASH")),
                           copia=backup_auto.estado(db, cfg), CLAVE_MIN=configuracion.CLAVE_MIN)
