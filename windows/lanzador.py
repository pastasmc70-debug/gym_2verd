"""Punto de entrada del programa de Windows (el que empaqueta PyInstaller): abre la app en una ventana propia.

  GestionGimnasio.exe                  abre la ventana (sin barra de navegador)
  GestionGimnasio.exe --autocomprobar  arranca el servidor, pide la pantalla de ingreso y sale (la usa el workflow de GitHub)

Al cerrar la ventana se apaga el servidor. Los datos viven en la carpeta de datos (ver app/escritorio.py), nunca acá.
"""
import logging
import sys
import urllib.request
from pathlib import Path

from app import escritorio
from app.config import ErrorDeConfiguracion
from app.version import __version__

TITULO = f"Gestión de Gimnasio {__version__}"
log = logging.getLogger("lanzador")


def _aviso(texto: str) -> None:
    """Mensaje visible aunque no haya consola (cuadro de Windows); en otros sistemas, a la salida de error."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, texto, TITULO, 0x10)
    except Exception:  # noqa: BLE001
        print(texto, file=sys.stderr)


def autocomprobar(carpeta=None) -> int:
    """Arranca todo sin ventana y verifica que la pantalla inicial responde. Devuelve 0 si está bien.
    El resultado también queda escrito en <datos>/registros/autocomprobacion.txt: el .exe no tiene consola, así que
    ese archivo (y no la pantalla) es lo que lee el workflow de GitHub."""
    carpeta = escritorio.preparar_carpeta(carpeta or escritorio.carpeta_de_datos())
    servidor, codigo, mensaje = None, 1, ""
    try:
        app = escritorio.crear_app_de_escritorio(carpeta)
        servidor = escritorio.Servidor(app).iniciar()
        # Sin administrador, la primera vez redirige al asistente: también cuenta como respuesta correcta.
        with urllib.request.urlopen(servidor.url, timeout=10) as r:
            cuerpo = r.read().decode("utf-8", "ignore")
        if r.status == 200 and ("Gimnasio" in cuerpo or "Gestión" in cuerpo):
            codigo, mensaje = 0, f"AUTOCOMPROBACION OK versión {__version__}"
        else:
            mensaje = "AUTOCOMPROBACION FALLA: la pantalla inicial no tiene el contenido esperado"
    except Exception as e:  # noqa: BLE001
        mensaje = f"AUTOCOMPROBACION FALLA: {type(e).__name__}: {e}"
    finally:
        if servidor:
            servidor.detener()
    (Path(carpeta) / "registros" / "autocomprobacion.txt").write_text(mensaje + "\n", encoding="utf-8")
    print(mensaje)
    return codigo


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    carpeta = escritorio.preparar_carpeta(escritorio.carpeta_de_datos())
    escritorio.configurar_registro(carpeta)
    if "--autocomprobar" in argv:
        return autocomprobar(carpeta)
    try:
        app = escritorio.crear_app_de_escritorio(carpeta)
    except ErrorDeConfiguracion as e:
        log.error("Configuración inválida: %s", e)
        _aviso(f"No se pudo iniciar: {e}")
        return 1
    servidor = escritorio.Servidor(app).iniciar()
    log.info("Servidor en %s (datos en %s)", servidor.url, carpeta)
    try:
        import webview  # pywebview: la ventana propia, sin barra de navegador
        webview.create_window(TITULO, servidor.url, width=1280, height=820, min_size=(360, 560), text_select=True)
        webview.start(icon=str(Path(__file__).with_name("icono.ico")) if Path(__file__).with_name("icono.ico").exists() else None)
    except Exception as e:  # noqa: BLE001
        log.exception("No se pudo abrir la ventana")
        _aviso(f"No se pudo abrir la ventana del programa: {e}\nMás datos en {carpeta / 'registros' / 'gimnasio.log'}")
        return 1
    finally:
        servidor.detener()  # cerrar la ventana apaga el servidor
        log.info("Servidor apagado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
