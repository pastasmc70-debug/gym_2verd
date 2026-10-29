"""Lógica de asistencia: búsqueda de socios y registro de ingresos."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .. import models, timeutils
from ..timeutils import fecha_ar
from .errors import ErrorDeNegocio
from .memberships import dias_restantes, estado_membresia
from .payments import saldo_del_socio, tiene_pago_vigente
from .validation import limpiar, normalizar_dni


def buscar_socios(db, texto: str, limite: int = 8):
    """Busca por DNI (exacto o parcial) o por parte del nombre."""
    texto = limpiar(texto)
    if not texto:
        return []
    dni = normalizar_dni(texto)
    if len(dni) >= 7 and dni == re_digitos(texto):
        exacto = models.obtener_socio_por_dni(db, dni)
        if exacto:
            return [exacto]
    like = f"%{texto}%"
    like_dni = f"%{dni}%" if dni else like
    return db.execute(
        """SELECT * FROM vista_socios WHERE nombre LIKE ? OR dni LIKE ?
           ORDER BY nombre COLLATE NOCASE LIMIT ?""",
        (like, like_dni, limite),
    ).fetchall()


def re_digitos(texto: str) -> str:
    """Los dígitos de un texto que solo contiene números, puntos o espacios; si no, ''."""
    limpio = texto.replace(".", "").replace(" ", "")
    return limpio if limpio.isdigit() else ""


@dataclass(frozen=True)
class ReglasIngreso:
    """Reglas configurables del ingreso (se cargan desde las variables de entorno, ver config.py)."""
    acceso_sin_pago: bool = False       # GYM_ACCESO_SIN_PAGO
    permitir_reingreso: bool = False    # GYM_PERMITIR_REINGRESO
    limitar_clases: bool = True         # GYM_LIMITAR_CLASES_SEMANA

    @classmethod
    def desde_config(cls, config) -> "ReglasIngreso":
        return cls(config["ACCESO_SIN_PAGO"], config["PERMITIR_REINGRESO"], config["LIMITAR_CLASES_SEMANA"])


def inicio_de_semana(hoy: date) -> date:
    """La semana de clases va de lunes a domingo."""
    return hoy - timedelta(days=hoy.weekday())


def clases_usadas_en_la_semana(db, socio_id: int, hoy: date) -> int:
    """Días distintos con ingreso en la semana (lunes a domingo) de `hoy`. Un reingreso el mismo día no gasta otra clase."""
    lunes = inicio_de_semana(hoy)
    return db.execute(
        "SELECT COUNT(DISTINCT fecha) FROM asistencias WHERE socio_id = ? AND fecha >= ? AND fecha <= ?",
        (socio_id, lunes.isoformat(), (lunes + timedelta(days=6)).isoformat()),
    ).fetchone()[0]


def registrar_ingreso(db, socio_id: int, hoy: date | None = None, ahora: datetime | None = None,
                      dias_alerta: int = 7, reglas: ReglasIngreso | None = None,
                      usuario: str | None = None) -> dict:
    """Registra el ingreso o lanza ErrorDeNegocio (con `codigo`) explicando el rechazo."""
    reglas = reglas or ReglasIngreso()
    ahora = ahora or timeutils.ahora()
    hoy = hoy or ahora.date()

    socio = models.obtener_socio(db, socio_id)
    if socio is None:
        raise ErrorDeNegocio("No encontramos al socio.", "socio")
    nombre = socio["nombre"]

    if socio["estado"] == "baja":
        raise ErrorDeNegocio(f"{nombre} está dado de baja. No puede ingresar.", "baja", socio=socio)
    if socio["estado"] == "pausado":
        raise ErrorDeNegocio(f"La cuenta de {nombre} está pausada. Reactivala para permitir el ingreso.", "pausado", socio=socio)

    vencimiento = socio["fecha_vencimiento"]
    if vencimiento is None:
        raise ErrorDeNegocio(f"{nombre} no tiene un plan asignado. Asignale uno y registrá el pago.", "sin_plan", socio=socio)

    estado = estado_membresia(vencimiento, hoy, dias_alerta)
    restantes = dias_restantes(date.fromisoformat(vencimiento), hoy)
    if estado == models.VENCIDA:
        hace = -restantes
        cuando = "ayer" if hace == 1 else f"hace {hace} días"
        raise ErrorDeNegocio(
            f"Ingreso rechazado: la cuota de {nombre} venció el {fecha_ar(vencimiento)} ({cuando}). "
            "Registrá un pago para renovarla.",
            "vencida", socio=socio, dias_restantes=restantes,
        )

    # Un plan asignado sin ningún pago no habilita el ingreso (salvo que se configure lo contrario).
    # Los días que vienen acumulados de una membresía anterior ya estaban pagos.
    if (not reglas.acceso_sin_pago and not tiene_pago_vigente(db, socio["membresia_id"])
            and not socio["dias_extra"]):
        raise ErrorDeNegocio(
            f"Ingreso rechazado: {nombre} tiene un plan asignado pero todavía no registra ningún pago. "
            "Registrá el pago para habilitar el ingreso.",
            "sin_pago", socio=socio,
        )

    previo = db.execute(
        "SELECT hora FROM asistencias WHERE socio_id = ? AND fecha = ? ORDER BY hora LIMIT 1",
        (socio_id, hoy.isoformat()),
    ).fetchone()
    if previo and not reglas.permitir_reingreso:
        raise ErrorDeNegocio(f"{nombre} ya registró su ingreso hoy a las {previo['hora'][:5]}.", "reingreso", socio=socio)

    # Límite de clases por semana del plan (el reingreso del mismo día no gasta otra clase).
    aviso_clases = None
    limite = db.execute("SELECT clases_por_semana FROM planes WHERE id = ?", (socio["plan_id"],)).fetchone()[0]
    if reglas.limitar_clases and limite is not None:
        usadas = clases_usadas_en_la_semana(db, socio_id, hoy)
        if previo is None:
            if usadas >= limite:
                raise ErrorDeNegocio(
                    f"Ingreso rechazado: {nombre} ya usó las {limite} clases por semana de su plan "
                    f"({socio['plan_nombre']}). La semana va de lunes a domingo.",
                    "limite_clases", socio=socio, limite=limite, usadas=usadas,
                )
            usadas += 1
        if previo is None:
            aviso_clases = (f"Esta fue su última clase de la semana ({usadas} de {limite})."
                            if usadas == limite else f"Clase {usadas} de {limite} de la semana.")

    with db:
        db.execute(
            "INSERT INTO asistencias (socio_id, fecha, hora, registrado_por) VALUES (?, ?, ?, ?)",
            (socio_id, hoy.isoformat(), ahora.strftime("%H:%M:%S"), usuario),
        )

    aviso = None
    if estado == models.POR_VENCER:
        aviso = (f"Su cuota vence hoy." if restantes == 0
                 else f"Su cuota vence en {restantes} día{'s' if restantes != 1 else ''} ({fecha_ar(vencimiento)}).")
    return {"socio": socio, "estado": estado, "dias_restantes": restantes, "aviso": aviso,
            "aviso_clases": aviso_clases, "reingreso": previo is not None}


def tarjeta_ingreso(db, socio_id: int, hoy: date | None = None, dias_alerta: int = 7) -> dict | None:
    """Datos de la tarjeta que ve recepción después de registrar un ingreso: foto, nombre, plan,
    estado, días restantes y saldo pendiente. Se lee de la base al mostrarla, así no queda desactualizada."""
    socio = models.obtener_socio(db, socio_id)
    if socio is None:
        return None
    hoy = hoy or timeutils.hoy()
    vencimiento = socio["fecha_vencimiento"]
    estado = estado_membresia(vencimiento, hoy, dias_alerta)
    return {
        "id": socio["id"], "nombre": socio["nombre"], "dni": socio["dni"], "foto": socio["foto"],
        "plan_nombre": socio["plan_nombre"], "estado": estado, "vencimiento": vencimiento,
        "dias_restantes": dias_restantes(date.fromisoformat(vencimiento), hoy) if vencimiento else None,
        "saldo_centavos": saldo_del_socio(db, socio_id),
    }
