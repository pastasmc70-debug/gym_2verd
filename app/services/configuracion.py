"""Configuración guardada en la base, clave secreta automática y datos del asistente de primera vez.

Orden de prioridad de cada ajuste: lo guardado desde la pantalla «Configuración» (tabla `configuracion`),
después la variable de entorno GYM_* y por último el valor por defecto. Las variables de entorno
siguen funcionando como alternativa: quien ya las usa no tiene que cambiar nada.

El administrador y la clave secreta son la excepción: si vienen por variables de entorno, ésas mandan
(y no aparece el asistente). Si no, se usan los que dejó el asistente.
"""
import os
import re
import secrets
import string
import time
from pathlib import Path

from werkzeug.security import generate_password_hash

from .. import models, timeutils
from .errors import ErrorDeNegocio
from .validation import limpiar, validar_plan

CLAVE_MIN = 10
CLAVE_MAX = 128
NOMBRE_MAX = 60
USUARIO_RE = re.compile(r"^[A-Za-z0-9._-]{3,30}$")
PLANES_EN_ASISTENTE = 3

# clave guardada en la base -> (clave de app.config, tipo)
AJUSTES = {
    "gym_nombre": ("GYM_NOMBRE", "texto"),
    "modulo_tienda": ("MODULO_TIENDA", "bool"),
    "acceso_sin_pago": ("ACCESO_SIN_PAGO", "bool"),
    "permitir_reingreso": ("PERMITIR_REINGRESO", "bool"),
    "limitar_clases_semana": ("LIMITAR_CLASES_SEMANA", "bool"),
    "kiosco_sonido": ("KIOSCO_SONIDO", "bool"),
    "kiosco_teclado": ("KIOSCO_TECLADO_PANTALLA", "bool"),
    "kiosco_clave_hash": ("KIOSCO_CLAVE_HASH", "texto"),
    "horas_adentro": ("HORAS_ADENTRO", "entero"),
    "backup_carpeta": ("BACKUP_DIR", "texto"),
}
HORAS_ADENTRO_RANGO = (1, 12)
BOOLEANOS = [k for k, (_, tipo) in AJUSTES.items() if tipo == "bool"]


# --------------------------------------------------------------- clave secreta automática
def _clave_valida(texto: str) -> bool:
    return len(texto) == 64 and all(c in string.hexdigits for c in texto)


def clave_secreta(carpeta) -> str:
    """Devuelve la clave secreta de la carpeta de datos; la genera la primera vez (token_hex(32))."""
    carpeta = Path(carpeta)
    ruta = carpeta / "secret_key"
    for intento in range(10):
        try:
            texto = ruta.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            texto = ""
        if _clave_valida(texto):
            return texto
        carpeta.mkdir(parents=True, exist_ok=True)
        try:  # creación exclusiva: si dos procesos arrancan a la vez, gana uno solo
            fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if intento < 9 and not texto:
                time.sleep(0.1)  # otro proceso la está escribiendo en este instante
                continue
            ruta.unlink(missing_ok=True)  # existe pero está dañada: se genera una nueva
            continue
        nueva = secrets.token_hex(32)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(nueva)
        return nueva
    raise ErrorDeNegocio("No se pudo guardar la clave secreta en la carpeta de datos.")


# ------------------------------------------------------------------ lectura y escritura
def leer_todo(db) -> dict[str, str]:
    return {f["clave"]: f["valor"] for f in db.execute("SELECT clave, valor FROM configuracion")}


def escribir(db, valores: dict[str, str]) -> None:
    """Escribe sin abrir ni cerrar la transacción (la maneja quien llama)."""
    ahora = timeutils.ahora().isoformat(timespec="seconds")
    for clave, valor in valores.items():
        db.execute(
            "INSERT INTO configuracion (clave, valor, actualizada_en) VALUES (?, ?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, actualizada_en = excluded.actualizada_en",
            (clave, valor, ahora),
        )


def guardar(db, valores: dict[str, str]) -> None:
    with db:
        escribir(db, valores)


def aplicar(config, db) -> None:
    """Pasa lo guardado en la base a app.config. Se llama en cada pedido, así un cambio vale en todos los procesos."""
    guardado = leer_todo(db)
    for clave, (destino, tipo) in AJUSTES.items():
        if clave in guardado:
            if tipo == "bool":
                config[destino] = guardado[clave] == "1"
            elif tipo == "entero":
                try:
                    config[destino] = int(guardado[clave])
                except ValueError:
                    pass  # un valor dañado no tira abajo la app: queda el de la variable de entorno o el de fábrica
            else:
                config[destino] = guardado[clave]
    if not config.get("ADMIN_USER") and not config.get("ADMIN_PASSWORD_HASH"):
        if guardado.get("admin_usuario") and guardado.get("admin_clave_hash"):
            config["ADMIN_USER"] = guardado["admin_usuario"]
            config["ADMIN_PASSWORD_HASH"] = guardado["admin_clave_hash"]


def hay_administrador(config) -> bool:
    return bool(config.get("ADMIN_USER") and config.get("ADMIN_PASSWORD_HASH"))


# ----------------------------------------------------------------------------- validación
def validar_nombre(texto) -> tuple[str, str | None]:
    nombre = limpiar(texto)
    if not nombre:
        return nombre, "Ingresá el nombre del gimnasio."
    if len(nombre) > NOMBRE_MAX:
        return nombre, f"El nombre es demasiado largo (máximo {NOMBRE_MAX} caracteres)."
    return nombre, None


def validar_clave(clave, confirmacion, campo="clave") -> dict[str, str]:
    errores = {}
    if len(clave or "") < CLAVE_MIN:
        errores[campo] = f"La clave es muy corta: usá al menos {CLAVE_MIN} caracteres."
    elif len(clave) > CLAVE_MAX:
        errores[campo] = f"La clave es demasiado larga (máximo {CLAVE_MAX} caracteres)."
    elif clave != (confirmacion or ""):
        errores["confirmacion"] = "Las dos claves no coinciden."
    return errores


def validar_administrador(form, usuario_recepcion=None) -> tuple[dict, dict]:
    errores = {}
    usuario = limpiar(form.get("usuario"))
    if not USUARIO_RE.match(usuario):
        errores["usuario"] = "El usuario debe tener entre 3 y 30 caracteres: letras, números, punto, guion o guion bajo."
    elif usuario_recepcion and usuario.lower() == usuario_recepcion.lower():
        errores["usuario"] = "Ese usuario ya lo usa recepción: elegí otro."
    errores.update(validar_clave(form.get("clave"), form.get("confirmacion")))
    return {"usuario": usuario}, errores


def validar_planes(db, form) -> tuple[list[dict], dict]:
    """Hasta PLANES_EN_ASISTENTE planes (nombre, precio, duración). Las filas vacías se ignoran."""
    planes, errores, nombres = [], {}, {}
    for i in range(1, PLANES_EN_ASISTENTE + 1):
        nombre, precio, duracion = (limpiar(form.get(f"p{i}_{c}")) for c in ("nombre", "precio", "duracion"))
        if not (nombre or precio or duracion):
            continue
        datos, errs = validar_plan(db, {"nombre": nombre, "precio": precio, "duracion_dias": duracion, "ilimitado": "1"})
        if not errs.get("nombre") and datos["nombre"].lower() in nombres:
            errs["nombre"] = "Ya cargaste un plan con ese nombre."
        nombres.setdefault(datos["nombre"].lower(), i)
        for campo, mensaje in errs.items():
            errores[f"p{i}_{'duracion' if campo == 'duracion_dias' else campo}"] = mensaje
        if not errs:
            planes.append(datos)
    if not planes and not errores:
        errores["planes"] = "Cargá al menos un plan con su precio y duración."
    return planes, errores


def validar_ajustes(form, config) -> tuple[dict[str, str], dict]:
    """Valida la pantalla Configuración. Devuelve (lo que hay que guardar, errores)."""
    errores, valores = {}, {}
    nombre, error = validar_nombre(form.get("gym_nombre"))
    if error:
        errores["gym_nombre"] = error
    valores["gym_nombre"] = nombre
    for clave in BOOLEANOS:
        valores[clave] = "1" if form.get(clave) else "0"
    minimo, maximo = HORAS_ADENTRO_RANGO
    if "horas_adentro" not in form:  # un formulario que no trae el campo no lo cambia
        valores["horas_adentro"] = str(config.get("HORAS_ADENTRO", 2))
    else:
        texto = limpiar(form.get("horas_adentro"))
        valido = texto.isdigit() and minimo <= int(texto) <= maximo
        if not valido:
            errores["horas_adentro"] = f"Ingresá un número entero de horas entre {minimo} y {maximo}."
        valores["horas_adentro"] = str(int(texto)) if valido else texto
    nueva = form.get("kiosco_clave") or ""
    if nueva:
        errores_clave = validar_clave(nueva, form.get("kiosco_clave_confirmacion"), campo="kiosco_clave")
        if "confirmacion" in errores_clave:
            errores_clave = {"kiosco_clave_confirmacion": errores_clave["confirmacion"]}
        errores.update(errores_clave)
    return valores, errores


def hash_de(clave: str, metodo: str | None = None) -> str:
    return generate_password_hash(clave, method=metodo) if metodo else generate_password_hash(clave)


# ------------------------------------------------------------------------------ asistente
def completar_asistente(db, config, *, nombre, usuario, clave_hash, planes, tienda) -> None:
    """Guarda todo lo del asistente en una sola transacción. Si ya hay administrador, no hace nada y avisa."""
    with db:
        db.execute("BEGIN IMMEDIATE")
        if hay_administrador(config) or leer_todo(db).get("admin_usuario"):
            raise ErrorDeNegocio("Ya hay un administrador: el asistente de primera vez no se puede repetir.")
        escribir(db, {"gym_nombre": nombre, "modulo_tienda": "1" if tienda else "0",
                      "admin_usuario": usuario, "admin_clave_hash": clave_hash})
        for p in planes:
            models.crear_plan(db, dict(nombre=p["nombre"], precio_centavos=p["precio_centavos"],
                                       duracion_dias=p["duracion_dias"], clases_por_semana=None))
