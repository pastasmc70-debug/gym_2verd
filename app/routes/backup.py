import io

from flask import Blueprint, current_app, flash, redirect, send_file, url_for

from .. import permisos
from ..services import backup
from ..services.errors import ErrorDeNegocio

bp = Blueprint("backup", __name__, url_prefix="/datos/respaldo")


@bp.post("/")
def descargar():
    """Solo el administrador (ver permisos.py). Se pide por POST con token CSRF."""
    cfg = current_app.config
    contenido = io.BytesIO()
    try:
        backup.crear_respaldo(cfg["DATABASE"], cfg["UPLOAD_DIR"], contenido)
    except ErrorDeNegocio as e:
        flash(str(e), "danger")
        return redirect(url_for("exportar.pagina"))
    contenido.seek(0)
    current_app.logger.info("Copia de seguridad descargada por %s", permisos.usuario_actual())
    return send_file(contenido, mimetype="application/zip", as_attachment=True,
                     download_name=backup.nombre_de_archivo())
