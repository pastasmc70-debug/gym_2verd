"""Caja diaria: lo cobrado en un día, separado por origen (cuotas, y tienda si el módulo está activo)."""
from datetime import date

from .. import models


def _por_metodo(montos: list[tuple[str, int]]) -> dict[str, int]:
    totales = {m: 0 for m in models.METODOS_PAGO}
    for metodo, monto in montos:
        totales[metodo] += monto
    return totales


def cuotas_del_dia(db, fecha: date) -> dict:
    """Pagos de cuotas con esa fecha. Los anulados se listan marcados pero NO suman en los totales."""
    pagos = models.pagos_del_dia(db, fecha)
    vigentes = [(p["metodo"], p["monto_centavos"]) for p in pagos if not p["anulado"]]
    return {
        "pagos": pagos,
        "total_centavos": sum(m for _, m in vigentes),
        "por_metodo": _por_metodo(vigentes),
        "cantidad": len(vigentes),
        "anulados": sum(1 for p in pagos if p["anulado"]),
    }
