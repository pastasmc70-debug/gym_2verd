"""Cuentas de recepción guardadas en la base (el administrador sigue viniendo de las variables de entorno).

Reglas: las claves se guardan siempre con hash; los usuarios no se borran, se desactivan (así el nombre que
quedó en pagos, ventas e ingresos viejos sigue siendo único); una cuenta desactivada o con la clave cambiada
pierde la sesión abierta en el siguiente clic.
"""
import hashlib
import re

from werkzeug.security import check_password_hash, generate_password_hash

from .. import timeutils
from .errors import ErrorDeNegocio

CLAVE_MINIMA = 10
USUARIO_RE = re.compile(r"^[a-z0-9._-]{3,30}$")
# Para gastar el mismo tiempo cuando el usuario no existe y no delatar qué nombres hay.
_HASH_FALSO = generate_password_hash("no-es-la-clave-de-nadie")


def _ahora() -> str:
    return timeutils.ahora().isoformat(timespec="seconds")


def normalizar(usuario) -> str:
    return (usuario or "").strip().lower()


def obtener(db, usuario_id):
    return db.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()


def obtener_por_nombre(db, usuario):
    return db.execute("SELECT * FROM usuarios WHERE usuario = ?", (normalizar(usuario),)).fetchone()


def listar(db):
    return db.execute("SELECT * FROM usuarios ORDER BY activo DESC, usuario").fetchall()


def validar_clave(clave, confirmacion) -> str | None:
    if clave is None or len(clave) < CLAVE_MINIMA:
        return f"La clave tiene que tener al menos {CLAVE_MINIMA} caracteres."
    if clave != confirmacion:
        return "Las dos claves no coinciden."
    return None


def validar_nuevo(db, form, usuario_admin: str | None = None):
    """Devuelve (datos, errores) para el alta de una cuenta de recepción."""
    errores = {}
    usuario = normalizar(form.get("usuario"))
    if not USUARIO_RE.match(usuario):
        errores["usuario"] = "El usuario tiene entre 3 y 30 caracteres: letras sin tildes, números, punto, guion o guion bajo."
    elif usuario == normalizar(usuario_admin) or obtener_por_nombre(db, usuario):
        errores["usuario"] = "Ese nombre de usuario ya está en uso."
    error_clave = validar_clave(form.get("clave"), form.get("clave2"))
    if error_clave:
        errores["clave"] = error_clave
    return {"usuario": usuario, "clave": form.get("clave", "")}, errores


def crear(db, usuario: str, clave: str, creado_por: str | None = None, clave_hash: str | None = None) -> int:
    with db:
        cur = db.execute(
            "INSERT INTO usuarios (usuario, clave_hash, rol, creado_en, creado_por) VALUES (?, ?, 'recepcion', ?, ?)",
            (normalizar(usuario), clave_hash or generate_password_hash(clave), _ahora(), creado_por))
    return cur.lastrowid


def cambiar_clave(db, usuario_id: int, clave: str, confirmacion: str) -> None:
    if obtener(db, usuario_id) is None:
        raise ErrorDeNegocio("No encontramos ese usuario.", "usuario")
    error = validar_clave(clave, confirmacion)
    if error:
        raise ErrorDeNegocio(error, "clave")
    with db:
        db.execute("UPDATE usuarios SET clave_hash = ? WHERE id = ?", (generate_password_hash(clave), usuario_id))


def cambiar_activo(db, usuario_id: int, activo: bool) -> None:
    if obtener(db, usuario_id) is None:
        raise ErrorDeNegocio("No encontramos ese usuario.", "usuario")
    with db:
        db.execute("UPDATE usuarios SET activo = ?, desactivado_en = ? WHERE id = ?",
                   (1 if activo else 0, None if activo else _ahora(), usuario_id))


def sello(fila) -> str:
    """Huella de la clave actual: si la clave cambia, las sesiones abiertas con la anterior dejan de valer."""
    return hashlib.sha256(fila["clave_hash"].encode()).hexdigest()[:16]


def autenticar(db, usuario, clave):
    """Devuelve la fila del usuario activo si la clave es correcta; si no, None."""
    fila = obtener_por_nombre(db, usuario)
    correcta = check_password_hash(fila["clave_hash"] if fila else _HASH_FALSO, clave or "")
    return fila if fila and correcta and fila["activo"] else None


def sesion_vigente(db, usuario, sello_guardado) -> bool:
    fila = obtener_por_nombre(db, usuario)
    return bool(fila and fila["activo"] and sello_guardado and sello(fila) == sello_guardado)


def importar_de_entorno(db, usuario, clave_hash) -> bool:
    """Compatibilidad: GYM_RECEPCION_USER / GYM_RECEPCION_PASSWORD_HASH pasan a ser una cuenta de la base.
    Solo se crea si ese nombre no existe todavía (si el administrador la desactivó, no se vuelve a crear)."""
    if not usuario or not clave_hash or obtener_por_nombre(db, usuario):
        return False
    crear(db, usuario, "", creado_por="variables de entorno", clave_hash=clave_hash)
    return True
