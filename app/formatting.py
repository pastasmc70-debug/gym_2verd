"""Formato de montos en pesos argentinos."""


def pesos(centavos) -> str:
    """15000 pesos -> '$ 15.000'; 15000,50 -> '$ 15.000,50' (formato argentino)."""
    centavos = int(centavos or 0)
    enteros, resto = divmod(centavos, 100)
    texto = f"{enteros:,}".replace(",", ".")
    return f"$ {texto},{resto:02d}" if resto else f"$ {texto}"


def monto_form(centavos) -> str:
    """Valor para precargar un input de monto: 25000 o 25000,50."""
    enteros, resto = divmod(int(centavos or 0), 100)
    return f"{enteros},{resto:02d}" if resto else str(enteros)
