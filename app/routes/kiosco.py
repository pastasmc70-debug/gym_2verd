import hmac
import time

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.security import check_password_hash

from .. import permisos
from ..db import get_db
from ..services import kiosco
from ..services.attendance import ReglasIngreso

bp = Blueprint("kiosco", __name__, url_prefix="/kiosco")

# Freno para adivinar la clave del kiosco: 5 fallos cada 5 minutos por IP.
_FALLOS_CLAVE: dict[str, list[float]] = {}


def _limitador() -> kiosco.Limitador:
    ext = current_app.extensions
    if "kiosco_limitador" not in ext:
        ext["kiosco_limitador"] = kiosco.Limitador(current_app.config["KIOSCO_MAX_INTENTOS_POR_MINUTO"])
    return ext["kiosco_limitador"]


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    cfg = current_app.config
    if not cfg.get("KIOSCO_CLAVE_HASH"):
        return render_template("kiosco/entrar.html", configurado=False), 503
    if permisos.rol_actual() == permisos.KIOSCO:
        return redirect(url_for("kiosco.pantalla"))
    if request.method == "POST":
        ip = request.remote_addr or "?"
        ahora = time.monotonic()
        recientes = [t for t in _FALLOS_CLAVE.get(ip, []) if ahora - t < 300]
        _FALLOS_CLAVE[ip] = recientes
        if len(recientes) >= 5:
            return render_template("kiosco/entrar.html", configurado=True,
                                   error="Demasiados intentos fallidos. Esperá unos minutos."), 429
        if check_password_hash(cfg["KIOSCO_CLAVE_HASH"], request.form.get("clave", "")):
            _FALLOS_CLAVE.pop(ip, None)
            permisos.iniciar_sesion(permisos.KIOSCO, "kiosco")
            return redirect(url_for("kiosco.pantalla"))
        _FALLOS_CLAVE.setdefault(ip, []).append(ahora)
        return render_template("kiosco/entrar.html", configurado=True, error="La clave del kiosco no es correcta.")
    return render_template("kiosco/entrar.html", configurado=True)


@bp.get("/")
def pantalla():
    cfg = current_app.config
    return render_template("kiosco/pantalla.html", sonido=cfg["KIOSCO_SONIDO"], teclado=cfg["KIOSCO_TECLADO_PANTALLA"])


@bp.post("/ingreso")
def ingreso():
    cfg = current_app.config
    quiere_json = request.headers.get("X-Requested-With") == "kiosco" or request.accept_mimetypes.best == "application/json"
    if not _limitador().intentar(request.remote_addr or "?"):
        resultado = {"ok": False, "mensaje": "Demasiados intentos. Esperá un minuto.", "nombre": "", "foto": None,
                     "estado": "", "dias": ""}
        status = 429
    else:
        resultado = kiosco.resolver_ingreso(get_db(), request.form.get("dni", ""), ReglasIngreso.desde_config(cfg),
                                            cfg["DIAS_ALERTA"])
        status = 200
    resultado["foto_url"] = url_for("kiosco.foto", nombre=resultado["foto"]) if resultado["foto"] else None
    if quiere_json:
        return jsonify(resultado), status
    return render_template("kiosco/resultado.html", r=resultado, sonido=cfg["KIOSCO_SONIDO"]), status


@bp.get("/foto/<nombre>")
def foto(nombre):
    """Solo sirve fotos que pertenecen a un socio (los nombres son aleatorios)."""
    existe = get_db().execute("SELECT 1 FROM socios WHERE foto = ?", (nombre,)).fetchone()
    if not existe:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_DIR"], nombre)


@bp.post("/salir")
def salir():
    from flask import session
    session.clear()
    flash("Saliste del modo kiosco.", "success")
    return redirect(url_for("kiosco.entrar"))
