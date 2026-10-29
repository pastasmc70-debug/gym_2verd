"""Fotos de socios: validación del archivo y guardado con nombre aleatorio."""
import secrets
from pathlib import Path

from .errors import ErrorDeNegocio


def _extension_por_contenido(cabecera: bytes) -> str | None:
    if cabecera.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if cabecera.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return ".webp"
    return None


def guardar_foto(archivo, carpeta: str) -> str | None:
    """Guarda la foto subida y devuelve el nombre de archivo. None si no se subió nada."""
    if archivo is None or not archivo.filename:
        return None
    contenido = archivo.read()
    if not contenido:
        return None
    extension = _extension_por_contenido(contenido[:16])
    if extension is None:
        raise ErrorDeNegocio("La foto tiene que ser JPG, PNG o WEBP.")
    nombre = secrets.token_hex(16) + extension
    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / nombre).write_bytes(contenido)
    return nombre


def borrar_foto(nombre: str | None, carpeta: str) -> None:
    if not nombre:
        return
    ruta = Path(carpeta) / Path(nombre).name  # .name evita salirse de la carpeta
    ruta.unlink(missing_ok=True)
