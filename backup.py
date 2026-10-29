"""Genera una copia de seguridad (base de datos + fotos) en un .zip. Pensado para programarlo.

Uso:
    python backup.py                              # guarda en la carpeta respaldos/
    python backup.py --destino /mnt/usb/respaldos
    python backup.py --conservar 14               # deja solo los 14 respaldos más nuevos (por defecto 30)

Usa las mismas variables que el sistema: GYM_DB_PATH y GYM_UPLOAD_DIR (por defecto instance/).
No hace falta tener cargadas las claves. Termina con código 0 si salió bien y 1 si falló.

Linux/macOS (todos los días a las 23:00):   0 23 * * *  cd /ruta/al/proyecto && .venv/bin/python backup.py
Windows: Programador de tareas -> acción «Iniciar un programa» -> .venv\\Scripts\\python.exe con el argumento backup.py
"""
import argparse
import os
import sys
from pathlib import Path

from app.services import backup
from app.services.errors import ErrorDeNegocio

RAIZ = Path(__file__).resolve().parent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Copia de seguridad de la base de datos y las fotos.")
    parser.add_argument("--destino", default=str(RAIZ / "respaldos"), help="carpeta donde guardar el .zip")
    parser.add_argument("--conservar", type=int, default=30, metavar="N",
                        help="cantidad de respaldos a conservar en la carpeta (0 = no borrar nada). Por defecto 30")
    args = parser.parse_args(argv)

    ruta_db = os.environ.get("GYM_DB_PATH") or str(RAIZ / "instance" / "gimnasio.db")
    carpeta_fotos = os.environ.get("GYM_UPLOAD_DIR") or str(RAIZ / "instance" / "fotos")
    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / backup.nombre_de_archivo()

    try:
        fotos = backup.crear_respaldo(ruta_db, carpeta_fotos, archivo)
    except (ErrorDeNegocio, OSError) as error:
        archivo.unlink(missing_ok=True)
        print(f"No se pudo generar la copia de seguridad: {error}", file=sys.stderr)
        return 1

    print(f"Copia de seguridad lista: {archivo} ({fotos} fotos, {archivo.stat().st_size / 1024:.0f} KB)")
    if args.conservar > 0:
        for viejo in backup.conservar_ultimos(str(destino), args.conservar):
            print(f"Se borró el respaldo viejo {viejo.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
