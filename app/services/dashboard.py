"""Datos del panel de inicio y de la lista de alertas."""
from datetime import date, timedelta

from .. import models, timeutils
from . import memberships


def resumen(db, hoy: date | None = None, dias_alerta: int = 7) -> dict:
    hoy = hoy or timeutils.hoy()
    desde = timeutils.primer_dia_mes(hoy)
    hasta = timeutils.primer_dia_mes_siguiente(hoy)
    limite = hoy + timedelta(days=dias_alerta)

    def contar(sql, *params):
        return db.execute(sql, params).fetchone()[0]

    ingresos = contar(
        "SELECT COALESCE(SUM(monto_centavos), 0) FROM pagos WHERE anulado = 0 AND fecha >= ? AND fecha < ?",
        desde.isoformat(), hasta.isoformat(),
    )
    return {
        "socios_activos": contar("SELECT COUNT(*) FROM socios WHERE estado = 'activo'"),
        "ingresos_mes_centavos": ingresos,
        "por_vencer": contar(
            """SELECT COUNT(*) FROM vista_socios WHERE estado = 'activo'
               AND fecha_vencimiento >= ? AND fecha_vencimiento <= ?""",
            hoy.isoformat(), limite.isoformat(),
        ),
        "vencidos": contar(
            "SELECT COUNT(*) FROM vista_socios WHERE estado = 'activo' AND fecha_vencimiento < ?",
            hoy.isoformat(),
        ),
        "asistencias_hoy": contar("SELECT COUNT(DISTINCT socio_id) FROM asistencias WHERE fecha = ?", hoy.isoformat()),
    }


def adentro_ahora(db, ahora, horas: int) -> list[dict]:
    """Estimación de quiénes siguen en el gimnasio: socios con un ingreso en las últimas `horas` horas (inclusive).

    No se registra la salida, por eso es aproximado. Cada socio cuenta una sola vez (con su último ingreso) y
    se cruza la medianoche sin problema porque se compara fecha y hora juntas. Sin datos privados: solo nombre y hora.
    """
    formato = "%Y-%m-%d %H:%M:%S"
    hasta = ahora.replace(tzinfo=None)
    desde = hasta - timedelta(hours=horas)
    filas = db.execute(
        """SELECT s.id AS socio_id, s.nombre, MAX(a.fecha || ' ' || a.hora) AS ingreso
           FROM asistencias a JOIN socios s ON s.id = a.socio_id
           WHERE (a.fecha || ' ' || a.hora) >= ? AND (a.fecha || ' ' || a.hora) <= ?
           GROUP BY s.id ORDER BY ingreso DESC, s.nombre""",
        (desde.strftime(formato), hasta.strftime(formato)),
    ).fetchall()
    return [{"socio_id": f["socio_id"], "nombre": f["nombre"], "hora": f["ingreso"][11:16], "ingreso": f["ingreso"]} for f in filas]


def socios_con_alerta(db, hoy: date | None = None, dias_alerta: int = 7) -> list[dict]:
    """Socios activos con la cuota vencida o por vencer, ordenados por urgencia."""
    hoy = hoy or timeutils.hoy()
    filas = models.socios_activos_con_vencimiento_hasta(db, hoy + timedelta(days=dias_alerta))
    return [memberships.enriquecer(f, hoy, dias_alerta) for f in filas]
