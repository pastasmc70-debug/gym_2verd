"""Roles y permisos.

Hay tres tipos de sesión:
  - administrador: puede todo.
  - recepción: SOLO puede lo que figura en ENDPOINTS_RECEPCION (cargar socios, ingresos y pagos).
    Todo lo que no esté en esa lista queda reservado al administrador: si mañana se agrega una
    pantalla nueva, nace bloqueada para recepción hasta que alguien la habilite a propósito.
  - kiosco: la PC de la recepción con el teclado numérico. Solo ve las pantallas de /kiosco.
"""
import time

from flask import current_app, session

ADMIN, RECEPCION, KIOSCO = "admin", "recepcion", "kiosco"

ENDPOINTS_RECEPCION = frozenset({
    "inicio.panel",
    "socios.lista", "socios.nuevo", "socios.editar", "socios.detalle", "socios.foto", "socios.selector_lista",
    "membresias.asignar", "membresias.elegir",
    "pagos.lista", "pagos.nuevo",
    "asistencia.pantalla", "asistencia.ingreso",
    "alertas.lista",
    "planes.lista",                      # puede ver los planes, no editarlos
    "caja.diaria",
    "tienda.nueva_venta", "tienda.ventas", "tienda.detalle_venta",
    "auth.logout",
})


def rol_actual() -> str | None:
    """El rol de la sesión, o None si no hay sesión válida (o si la del personal ya venció)."""
    rol = session.get("rol")
    if rol in (ADMIN, RECEPCION):
        horas = current_app.config["SESION_PERSONAL_HORAS"]
        if time.time() - session.get("inicio", 0) > horas * 3600:
            session.clear()
            return None
        return rol
    if rol == KIOSCO:
        dias = current_app.config["KIOSCO_SESION_DIAS"]
        if time.time() - session.get("inicio", 0) > dias * 86400:
            session.clear()
            return None
        return KIOSCO
    return None


def usuario_actual() -> str | None:
    return session.get("usuario") if rol_actual() else None


def es_admin() -> bool:
    return rol_actual() == ADMIN


def puede(endpoint: str, rol: str | None) -> bool:
    if rol == ADMIN:
        return not endpoint.startswith("kiosco.")
    if rol == RECEPCION:
        return endpoint in ENDPOINTS_RECEPCION
    if rol == KIOSCO:
        return endpoint.startswith("kiosco.")
    return False


def iniciar_sesion(rol: str, usuario: str, sello: str | None = None) -> None:
    session.clear()
    session["rol"] = rol
    session["usuario"] = usuario
    session["sello"] = sello  # huella de la clave (solo recepción): si la cambian, esta sesión deja de valer
    session["inicio"] = time.time()
    session.permanent = True
