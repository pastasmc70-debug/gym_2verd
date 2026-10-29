"""Lo que necesita la versión de escritorio (instalador de Windows): dónde van los datos, el servidor local y el registro.

Está separado del lanzador (windows/lanzador.py) para poder probarlo en cualquier sistema: el lanzador solo agrega
la ventana (pywebview). Regla central: los datos (base, fotos, copias, clave secreta) viven en una carpeta aparte
y NUNCA dentro de la carpeta del programa, así actualizar o desinstalar el programa no los toca.
"""
import logging
import os
import socket
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from werkzeug.serving import make_server

NOMBRE_CARPETA = "GestionGimnasio"


def _es_escribible(carpeta: Path) -> bool:
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / ".escritura"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
        return True
    except OSError:
        return False


def carpeta_de_datos(env=None, plataforma: str | None = None) -> Path:
    """Carpeta donde viven los datos.

    - GYM_DATA_DIR, si está definida (para quien quiere elegir otra).
    - Windows: %PROGRAMDATA%\\GestionGimnasio (compartida por todos los usuarios de la PC; la crea el instalador con
      permiso de escritura). Si esa no se puede escribir, %APPDATA%\\GestionGimnasio (la de cada usuario).
    - Otros sistemas (para desarrollo y pruebas): ~/.local/share/GestionGimnasio.
    """
    env = os.environ if env is None else env
    plataforma = plataforma or sys.platform
    if env.get("GYM_DATA_DIR"):
        return Path(env["GYM_DATA_DIR"])
    if plataforma.startswith("win"):
        candidatas = [Path(env[v]) / NOMBRE_CARPETA for v in ("PROGRAMDATA", "APPDATA") if env.get(v)]
        for carpeta in candidatas:
            if _es_escribible(carpeta):
                return carpeta
        if candidatas:
            return candidatas[-1]
        return Path.home() / NOMBRE_CARPETA
    return Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / NOMBRE_CARPETA


def carpeta_del_programa() -> Path:
    """Donde está el programa instalado (con PyInstaller, la carpeta del .exe)."""
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def esta_dentro(carpeta: Path, otra: Path) -> bool:
    try:
        Path(carpeta).resolve().relative_to(Path(otra).resolve())
        return True
    except ValueError:
        return False


def preparar_carpeta(carpeta: Path) -> Path:
    """Crea la carpeta de datos con sus subcarpetas y se niega a usar una que esté dentro del programa."""
    carpeta = Path(carpeta)
    if esta_dentro(carpeta, carpeta_del_programa()) and getattr(sys, "frozen", False):
        raise RuntimeError("La carpeta de datos no puede estar dentro de la carpeta del programa.")
    for sub in ("", "fotos", "importaciones", "copias", "registros"):
        (carpeta / sub).mkdir(parents=True, exist_ok=True)
    return carpeta


def configurar_registro(carpeta: Path) -> Path:
    """Manda el registro a un archivo de la carpeta de datos. Sin consola (ventana de escritorio) no hay stdout ni
    stderr: se reemplazan para que nada falle al intentar imprimir."""
    ruta = Path(carpeta) / "registros" / "gimnasio.log"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    manejador = RotatingFileHandler(ruta, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    if not any(getattr(h, "baseFilename", None) == str(ruta) for h in raiz.handlers):
        raiz.addHandler(manejador)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    return ruta


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Servidor:
    """El servidor de la app en un hilo, solo en esta computadora (127.0.0.1). `detener()` lo apaga y libera el puerto."""

    def __init__(self, app, puerto: int | None = None):
        self.puerto = puerto or puerto_libre()
        self._servidor = make_server("127.0.0.1", self.puerto, app, threaded=True)
        self._hilo = threading.Thread(target=self._servidor.serve_forever, name="servidor-gimnasio", daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.puerto}/"

    def iniciar(self) -> "Servidor":
        self._hilo.start()
        return self

    def detener(self) -> None:
        self._servidor.shutdown()
        self._servidor.server_close()
        self._hilo.join(timeout=5)

    @property
    def activo(self) -> bool:
        return self._hilo.is_alive()


def crear_app_de_escritorio(carpeta: Path | None = None, test_config=None):
    """Arma la app con todos los datos en la carpeta de datos (base, fotos, importaciones, clave secreta)."""
    from . import create_app
    carpeta = preparar_carpeta(carpeta or carpeta_de_datos())
    return create_app(test_config, instance_path=str(carpeta))
