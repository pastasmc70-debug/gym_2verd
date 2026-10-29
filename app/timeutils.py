"""Fechas y horas siempre en America/Argentina/Buenos_Aires."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def ahora() -> datetime:
    return datetime.now(TZ)


def hoy() -> date:
    return ahora().date()


def parse_fecha(texto) -> date | None:
    """Convierte 'AAAA-MM-DD' en date; devuelve None si no es una fecha válida."""
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


def fecha_ar(valor) -> str:
    """dd/mm/aaaa para mostrar. Acepta date, 'AAAA-MM-DD' o None."""
    if not valor:
        return "—"
    if isinstance(valor, str):
        valor = date.fromisoformat(valor[:10])
    return valor.strftime("%d/%m/%Y")


def primer_dia_mes(d: date) -> date:
    return d.replace(day=1)


def primer_dia_mes_siguiente(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)
