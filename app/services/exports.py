"""Exportación a CSV pensada para abrirse en Excel en Argentina (separador ';', UTF-8 con BOM)."""
import csv
import io
import re

from .. import models, timeutils
from ..timeutils import fecha_ar
from . import memberships

_TELEFONO_CON_MAS = re.compile(r"^\+[\d\s\-()]+$")


def _seguro(valor) -> str:
    """Evita 'inyección de fórmulas': Excel ejecuta celdas que empiezan con = + - @."""
    texto = "" if valor is None else str(valor)
    if texto and texto[0] in "=+-@\t\r" and not _TELEFONO_CON_MAS.match(texto):
        return "'" + texto
    return texto


def _monto(centavos: int) -> str:
    return f"{centavos // 100}.{centavos % 100:02d}".replace(".", ",")


def _a_csv(encabezados, filas) -> str:
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(encabezados)
    escritor.writerows(filas)
    return "﻿" + salida.getvalue()


def socios_csv(db, hoy=None, dias_alerta: int = 7) -> str:
    hoy = hoy or timeutils.hoy()
    filas = []
    for fila in models.todos_los_socios(db):
        s = memberships.enriquecer(fila, hoy, dias_alerta)
        filas.append([
            s["id"], _seguro(s["nombre"]), s["dni"], _seguro(s["telefono"]), _seguro(s["email"]),
            fecha_ar(s["fecha_alta"]), s["estado"], _seguro(s["plan_nombre"]),
            fecha_ar(s["fecha_vencimiento"]) if s["fecha_vencimiento"] else "",
            s["estado_membresia"], _seguro(s["notas"]),
        ])
    return _a_csv(
        ["ID", "Nombre", "DNI", "Teléfono", "Email", "Fecha de alta", "Estado", "Plan actual",
         "Vencimiento", "Estado de la membresía", "Notas"],
        filas,
    )


def pagos_csv(db) -> str:
    """Todos los pagos. Los anulados aparecen marcados y su «Monto que cuenta» es 0, así que
    sumar esa columna da la plata realmente cobrada."""
    filas = []
    for p in models.todos_los_pagos(db):
        anulado = bool(p["anulado"])
        filas.append([
            p["id"], fecha_ar(p["fecha"]), _seguro(p["socio_nombre"]), p["socio_dni"],
            _monto(p["monto_centavos"]), p["metodo"], _seguro(p["plan_nombre"]),
            "" if anulado else fecha_ar(p["vencimiento_nuevo"]), _seguro(p["nota"]),
            "ANULADO" if anulado else "Vigente",
            "Sí" if p["es_parcial"] and not anulado else "No",
            _monto(0 if anulado else p["monto_centavos"]),
            _seguro(p["cargado_por"]),
            fecha_ar(p["anulado_en"][:10]) if anulado else "",
            _seguro(p["anulado_por"]) if anulado else "",
            _seguro(p["anulado_motivo"]) if anulado else "",
        ])
    return _a_csv(
        ["ID", "Fecha", "Socio", "DNI", "Monto (ARS)", "Método", "Plan", "Cubre hasta", "Nota",
         "Estado", "Pago parcial", "Monto que cuenta (ARS)", "Cargado por", "Anulado el", "Anulado por",
         "Motivo de anulación"],
        filas,
    )
