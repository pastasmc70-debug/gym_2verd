"""Links de WhatsApp (wa.me) con mensaje prellenado."""
import re
from urllib.parse import quote

from .. import models
from ..timeutils import fecha_ar


def normalizar_telefono_ar(telefono: str) -> str:
    """Devuelve el número en el formato que pide wa.me para Argentina: 549 + área + número.

    Acepta cosas como '+54 9 11 1234-5678', '011 15 1234-5678', '(0221) 15-456789' o '1112345678'.
    """
    d = re.sub(r"\D", "", telefono or "")
    if d.startswith("549"):
        return d
    if d.startswith("54"):
        return "549" + d[2:]
    d = d.lstrip("0")
    if len(d) == 12:  # área + '15' + número: se saca el 15
        for i in (2, 3, 4):
            if d[i:i + 2] == "15":
                d = d[:i] + d[i + 2:]
                break
    return "549" + d


def mensaje_cobranza(socio: dict, gimnasio: str) -> str:
    primer_nombre = socio["nombre"].split()[0]
    venc = fecha_ar(socio["fecha_vencimiento"])
    if socio["estado_membresia"] == models.VENCIDA:
        situacion = f"tu cuota venció el {venc}"
    elif socio["dias_restantes"] == 0:
        situacion = "tu cuota vence hoy"
    else:
        situacion = f"tu cuota vence el {venc}"
    return (f"Hola {primer_nombre}, te escribimos de {gimnasio}. Te recordamos que {situacion}. "
            "¿Querés renovarla? ¡Te esperamos!")


def link_whatsapp(socio: dict, gimnasio: str) -> str:
    numero = normalizar_telefono_ar(socio["telefono"])
    return f"https://wa.me/{numero}?text={quote(mensaje_cobranza(socio, gimnasio))}"
