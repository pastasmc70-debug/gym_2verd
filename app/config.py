"""Configuración de la app. Todo lo sensible viene de variables de entorno."""
import os
from datetime import timedelta


class ErrorDeConfiguracion(RuntimeError):
    pass


def _bool(valor, defecto: bool) -> bool:
    """'1', 'si', 'sí', 'true', 'on' -> True; '0', 'no', 'false', 'off' -> False; vacío -> defecto."""
    if valor is None or not valor.strip():
        return defecto
    texto = valor.strip().lower()
    if texto in ("1", "si", "sí", "true", "yes", "on", "verdadero"):
        return True
    if texto in ("0", "no", "false", "off", "falso"):
        return False
    raise ErrorDeConfiguracion(f"No entiendo el valor «{valor}»: usá 1 o 0 (también sí / no).")


def _entero(valor, defecto: int, nombre: str) -> int:
    if valor is None or not valor.strip():
        return defecto
    try:
        return int(valor)
    except ValueError:
        raise ErrorDeConfiguracion(f"{nombre} tiene que ser un número entero.") from None


def config_desde_entorno(instance_path: str) -> dict:
    env = os.environ
    return {
        "SECRET_KEY": env.get("GYM_SECRET_KEY"),
        "ADMIN_USER": env.get("GYM_ADMIN_USER"),
        "ADMIN_PASSWORD_HASH": env.get("GYM_ADMIN_PASSWORD_HASH"),
        # Usuario de recepción (opcional): puede cargar socios, ingresos y pagos, pero nada más.
        "RECEPCION_USER": env.get("GYM_RECEPCION_USER"),
        "RECEPCION_PASSWORD_HASH": env.get("GYM_RECEPCION_PASSWORD_HASH"),
        "DATABASE": env.get("GYM_DB_PATH") or os.path.join(instance_path, "gimnasio.db"),
        "UPLOAD_DIR": env.get("GYM_UPLOAD_DIR") or os.path.join(instance_path, "fotos"),
        "IMPORT_DIR": env.get("GYM_IMPORT_DIR") or os.path.join(instance_path, "importaciones"),
        "GYM_NOMBRE": env.get("GYM_NOMBRE", "Mi Gimnasio"),
        "DIAS_ALERTA": _entero(env.get("GYM_DIAS_ALERTA"), 7, "GYM_DIAS_ALERTA"),
        # «Adentro ahora (aprox.)»: se cuentan los socios que ingresaron en las últimas N horas (no se registra la salida)
        "HORAS_ADENTRO": _entero(env.get("GYM_HORAS_ADENTRO"), 2, "GYM_HORAS_ADENTRO"),
        # Reglas de ingreso
        "ACCESO_SIN_PAGO": _bool(env.get("GYM_ACCESO_SIN_PAGO"), False),
        "PERMITIR_REINGRESO": _bool(env.get("GYM_PERMITIR_REINGRESO"), False),
        "LIMITAR_CLASES_SEMANA": _bool(env.get("GYM_LIMITAR_CLASES_SEMANA"), True),
        # Módulo opcional
        "MODULO_TIENDA": _bool(env.get("GYM_MODULO_TIENDA"), False),
        # Modo kiosco (pantalla de ingreso con teclado numérico en la recepción)
        "KIOSCO_CLAVE_HASH": env.get("GYM_KIOSCO_CLAVE_HASH"),
        "KIOSCO_SONIDO": _bool(env.get("GYM_KIOSCO_SONIDO"), True),
        "KIOSCO_TECLADO_PANTALLA": _bool(env.get("GYM_KIOSCO_TECLADO"), False),
        "KIOSCO_MAX_INTENTOS_POR_MINUTO": _entero(env.get("GYM_KIOSCO_MAX_POR_MINUTO"), 15, "GYM_KIOSCO_MAX_POR_MINUTO"),
        "KIOSCO_SESION_DIAS": _entero(env.get("GYM_KIOSCO_SESION_DIAS"), 30, "GYM_KIOSCO_SESION_DIAS"),
        # Copia de seguridad automática diaria: carpeta (vacía = apagada). También se elige en Configuración.
        "BACKUP_DIR": env.get("GYM_BACKUP_DIR") or "",
        "BACKUP_HILO": True,  # el proceso revisa cada 15 minutos si toca la copia del día (se apaga en los tests)
        "CSRF_ACTIVO": True,
        "MAX_CONTENT_LENGTH": 3 * 1024 * 1024,  # fotos de hasta 3 MB
        # La cookie dura lo que dure la sesión de kiosco; la del personal se vence a las horas indicadas.
        "PERMANENT_SESSION_LIFETIME": timedelta(days=30),
        "SESION_PERSONAL_HORAS": 12,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        # Poné GYM_COOKIE_SECURE=1 cuando lo sirvas por HTTPS.
        "SESSION_COOKIE_SECURE": env.get("GYM_COOKIE_SECURE") == "1",
    }


def validar_config(config) -> None:
    # El administrador puede no estar definido: en ese caso la primera vez aparece el asistente.
    # Lo que no vale es definirlo a medias.
    if bool(config.get("ADMIN_USER")) != bool(config.get("ADMIN_PASSWORD_HASH")):
        faltante = "GYM_ADMIN_PASSWORD_HASH" if config.get("ADMIN_USER") else "GYM_ADMIN_USER"
        raise ErrorDeConfiguracion(
            f"Falta la variable {faltante}: el administrador necesita las dos (GYM_ADMIN_USER y GYM_ADMIN_PASSWORD_HASH). "
            "Si no definís ninguna, la primera vez que abras la app te la pide un asistente."
        )
    if bool(config.get("RECEPCION_USER")) != bool(config.get("RECEPCION_PASSWORD_HASH")):
        raise ErrorDeConfiguracion(
            "Para habilitar el usuario de recepción hacen falta las dos variables: "
            "GYM_RECEPCION_USER y GYM_RECEPCION_PASSWORD_HASH."
        )
    if config.get("RECEPCION_USER") and config["RECEPCION_USER"] == config["ADMIN_USER"]:
        raise ErrorDeConfiguracion("El usuario de recepción tiene que ser distinto del administrador.")
    if config["DIAS_ALERTA"] < 0 or config["KIOSCO_MAX_INTENTOS_POR_MINUTO"] < 1:
        raise ErrorDeConfiguracion("GYM_DIAS_ALERTA no puede ser negativo y GYM_KIOSCO_MAX_POR_MINUTO tiene que ser al menos 1.")
    if not 1 <= config.get("HORAS_ADENTRO", 2) <= 12:
        raise ErrorDeConfiguracion("GYM_HORAS_ADENTRO tiene que estar entre 1 y 12.")
