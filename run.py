"""Punto de entrada para desarrollo y uso local:  python run.py"""
import os

from app import create_app
from app.config import ErrorDeConfiguracion

try:
    app = create_app()
except ErrorDeConfiguracion as error:
    raise SystemExit(f"\nNo se pudo iniciar: {error}\n")

if __name__ == "__main__":
    # Por defecto escucha solo en esta computadora. Para abrirlo a la red local: HOST=0.0.0.0
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=False)
