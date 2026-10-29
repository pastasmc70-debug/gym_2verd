"""Fábrica de la aplicación Flask."""
import hmac
import secrets
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from . import db, permisos, timeutils
from .services import backup_auto, configuracion, usuarios
from .formatting import monto_form, pesos
from .config import config_desde_entorno, validar_config
from .version import __version__
from .models import ESTADOS_SOCIO, METODOS_PAGO, POR_VENCER, SIN_MEMBRESIA, VENCIDA, VIGENTE

METODOS_ESCRITURA = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(test_config=None, instance_path=None):
    """`instance_path` permite guardar los datos fuera de la carpeta del programa (instalación de Windows)."""
    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    app.config.update(config_desde_entorno(app.instance_path))
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        # Sin GYM_SECRET_KEY la clave se genera sola y se guarda en la carpeta de datos (junto a la base).
        base = app.config["DATABASE"]
        carpeta = app.instance_path if base == ":memory:" else str(Path(base).parent)
        app.config["SECRET_KEY"] = configuracion.clave_secreta(carpeta)
    validar_config(app.config)

    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    conn = db.connect(app.config["DATABASE"])
    db.init_schema(conn)
    configuracion.aplicar(app.config, conn)
    usuarios.importar_de_entorno(conn, app.config.get("RECEPCION_USER"), app.config.get("RECEPCION_PASSWORD_HASH"))
    conn.close()
    app.teardown_appcontext(db.close_db)

    # ---------------------------------------------------------- plantillas
    app.jinja_env.globals["app_version"] = __version__
    app.jinja_env.filters["pesos"] = pesos
    app.jinja_env.filters["monto_form"] = monto_form
    app.jinja_env.filters["fecha"] = timeutils.fecha_ar

    def csrf_token() -> str:
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    app.jinja_env.globals.update(
        csrf_token=csrf_token,
        ESTADOS_SOCIO=ESTADOS_SOCIO,
        METODOS_PAGO=METODOS_PAGO,
        VIGENTE=VIGENTE, POR_VENCER=POR_VENCER, VENCIDA=VENCIDA, SIN_MEMBRESIA=SIN_MEMBRESIA,
    )

    @app.context_processor
    def contexto():
        rol = permisos.rol_actual()
        return {"rol": rol, "es_admin": rol == permisos.ADMIN, "usuario": session.get("usuario") if rol else None,
                "tienda_activa": app.config["MODULO_TIENDA"], "gym_nombre": app.config["GYM_NOMBRE"]}

    # ------------------------------------------- seguridad (por defecto, todo requiere login)
    ABIERTOS = ("auth.login", "kiosco.entrar")

    @app.before_request
    def proteger():
        endpoint = request.endpoint
        if endpoint in (None, "static"):
            return None
        if request.method in METODOS_ESCRITURA and app.config["CSRF_ACTIVO"]:
            esperado = session.get("csrf", "")
            recibido = request.form.get("csrf_token", "")
            if not esperado or not hmac.compare_digest(esperado, recibido):
                abort(400, description="La sesión expiró o el formulario no es válido. Recargá la página e intentá de nuevo.")
        configuracion.aplicar(app.config, db.get_db())  # lo guardado en Configuración vale en todos los procesos
        if not configuracion.hay_administrador(app.config):
            # Primera vez: sin administrador todo lleva al asistente.
            return None if endpoint.startswith("asistente.") else redirect(url_for("asistente.inicio"))
        if endpoint.startswith("asistente."):  # con administrador el asistente no se puede repetir
            return redirect(url_for("auth.login"))
        if endpoint in ABIERTOS:
            return None
        rol = permisos.rol_actual()
        if rol is None:
            login = "kiosco.entrar" if endpoint.startswith("kiosco.") else "auth.login"
            destino = request.full_path.rstrip("?") if request.method == "GET" and login == "auth.login" else None
            return redirect(url_for(login, next=destino))
        if rol == permisos.RECEPCION and not usuarios.sesion_vigente(db.get_db(), session.get("usuario"), session.get("sello")):
            session.clear()  # la cuenta se desactivó o le cambiaron la clave
            flash("Tu sesión se cerró porque la cuenta cambió. Ingresá de nuevo.", "warning")
            return redirect(url_for("auth.login"))
        if not permisos.puede(endpoint, rol):
            if rol == permisos.KIOSCO:
                return redirect(url_for("kiosco.pantalla"))
            if endpoint.startswith("kiosco."):  # el personal entra al kiosco con la clave del kiosco
                return redirect(url_for("kiosco.entrar"))
            abort(403)
        return None

    @app.after_request
    def cabeceras(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.errorhandler(400)
    def error_400(e):
        return render_template("error.html", titulo="Solicitud inválida", mensaje=e.description), 400

    @app.errorhandler(403)
    def error_403(e):
        return render_template("error.html", titulo="Sin permiso",
                               mensaje="Tu usuario no tiene permiso para hacer esto. Pedile ayuda al administrador."), 403

    @app.errorhandler(404)
    def error_404(e):
        return render_template("error.html", titulo="No encontrado",
                               mensaje="La página o el registro que buscás no existe."), 404

    @app.errorhandler(413)
    def error_413(e):
        return render_template("error.html", titulo="Archivo demasiado grande",
                               mensaje="La foto supera el tamaño máximo permitido (3 MB)."), 413

    @app.errorhandler(500)
    def error_500(e):
        return render_template("error.html", titulo="Algo salió mal",
                               mensaje="Ocurrió un error inesperado. Probá de nuevo en un momento."), 500

    # --------------------------------------------------------------- rutas
    from .routes import (alertas, asistencia, asistente, auth, backup, caja, configuracion as pantalla_config, exportar,
                         importar, inicio, kiosco, membresias, pagos, planes, socios, tienda)
    from .routes import usuarios as rutas_usuarios

    for modulo in (auth, asistente, pantalla_config, inicio, socios, planes, membresias, pagos, asistencia, alertas, exportar,
                   backup, importar, caja, kiosco, tienda, rutas_usuarios):
        app.register_blueprint(modulo.bp)

    if app.config["BACKUP_HILO"] and not app.config.get("TESTING"):
        backup_auto.iniciar_hilo(app)

    return app
