"""Importación de socios desde un CSV, en dos pasos: análisis (vista previa) y confirmación.

El análisis no escribe nada. Devuelve las filas que se pueden importar y, por cada fila con
problemas, qué está mal y en qué línea del archivo. Al confirmar se vuelve a analizar el archivo
(la base pudo cambiar entre un paso y otro) y se importan solo las filas válidas.
"""
import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from .. import models, timeutils
from .errors import ErrorDeNegocio
from .validation import validar_socio

MAX_BYTES = 1024 * 1024
MAX_FILAS = 2000

# Nombre normalizado de la columna (sin tildes, minúsculas, sin espacios ni guiones) -> campo
SINONIMOS = {
    "nombre": "nombre", "nombreyapellido": "nombre", "apellidoynombre": "nombre", "socio": "nombre",
    "dni": "dni", "documento": "dni",
    "telefono": "telefono", "tel": "telefono", "celular": "telefono", "whatsapp": "telefono",
    "email": "email", "mail": "email", "correo": "email", "correoelectronico": "email",
    "fechaalta": "fecha_alta", "alta": "fecha_alta", "fechadealta": "fecha_alta", "fecha": "fecha_alta",
    "estado": "estado",
    "notas": "notas", "nota": "notas", "observaciones": "notas",
}
OBLIGATORIAS = ("nombre", "dni", "telefono")
CAMPOS = ("nombre", "dni", "telefono", "email", "fecha_alta", "estado", "notas")


@dataclass
class ErrorFila:
    linea: int
    nombre: str
    dni: str
    mensajes: list[str]


@dataclass
class Analisis:
    validas: list[dict] = field(default_factory=list)      # datos ya limpios, listos para crear_socio
    lineas_validas: list[int] = field(default_factory=list)
    errores: list[ErrorFila] = field(default_factory=list)
    problema_general: str | None = None                     # el archivo entero no se puede leer
    total_filas: int = 0

    @property
    def puede_confirmar(self) -> bool:
        return self.problema_general is None and bool(self.validas)


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sin_tildes.lower())


def _decodificar(contenido: bytes) -> str:
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return contenido.decode("latin-1")


def _delimitador(primera_linea: str) -> str:
    return max((";", ",", "\t"), key=primera_linea.count)


def _fecha_a_iso(texto: str) -> str:
    """Acepta dd/mm/aaaa, dd-mm-aaaa y aaaa-mm-dd. Si no la entiende, la devuelve igual (el validador la rechaza)."""
    texto = (texto or "").strip()
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", texto)
    if m:
        try:
            return date(int(m[3]), int(m[2]), int(m[1])).isoformat()
        except ValueError:
            return texto
    return texto


def analizar(db, contenido: bytes, hoy: date | None = None) -> Analisis:
    hoy = hoy or timeutils.hoy()
    resultado = Analisis()

    if not contenido.strip():
        resultado.problema_general = "El archivo está vacío."
        return resultado
    if len(contenido) > MAX_BYTES:
        resultado.problema_general = "El archivo es demasiado grande (máximo 1 MB)."
        return resultado

    texto = _decodificar(contenido)
    primera = texto.splitlines()[0] if texto.splitlines() else ""
    lector = csv.reader(io.StringIO(texto), delimiter=_delimitador(primera))
    try:
        encabezado = next(lector)
    except (StopIteration, csv.Error):
        resultado.problema_general = "No se pudo leer el archivo como CSV."
        return resultado

    columnas: dict[int, str] = {}
    for posicion, nombre in enumerate(encabezado):
        campo = SINONIMOS.get(_normalizar(nombre))
        if campo and campo not in columnas.values():
            columnas[posicion] = campo
    faltan = [c for c in OBLIGATORIAS if c not in columnas.values()]
    if faltan:
        resultado.problema_general = (
            "Al archivo le faltan columnas obligatorias: " + ", ".join(faltan) + ". "
            "La primera fila tiene que ser el encabezado, por ejemplo: nombre;dni;telefono;email;fecha_alta;estado;notas."
        )
        return resultado

    dnis_vistos: dict[str, int] = {}
    try:
        filas = list(lector)
    except csv.Error as e:
        resultado.problema_general = f"El archivo tiene un error de formato: {e}"
        return resultado

    for numero, fila in enumerate(filas, start=2):
        if not any(celda.strip() for celda in fila):
            continue  # línea en blanco
        resultado.total_filas += 1
        if resultado.total_filas > MAX_FILAS:
            resultado.problema_general = f"El archivo tiene más de {MAX_FILAS} filas. Dividilo en partes más chicas."
            resultado.validas, resultado.lineas_validas, resultado.errores = [], [], []
            return resultado

        form = {campo: (fila[pos].strip() if pos < len(fila) else "") for pos, campo in columnas.items()}
        form["fecha_alta"] = _fecha_a_iso(form.get("fecha_alta", ""))
        form["estado"] = form.get("estado", "").lower()
        datos, errores = validar_socio(db, form, hoy=hoy)

        mensajes = list(errores.values())
        dni = datos.get("dni", "")
        if dni and "dni" not in errores:
            if dni in dnis_vistos:
                mensajes.append(f"El DNI {dni} está repetido en el archivo (ya aparece en la línea {dnis_vistos[dni]}).")
            else:
                dnis_vistos[dni] = numero
        if mensajes:
            resultado.errores.append(ErrorFila(numero, form.get("nombre", ""), form.get("dni", ""), mensajes))
        else:
            datos["foto"] = None
            resultado.validas.append(datos)
            resultado.lineas_validas.append(numero)

    if resultado.total_filas == 0:
        resultado.problema_general = "El archivo tiene el encabezado pero ninguna fila con datos."
    return resultado


def registrar_importacion(db, usuario: str | None, importadas: int, omitidas: int) -> None:
    """Deja asentado quién importó, cuándo y cuántas filas (visible en la pantalla de importación)."""
    with db:
        db.execute("INSERT INTO importaciones (creada_en, usuario, importadas, omitidas) VALUES (?, ?, ?, ?)",
                   (timeutils.ahora().isoformat(timespec="seconds"), usuario, importadas, omitidas))


def ultimas_importaciones(db, limite: int = 10):
    return db.execute("SELECT * FROM importaciones ORDER BY id DESC LIMIT ?", (limite,)).fetchall()


def importar(db, analisis: Analisis) -> int:
    """Crea los socios válidos en una sola transacción. Devuelve cuántos se crearon."""
    if not analisis.puede_confirmar:
        raise ErrorDeNegocio("No hay filas válidas para importar.")
    with db:
        for datos in analisis.validas:
            models.crear_socio(db, datos)
    return len(analisis.validas)
