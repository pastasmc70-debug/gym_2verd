"""Lógica del modo kiosco: ingreso por DNI con una respuesta que muestra lo mínimo.

PRIVACIDAD: lo que devuelve `resolver_ingreso` es lo único que llega a la pantalla del kiosco, y
solo contiene nombre, foto, estado de la membresía y días restantes. Nunca teléfono, email,
notas, pagos ni deudas: por eso los motivos de rechazo se traducen a mensajes neutros acá, en vez
de mostrar el texto de la regla (que, por ejemplo, menciona que no hay pagos).
"""
import time
from datetime import date, datetime

from .. import models, timeutils
from . import memberships
from .attendance import ReglasIngreso, registrar_ingreso
from .errors import ErrorDeNegocio
from .validation import normalizar_dni

USUARIO = "kiosco"

ETIQUETA_ESTADO = {
    models.VIGENTE: "Vigente",
    models.POR_VENCER: "Por vencer",
    models.VENCIDA: "Vencida",
    models.SIN_MEMBRESIA: "Sin plan",
}

# código de rechazo -> mensaje para la pantalla (neutro: sin datos de pagos ni de deudas)
MENSAJE_RECHAZO = {
    "vencida": "Tu cuota está vencida. Pasá por recepción.",
    "sin_pago": "Pasá por recepción.",
    "sin_plan": "Todavía no tenés un plan. Pasá por recepción.",
    "pausado": "Tu cuenta está pausada. Pasá por recepción.",
    "baja": "Pasá por recepción.",
    "reingreso": "Ya registraste tu ingreso hoy.",
    "limite_clases": "Ya usaste las clases de esta semana.",
}
MENSAJE_GENERICO = "No pudimos registrar tu ingreso. Pasá por recepción."


class Limitador:
    """Máximo de intentos en una ventana de tiempo, por clave (por ejemplo la IP). Vive en memoria."""

    def __init__(self, maximo: int, ventana: float = 60.0, reloj=time.monotonic):
        self.maximo, self.ventana, self.reloj = maximo, ventana, reloj
        self._intentos: dict[str, list[float]] = {}

    def intentar(self, clave: str) -> bool:
        """Registra un intento. Devuelve False (y no lo cuenta de nuevo) si ya se pasó del máximo."""
        ahora = self.reloj()
        recientes = [t for t in self._intentos.get(clave, []) if ahora - t < self.ventana]
        if len(recientes) >= self.maximo:
            self._intentos[clave] = recientes
            return False
        recientes.append(ahora)
        self._intentos[clave] = recientes
        return True


def _dias_texto(restantes: int | None) -> str:
    if restantes is None:
        return ""
    if restantes < 0:
        hace = -restantes
        return "Venció ayer" if hace == 1 else f"Venció hace {hace} días"
    if restantes == 0:
        return "Tu cuota vence hoy"
    return "Te queda 1 día" if restantes == 1 else f"Te quedan {restantes} días"


def _respuesta(ok: bool, mensaje: str, socio=None, estado: str = "", dias: str = "") -> dict:
    # Las ÚNICAS claves que salen hacia la pantalla.
    return {"ok": ok, "mensaje": mensaje, "nombre": socio["nombre"] if socio else "",
            "foto": socio["foto"] if socio else None, "estado": estado, "dias": dias}


def resolver_ingreso(db, texto_dni: str, reglas: ReglasIngreso, dias_alerta: int = 7,
                     hoy: date | None = None, ahora: datetime | None = None) -> dict:
    dni = normalizar_dni(texto_dni)
    if not 7 <= len(dni) <= 8 or dni != (texto_dni or "").strip():
        return _respuesta(False, "El DNI tiene que tener 7 u 8 números.")
    socio = models.obtener_socio_por_dni(db, dni)
    if socio is None:
        return _respuesta(False, "No encontramos ese DNI. Consultá en recepción.")

    try:
        r = registrar_ingreso(db, socio["id"], hoy=hoy, ahora=ahora, dias_alerta=dias_alerta,
                              reglas=reglas, usuario=USUARIO)
    except ErrorDeNegocio as e:
        hoy_ = hoy or (ahora.date() if ahora else timeutils.hoy())
        estado = memberships.estado_membresia(socio["fecha_vencimiento"], hoy_, dias_alerta)
        restantes = (memberships.dias_restantes(date.fromisoformat(socio["fecha_vencimiento"]), hoy_)
                     if socio["fecha_vencimiento"] else None)
        etiqueta = {"pausado": "Pausado", "baja": "De baja"}.get(e.codigo) or ETIQUETA_ESTADO[estado]
        dias = _dias_texto(restantes) if e.codigo not in ("pausado", "baja") else ""
        return _respuesta(False, MENSAJE_RECHAZO.get(e.codigo, MENSAJE_GENERICO), socio, etiqueta, dias)

    return _respuesta(True, "¡Bienvenido!", r["socio"], ETIQUETA_ESTADO[r["estado"]], _dias_texto(r["dias_restantes"]))
