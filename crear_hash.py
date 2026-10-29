"""Genera el hash de una clave para guardarlo en una variable de entorno.

Uso:
    python crear_hash.py                    # clave del administrador  -> GYM_ADMIN_PASSWORD_HASH
    python crear_hash.py recepcion          # clave de recepción       -> GYM_RECEPCION_PASSWORD_HASH
    python crear_hash.py kiosco             # clave del kiosco         -> GYM_KIOSCO_CLAVE_HASH
La clave nunca se guarda en texto plano: la app solo conoce el hash.
"""
import getpass
import sys

VARIABLES = {
    "admin": "GYM_ADMIN_PASSWORD_HASH",
    "recepcion": "GYM_RECEPCION_PASSWORD_HASH",
    "kiosco": "GYM_KIOSCO_CLAVE_HASH",
}

from werkzeug.security import generate_password_hash


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    quien = argv[0] if argv else "admin"
    if quien not in VARIABLES or len(argv) > 1:
        print(f"Uso: python crear_hash.py [{'|'.join(VARIABLES)}]", file=sys.stderr)
        return 1
    clave = getpass.getpass("Clave nueva (mínimo 10 caracteres): ")
    if len(clave) < 10:
        print("La clave es muy corta: usá al menos 10 caracteres.", file=sys.stderr)
        return 1
    if clave != getpass.getpass("Repetí la clave: "):
        print("Las claves no coinciden.", file=sys.stderr)
        return 1
    print("\nCopiá esta línea tal cual (con las comillas simples) en tu configuración:\n")
    print(f"{VARIABLES[quien]}='{generate_password_hash(clave)}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
