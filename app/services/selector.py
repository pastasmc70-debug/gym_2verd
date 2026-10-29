"""Lista de socios para elegir con un clic (nuevo pago, asignar plan, ingreso, venta de tienda).

Orden por defecto ("prioridad"): primero los vencidos, después los que están por vencer y al final el resto;
dentro de cada grupo, alfabético. El otro orden es solo alfabético. Se pagina de a LIMITE para que siga rápida
con cientos de socios.
"""
from datetime import date, timedelta

from .. import models
from . import memberships
from .validation import limpiar, normalizar_dni

LIMITE = 50
ORDENES = ("prioridad", "alfabetico")
DESTINOS = ("pago", "membresia", "ingreso", "venta")


def _orden(valor) -> str:
    return valor if valor in ORDENES else "prioridad"


def listar(db, q="", orden="prioridad", pagina=1, hoy: date | None = None, dias_alerta: int = 7,
           limite: int = LIMITE) -> dict:
    """Devuelve {socios, total, pagina, hay_mas, orden, q}. Cada socio trae estado_membresia y dias_restantes."""
    from .. import timeutils
    hoy = hoy or timeutils.hoy()
    orden = _orden(orden)
    q = limpiar(q)
    pagina = max(1, int(pagina or 1))

    donde, params = "", []
    if q:
        condiciones, params = ["nombre LIKE ?"], [f"%{q}%"]
        solo_numeros = q.replace(".", "").replace(" ", "")
        if solo_numeros.isdigit():   # "Socio 003" busca por nombre; "30.123" o "0002" también por DNI
            condiciones.append("dni LIKE ?")
            params.append(f"%{normalizar_dni(q)}%")
        donde = " WHERE " + " OR ".join(condiciones)

    if orden == "prioridad":
        ordenar = ("CASE WHEN fecha_vencimiento IS NOT NULL AND fecha_vencimiento < ? THEN 0 "
                   "WHEN fecha_vencimiento IS NOT NULL AND fecha_vencimiento <= ? THEN 1 ELSE 2 END, "
                   "nombre COLLATE NOCASE, id")
        params_orden = [hoy.isoformat(), (hoy + timedelta(days=dias_alerta)).isoformat()]
    else:
        ordenar, params_orden = "nombre COLLATE NOCASE, id", []

    total = db.execute(f"SELECT COUNT(*) FROM vista_socios{donde}", params).fetchone()[0]
    filas = db.execute(
        f"SELECT * FROM vista_socios{donde} ORDER BY {ordenar} LIMIT ? OFFSET ?",
        params + params_orden + [limite, (pagina - 1) * limite],
    ).fetchall()
    socios = [memberships.enriquecer(f, hoy, dias_alerta) for f in filas]
    return {"socios": socios, "total": total, "pagina": pagina, "orden": orden, "q": q,
            "hay_mas": pagina * limite < total, "mostrados": min(total, (pagina - 1) * limite + len(socios))}
