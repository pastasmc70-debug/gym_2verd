"""Validación de formularios. Cada validador devuelve (datos_limpios, errores)."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .. import models, timeutils
from .payments import periodos_anuales

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MONTO_MAXIMO_CENTAVOS = 100_000_000 * 100  # 100 millones de pesos: tope de cordura


def limpiar(valor) -> str:
    return (valor or "").strip()


def normalizar_dni(texto) -> str:
    """Deja solo los dígitos: '30.123.456' -> '30123456'."""
    return re.sub(r"\D", "", texto or "")


def parse_monto(texto) -> int:
    """Convierte '15.000,50', '15000.5' o '$ 15000' en centavos. Lanza ValueError si no se entiende."""
    s = limpiar(texto).replace("$", "").replace(" ", "")
    if not s:
        raise ValueError("vacío")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")  # '15.000' es quince mil en Argentina
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):  # nada de notación científica, NaN ni símbolos raros
        raise ValueError("no es un número")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("no es un número") from None
    if d != d.quantize(Decimal("0.01")):
        raise ValueError("demasiados decimales")
    return int(d * 100)


def _entero(texto, minimo, maximo):
    try:
        n = int(limpiar(texto))
    except ValueError:
        return None
    return n if minimo <= n <= maximo else None


# ----------------------------------------------------------------- socios
def validar_socio(db, form, socio_id=None, hoy: date | None = None):
    hoy = hoy or timeutils.hoy()
    errores, d = {}, {}

    d["nombre"] = limpiar(form.get("nombre"))
    if not d["nombre"]:
        errores["nombre"] = "Ingresá el nombre y apellido."
    elif len(d["nombre"]) > 100:
        errores["nombre"] = "El nombre es demasiado largo (máximo 100 caracteres)."

    d["dni"] = normalizar_dni(form.get("dni"))
    if not limpiar(form.get("dni")):
        errores["dni"] = "Ingresá el DNI."
    elif not 7 <= len(d["dni"]) <= 8:
        errores["dni"] = "El DNI debe tener 7 u 8 números."
    else:
        otro = models.obtener_socio_por_dni(db, d["dni"])
        if otro and otro["id"] != socio_id:
            errores["dni"] = f"Ya existe un socio con ese DNI ({otro['nombre']})."

    d["telefono"] = limpiar(form.get("telefono"))
    digitos = re.sub(r"\D", "", d["telefono"])
    if not d["telefono"]:
        errores["telefono"] = "Ingresá un teléfono de contacto."
    elif not 8 <= len(digitos) <= 15 or not re.fullmatch(r"[\d\s+\-()]+", d["telefono"]):
        errores["telefono"] = "El teléfono no parece válido. Usá solo números, espacios, + y guiones."

    d["email"] = limpiar(form.get("email")).lower() or None
    if d["email"] and (len(d["email"]) > 120 or not EMAIL_RE.match(d["email"])):
        errores["email"] = "El email no parece válido."

    texto_fecha = limpiar(form.get("fecha_alta"))
    if not texto_fecha:
        d["fecha_alta"] = hoy.isoformat()
    elif timeutils.parse_fecha(texto_fecha) is None:
        errores["fecha_alta"] = "La fecha de alta no es válida."
        d["fecha_alta"] = texto_fecha
    else:
        d["fecha_alta"] = texto_fecha

    d["estado"] = limpiar(form.get("estado")) or "activo"
    if d["estado"] not in models.ESTADOS_SOCIO:
        errores["estado"] = "Elegí un estado válido: activo, pausado o baja."

    d["notas"] = limpiar(form.get("notas")) or None
    if d["notas"] and len(d["notas"]) > 1000:
        errores["notas"] = "Las notas son demasiado largas (máximo 1000 caracteres)."

    return d, errores


# ------------------------------------------------------------------ planes
def validar_plan(db, form, plan_id=None):
    errores, d = {}, {}

    d["nombre"] = limpiar(form.get("nombre"))
    if not d["nombre"]:
        errores["nombre"] = "Ingresá el nombre del plan."
    elif len(d["nombre"]) > 60:
        errores["nombre"] = "El nombre del plan es demasiado largo (máximo 60 caracteres)."
    else:
        otro = db.execute("SELECT id FROM planes WHERE nombre = ? COLLATE NOCASE", (d["nombre"],)).fetchone()
        if otro and otro["id"] != plan_id:
            errores["nombre"] = "Ya existe un plan con ese nombre."

    d["precio_centavos"] = None
    try:
        centavos = parse_monto(form.get("precio"))
        if centavos <= 0:
            errores["precio"] = "El precio tiene que ser mayor a cero."
        elif centavos > MONTO_MAXIMO_CENTAVOS:
            errores["precio"] = "El precio es demasiado alto."
        else:
            d["precio_centavos"] = centavos
    except ValueError:
        errores["precio"] = "Ingresá un precio válido, por ejemplo 25000 o 25.000,50."

    d["duracion_dias"] = _entero(form.get("duracion_dias"), 1, 3650)
    if d["duracion_dias"] is None:
        errores["duracion_dias"] = "La duración tiene que ser un número de días entre 1 y 3650."

    if form.get("ilimitado"):
        d["clases_por_semana"] = None
    else:
        d["clases_por_semana"] = _entero(form.get("clases_por_semana"), 1, 14)
        if d["clases_por_semana"] is None:
            errores["clases_por_semana"] = "Ingresá las clases por semana (1 a 14) o marcá «Ilimitado»."

    _validar_descuento_anual(form, d, errores)
    return d, errores


def _validar_descuento_anual(form, d, errores):
    """Descuento opcional por pago anual: sin descuento, un porcentaje (1 a 99) o un monto fijo."""
    tipo = limpiar(form.get("descuento_tipo"))
    d["descuento_anual_tipo"], d["descuento_anual_valor"] = None, None
    if tipo not in ("", "porcentaje", "monto"):
        errores["descuento_tipo"] = "Elegí si el descuento es un porcentaje, un monto fijo o ninguno."
        return
    if not tipo:
        return
    texto = form.get("descuento_valor")
    if tipo == "porcentaje":
        porcentaje = _entero(texto, 1, 99)
        if porcentaje is None:
            errores["descuento_valor"] = "El porcentaje tiene que ser un número entero entre 1 y 99."
        else:
            d["descuento_anual_tipo"], d["descuento_anual_valor"] = tipo, porcentaje
        return
    try:
        centavos = parse_monto(texto)
    except ValueError:
        errores["descuento_valor"] = "Ingresá el descuento como monto, por ejemplo 20000 o 20.000,50."
        return
    if centavos <= 0:
        errores["descuento_valor"] = "El descuento tiene que ser mayor a cero."
    elif d.get("precio_centavos") and d.get("duracion_dias") and \
            centavos >= d["precio_centavos"] * periodos_anuales(d["duracion_dias"]):
        errores["descuento_valor"] = "El descuento tiene que ser menor que el precio anual del plan."
    else:
        d["descuento_anual_tipo"], d["descuento_anual_valor"] = tipo, centavos


# ------------------------------------------------------------------- pagos
def validar_pago(form, hoy: date | None = None):
    hoy = hoy or timeutils.hoy()
    errores, d = {}, {}

    d["monto_centavos"] = None
    try:
        centavos = parse_monto(form.get("monto"))
        if centavos <= 0:
            errores["monto"] = "El monto tiene que ser mayor a cero."
        elif centavos > MONTO_MAXIMO_CENTAVOS:
            errores["monto"] = "El monto es demasiado alto."
        else:
            d["monto_centavos"] = centavos
    except ValueError:
        errores["monto"] = "Ingresá un monto válido, por ejemplo 25000 o 25.000,50."

    texto_fecha = limpiar(form.get("fecha"))
    fecha = timeutils.parse_fecha(texto_fecha) if texto_fecha else hoy
    if fecha is None:
        errores["fecha"] = "La fecha del pago no es válida."
    elif fecha > hoy:
        errores["fecha"] = "La fecha del pago no puede ser futura."
    d["fecha"] = fecha

    d["metodo"] = limpiar(form.get("metodo"))
    if d["metodo"] not in models.METODOS_PAGO:
        errores["metodo"] = "Elegí cómo pagó: efectivo, transferencia o tarjeta."

    d["nota"] = limpiar(form.get("nota")) or None
    if d["nota"] and len(d["nota"]) > 300:
        errores["nota"] = "La nota es demasiado larga (máximo 300 caracteres)."

    return d, errores
