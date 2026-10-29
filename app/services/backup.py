"""Copia de seguridad: la base de datos (copia consistente) y las fotos, en un único .zip.

No depende de Flask, así que lo usan tanto la pantalla de «Descargar copia de seguridad» como el
script backup.py que se puede programar.
"""
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from .. import timeutils
from .errors import ErrorDeNegocio

NOMBRE_DB_EN_ZIP = "gimnasio.db"
CARPETA_FOTOS_EN_ZIP = "fotos"
PREFIJO = "copia-seguridad"

LEEME = """Copia de seguridad del sistema del gimnasio
Generada el {fecha} (hora de Buenos Aires).

Contenido:
  gimnasio.db   base de datos completa (socios, planes, pagos, asistencias, etc.)
  fotos/        fotos de los socios

Cómo restaurarla:
  1. Cerrá el sistema.
  2. Reemplazá la base de datos actual (por defecto instance/gimnasio.db) por gimnasio.db de este zip.
  3. Reemplazá la carpeta de fotos (por defecto instance/fotos) por la carpeta fotos/ de este zip.
  4. Volvé a abrir el sistema.
"""


def nombre_de_archivo(ahora: datetime | None = None) -> str:
    ahora = ahora or timeutils.ahora()
    return f"{PREFIJO}_{ahora.strftime('%Y-%m-%d_%H%M%S')}.zip"


def _copia_consistente(ruta_db: str, destino: str) -> None:
    """Usa la API de backup de SQLite: la copia es consistente aunque el sistema esté en uso."""
    origen = sqlite3.connect(f"file:{ruta_db}?mode=ro", uri=True)
    try:
        copia = sqlite3.connect(destino)
        try:
            origen.backup(copia)
            resultado = copia.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            copia.close()
    finally:
        origen.close()
    if resultado != "ok":
        raise ErrorDeNegocio("La copia de la base de datos no pasó la verificación de integridad. No se generó el respaldo.")


def crear_respaldo(ruta_db: str, carpeta_fotos: str, destino, ahora: datetime | None = None) -> int:
    """Escribe el .zip en `destino` (ruta o archivo abierto en binario). Devuelve la cantidad de fotos incluidas."""
    ahora = ahora or timeutils.ahora()
    if not Path(ruta_db).is_file():
        raise ErrorDeNegocio(f"No encontramos la base de datos en {ruta_db}.")
    fotos = 0
    with tempfile.TemporaryDirectory() as tmp:
        copia = str(Path(tmp) / NOMBRE_DB_EN_ZIP)
        _copia_consistente(ruta_db, copia)
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copia, NOMBRE_DB_EN_ZIP)
            carpeta = Path(carpeta_fotos)
            if carpeta.is_dir():
                for archivo in sorted(carpeta.iterdir()):
                    if archivo.is_file() and not archivo.is_symlink():
                        z.write(archivo, f"{CARPETA_FOTOS_EN_ZIP}/{archivo.name}")
                        fotos += 1
            z.writestr("LEEME.txt", LEEME.format(fecha=ahora.strftime("%d/%m/%Y %H:%M")))
    return fotos


def conservar_ultimos(carpeta: str, cantidad: int) -> list[Path]:
    """Borra los respaldos más viejos de la carpeta y deja los últimos `cantidad`. Devuelve los borrados."""
    if cantidad < 1:
        return []
    archivos = sorted(Path(carpeta).glob(f"{PREFIJO}_*.zip"))
    sobrantes = archivos[:-cantidad] if len(archivos) > cantidad else []
    for archivo in sobrantes:
        archivo.unlink(missing_ok=True)
    return sobrantes
