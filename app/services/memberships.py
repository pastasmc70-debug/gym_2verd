"""Lógica de membresías: vencimientos y estados.

Regla de vencimiento: una membresía que arranca el día X y dura N días vence el día X + N.
El socio puede entrar hasta ese día inclusive; recién al día siguiente figura como vencida.
"""
from datetime import date, timedelta

from .. import models, timeutils
from .errors import ErrorDeNegocio


def calcular_vencimiento(fecha_inicio: date, duracion_dias: int) -> date:
    return fecha_inicio + timedelta(days=duracion_dias)


def dias_restantes(vencimiento: date, hoy: date) -> int:
    """Negativo si ya venció."""
    return (vencimiento - hoy).days


def estado_membresia(vencimiento: date | str | None, hoy: date, dias_alerta: int = 7) -> str:
    if vencimiento is None:
        return models.SIN_MEMBRESIA
    if isinstance(vencimiento, str):
        vencimiento = date.fromisoformat(vencimiento)
    restantes = dias_restantes(vencimiento, hoy)
    if restantes < 0:
        return models.VENCIDA
    if restantes <= dias_alerta:
        return models.POR_VENCER
    return models.VIGENTE


def enriquecer(fila, hoy: date, dias_alerta: int = 7) -> dict:
    """Convierte una fila de vista_socios en dict con el estado de la membresía calculado."""
    socio = dict(fila)
    venc = socio.get("fecha_vencimiento")
    socio["estado_membresia"] = estado_membresia(venc, hoy, dias_alerta)
    socio["dias_restantes"] = dias_restantes(date.fromisoformat(venc), hoy) if venc else None
    return socio


def dias_vigentes_a_acumular(db, socio_id: int, fecha_inicio: date) -> int:
    """Días que le quedan al socio en su membresía actual a partir de `fecha_inicio` (0 si no le quedan)."""
    actual = models.membresia_actual(db, socio_id)
    if actual is None:
        return 0
    return max(0, (date.fromisoformat(actual["fecha_vencimiento"]) - fecha_inicio).days)


def asignar_plan(db, socio_id: int, plan_id: int, fecha_inicio: date, acumular: bool = False,
                 cargada_por: str | None = None) -> dict:
    """Crea una membresía nueva para el socio, con el vencimiento calculado a partir del plan.

    Si el socio todavía tiene días vigentes y `acumular` es True, esos días se suman a la nueva
    membresía; si no, la nueva reemplaza a la anterior y los días restantes se pierden.
    """
    socio = models.obtener_socio(db, socio_id)
    if socio is None:
        raise ErrorDeNegocio("No encontramos al socio.", "socio")
    if socio["estado"] == "baja":
        raise ErrorDeNegocio("El socio está dado de baja. Reactivalo antes de asignarle un plan.", "baja")
    plan = models.obtener_plan(db, plan_id)
    if plan is None:
        raise ErrorDeNegocio("Elegí un plan válido.", "plan")
    if not plan["activo"]:
        raise ErrorDeNegocio(f"El plan «{plan['nombre']}» está desactivado. Elegí otro o activalo desde Planes.", "plan_inactivo")

    extra = dias_vigentes_a_acumular(db, socio_id, fecha_inicio) if acumular else 0
    vencimiento = calcular_vencimiento(fecha_inicio, plan["duracion_dias"] + extra)
    with db:
        cur = db.execute(
            """INSERT INTO membresias (socio_id, plan_id, fecha_inicio, fecha_vencimiento, creada_en,
                                       duracion_dias, precio_centavos, dias_extra, cargada_por)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (socio_id, plan_id, fecha_inicio.isoformat(), vencimiento.isoformat(),
             timeutils.ahora().isoformat(timespec="seconds"), plan["duracion_dias"],
             plan["precio_centavos"], extra, cargada_por),
        )
    return {"membresia_id": cur.lastrowid, "fecha_vencimiento": vencimiento, "plan": plan, "dias_acumulados": extra}
