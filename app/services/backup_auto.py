"""Copia de seguridad automática diaria.

Una vez por día (la primera vez que el sistema la revisa después de la medianoche, hora de Buenos Aires)
se guarda un .zip con la base y las fotos en la carpeta que el dueño eligió en Configuración (puede ser una
carpeta sincronizada de Google Drive u OneDrive, o un pendrive). Se conservan las últimas COPIAS_A_CONSERVAR.

Dónde queda anotado qué pasó: en la tabla `configuracion` (claves backup_*), así lo ven todos los procesos.
No depende de Flask salvo `iniciar_hilo`, que corre la revisión en un hilo de fondo.
"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from .. import db as dbm
from .. import timeutils
from . import backup, configuracion
from .errors import ErrorDeNegocio
from .validation import limpiar

COPIAS_A_CONSERVAR = 14
DIAS_PARA_AVISAR = 3          # se avisa cuando hace MÁS de 3 días que no hay una copia
INTERVALO_SEGUNDOS = 15 * 60  # cada cuánto revisa el hilo si toca la copia del día
EN_CURSO_VENCE = timedelta(minutes=15)
TEMPORAL = ".copia-en-curso.tmp"

log = logging.getLogger(__name__)


def _fecha(texto) -> datetime | None:
    try:
        return datetime.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def _iso(ahora: datetime) -> str:
    return ahora.isoformat(timespec="seconds")


# ---------------------------------------------------------------- carpeta elegida
def validar_carpeta(texto, carpeta_fotos: str | None = None) -> tuple[str, str | None]:
    """Devuelve (ruta limpia, error). Vacío es válido: apaga la copia automática."""
    texto = limpiar(texto)
    if not texto:
        return "", None
    ruta = Path(texto)
    if not ruta.is_absolute():
        return texto, "Escribí la ruta completa de la carpeta, por ejemplo D:\\Copias o /mnt/usb/copias."
    if carpeta_fotos:
        fotos = Path(carpeta_fotos).resolve()
        if ruta.resolve() == fotos or fotos in ruta.resolve().parents:
            return texto, "La carpeta de copias no puede estar dentro de la carpeta de fotos."
    try:
        ruta.mkdir(parents=True, exist_ok=True)
        prueba = ruta / ".prueba-de-escritura"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
    except OSError as e:
        return texto, f"No se puede guardar en esa carpeta: {e.strerror or e}."
    return str(ruta), None


# ----------------------------------------------------------------------- estado
def estado(db, config, ahora: datetime | None = None) -> dict:
    """Lo que muestran el panel y Configuración: última copia y si hay que avisar algo."""
    ahora = ahora or timeutils.ahora()
    g = configuracion.leer_todo(db)
    carpeta = config.get("BACKUP_DIR") or ""
    ultima = _fecha(g.get("backup_ultimo_ok"))
    error_en, error = _fecha(g.get("backup_error_en")), g.get("backup_error_msg") or ""
    dias = (ahora.date() - ultima.date()).days if ultima else None
    r = {"carpeta": carpeta, "ultima": ultima, "dias": dias, "error": error, "nivel": "ok", "mensaje": ""}
    if not carpeta:
        r.update(nivel="aviso", mensaje="La copia de seguridad automática no está configurada. Elegí una carpeta en Configuración.")
    elif ultima is None:
        r.update(nivel="aviso", mensaje="Todavía no se hizo ninguna copia de seguridad automática.")
    elif dias > DIAS_PARA_AVISAR:
        r.update(nivel="peligro", mensaje=f"Hace {dias} días que no se hace una copia de seguridad.")
    if carpeta and error and (ultima is None or (error_en and error_en > ultima)):
        r["mensaje"] = (r["mensaje"] + " " if r["mensaje"] else "") + f"La última copia automática falló: {error}"
        if r["nivel"] == "ok":
            r["nivel"] = "aviso"
    return r


# ---------------------------------------------------------------------- ejecutar
def _corresponde(g: dict, carpeta: str, ahora: datetime) -> bool:
    ultima = _fecha(g.get("backup_ultimo_ok"))
    return ultima is None or ultima.date() < ahora.date() or g.get("backup_ultima_carpeta") != carpeta


def ejecutar(db, config, ahora: datetime | None = None, forzar: bool = False) -> dict | None:
    """Hace la copia del día si corresponde. Devuelve None si no tocaba (o no hay carpeta), o
    {"ok": True, "archivo": ...} / {"ok": False, "error": ...}."""
    ahora = ahora or timeutils.ahora()
    carpeta = config.get("BACKUP_DIR") or ""
    if not carpeta:
        return None
    with db:  # IMMEDIATE: si dos procesos revisan a la vez, solo uno se queda con la copia del día
        db.execute("BEGIN IMMEDIATE")
        g = configuracion.leer_todo(db)
        if not forzar and not _corresponde(g, carpeta, ahora):
            return None
        en_curso = _fecha(g.get("backup_en_curso"))
        if en_curso and ahora - en_curso < EN_CURSO_VENCE:
            return None
        configuracion.escribir(db, {"backup_en_curso": _iso(ahora)})

    destino = Path(carpeta)
    temporal = destino / TEMPORAL
    try:
        destino.mkdir(parents=True, exist_ok=True)
        fotos = backup.crear_respaldo(config["DATABASE"], config["UPLOAD_DIR"], temporal, ahora)
        final = destino / backup.nombre_de_archivo(ahora)
        os.replace(temporal, final)  # recién ahora existe como copia: nunca queda una a medias
    except (ErrorDeNegocio, OSError) as e:
        try:
            temporal.unlink(missing_ok=True)
        except OSError:  # p. ej. la "carpeta" es un archivo o el pendrive ya no está: no hay nada que limpiar
            pass
        configuracion.guardar(db, {"backup_en_curso": "", "backup_error_en": _iso(ahora), "backup_error_msg": str(e)})
        log.warning("Falló la copia automática: %s", e)
        return {"ok": False, "error": str(e)}

    try:
        backup.conservar_ultimos(carpeta, COPIAS_A_CONSERVAR)
    except OSError as e:  # la copia nueva ya está bien: que no se puedan borrar las viejas no la invalida
        log.warning("No se pudieron borrar copias viejas: %s", e)
    configuracion.guardar(db, {"backup_en_curso": "", "backup_ultimo_ok": _iso(ahora), "backup_ultima_carpeta": carpeta,
                               "backup_error_en": "", "backup_error_msg": ""})
    return {"ok": True, "archivo": final, "fotos": fotos}


# --------------------------------------------------------------------------- hilo
def ciclo(app) -> dict | None:
    """Una revisión: toma la configuración vigente de la base y hace la copia si toca."""
    conn = dbm.connect(app.config["DATABASE"])
    try:
        configuracion.aplicar(app.config, conn)
        return ejecutar(conn, app.config)
    finally:
        conn.close()


def iniciar_hilo(app, intervalo: int = INTERVALO_SEGUNDOS, espera_inicial: int = 20) -> threading.Thread | None:
    """Arranca (una sola vez por app) el hilo de fondo que revisa si toca la copia del día."""
    if app.extensions.get("backup_hilo"):
        return None

    def bucle():
        time.sleep(espera_inicial)
        while True:
            try:
                ciclo(app)
            except Exception:  # el hilo nunca se tiene que morir por un error de una revisión
                log.exception("Error en la revisión de la copia automática")
            time.sleep(intervalo)

    hilo = threading.Thread(target=bucle, name="copia-automatica", daemon=True)
    app.extensions["backup_hilo"] = hilo
    hilo.start()
    return hilo
