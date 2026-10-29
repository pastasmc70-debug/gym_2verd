import hmac
import time

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .. import permisos
from ..db import get_db
from ..services import usuarios

bp = Blueprint("auth", __name__)

# Freno básico contra fuerza bruta: 5 intentos fallidos por IP cada 5 minutos.
# Vive en memoria de cada proceso (si corrés varios workers, el límite es por worker).
_INTENTOS: dict[str, list[float]] = {}
MAX_INTENTOS, VENTANA = 5, 300


def _bloqueado(ip: str) -> bool:
    ahora = time.monotonic()
    recientes = [t for t in _INTENTOS.get(ip, []) if ahora - t < VENTANA]
    _INTENTOS[ip] = recientes
    return len(recientes) >= MAX_INTENTOS


def _destino_seguro(destino: str | None) -> str:
    if destino and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return url_for("inicio.panel")


def _identificar(usuario: str, clave: str):
    """Devuelve (rol, sello) si el usuario y la clave son correctos, o (None, None). El administrador viene de las
    variables de entorno; recepción, de la base. Siempre se evalúan las dos claves, así el tiempo de respuesta
    no delata qué usuario existe."""
    cfg = current_app.config
    es_admin = hmac.compare_digest(usuario.encode(), cfg["ADMIN_USER"].encode())
    clave_admin = check_password_hash(cfg["ADMIN_PASSWORD_HASH"], clave)
    cuenta = usuarios.autenticar(get_db(), usuario, clave)
    if es_admin and clave_admin:
        return permisos.ADMIN, None
    if cuenta is not None:
        return permisos.RECEPCION, usuarios.sello(cuenta)
    return None, None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if permisos.rol_actual() in (permisos.ADMIN, permisos.RECEPCION):
        return redirect(url_for("inicio.panel"))
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _bloqueado(ip):
            flash("Demasiados intentos fallidos. Esperá unos minutos y probá de nuevo.", "danger")
            return render_template("login.html"), 429
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("clave", "")
        rol, sello = _identificar(usuario, clave)
        if rol:
            _INTENTOS.pop(ip, None)
            nombre = usuarios.normalizar(usuario) if rol == permisos.RECEPCION else usuario
            permisos.iniciar_sesion(rol, nombre, sello)
            return redirect(_destino_seguro(request.args.get("next")))
        _INTENTOS.setdefault(ip, []).append(time.monotonic())
        flash("Usuario o clave incorrectos.", "danger")
    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    flash("Cerraste la sesión.", "success")
    return redirect(url_for("auth.login"))
