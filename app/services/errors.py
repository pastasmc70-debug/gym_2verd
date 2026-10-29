class ErrorDeNegocio(Exception):
    """Regla de negocio incumplida. El mensaje está listo para mostrárselo al usuario.

    `codigo` identifica el motivo (por ejemplo 'vencida' o 'sin_pago') para quien necesite
    decidir qué mostrar según el caso, como el modo kiosco. `datos` lleva información extra.
    """

    def __init__(self, mensaje: str, codigo: str | None = None, **datos):
        super().__init__(mensaje)
        self.codigo = codigo
        self.datos = datos


class RequiereConfirmacion(ErrorDeNegocio):
    """La operación es válida pero necesita que la persona la confirme de forma explícita."""
