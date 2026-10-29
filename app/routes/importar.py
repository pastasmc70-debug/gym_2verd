import re
import secrets
import sqlite3
import time
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from .. import permisos
from ..db import get_db
from ..services import importar
from ..services.errors import ErrorDeNegocio

bp = Blueprint("importar", __name__, url_prefix="/datos/importar")

TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
VIGENCIA_SEGUNDOS = 3600  # el archivo de la vista previa se descarta después de una hora


def _carpeta() -> Path:
    carpeta = Path(current_app.config["IMPORT_DIR"])
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _limpiar_viejos(carpeta: Path) -> None:
    limite = time.time() - VIGENCIA_SEGUNDOS
    for archivo in carpeta.glob("*.csv"):
        if archivo.stat().st_mtime < limite:
            archivo.unlink(missing_ok=True)


@bp.route("/", methods=["GET", "POST"])
def subir():
    if request.method == "GET":
        return render_template("importar/subir.html", campos=importar.CAMPOS,
                               historial=importar.ultimas_importaciones(get_db()))

    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        flash("Elegí el archivo CSV con los socios.", "danger")
        return redirect(url_for("importar.subir"))
    contenido = archivo.read(importar.MAX_BYTES + 1)
    analisis = importar.analizar(get_db(), contenido)

    token = None
    if analisis.puede_confirmar:
        carpeta = _carpeta()
        _limpiar_viejos(carpeta)
        token = secrets.token_hex(16)
        (carpeta / f"{token}.csv").write_bytes(contenido)
    return render_template("importar/vista_previa.html", analisis=analisis, token=token,
                           nombre_archivo=archivo.filename, campos=importar.CAMPOS)


@bp.post("/confirmar")
def confirmar():
    token = request.form.get("token", "")
    if not TOKEN_RE.match(token):
        flash("La vista previa ya no es válida. Subí el archivo de nuevo.", "danger")
        return redirect(url_for("importar.subir"))
    ruta = _carpeta() / f"{token}.csv"
    if not ruta.is_file():
        flash("La vista previa venció. Subí el archivo de nuevo.", "danger")
        return redirect(url_for("importar.subir"))

    db = get_db()
    analisis = importar.analizar(db, ruta.read_bytes())  # se revalida: la base pudo cambiar
    try:
        cantidad = importar.importar(db, analisis)
    except ErrorDeNegocio as e:
        flash(str(e), "danger")
        return redirect(url_for("importar.subir"))
    except sqlite3.IntegrityError:
        flash("Mientras tanto se cargó otro socio con el mismo DNI. No se importó nada: subí el archivo de nuevo.", "danger")
        return redirect(url_for("importar.subir"))
    ruta.unlink(missing_ok=True)
    importar.registrar_importacion(db, permisos.usuario_actual(), cantidad, len(analisis.errores))
    current_app.logger.info("Importación de %s socios por %s", cantidad, permisos.usuario_actual())

    omitidas = len(analisis.errores)
    mensaje = f"Se importaron {cantidad} socio{'s' if cantidad != 1 else ''}."
    if omitidas:
        mensaje += f" Se omitieron {omitidas} fila{'s' if omitidas != 1 else ''} con errores."
    flash(mensaje, "success" if not omitidas else "warning")
    return redirect(url_for("socios.lista"))
