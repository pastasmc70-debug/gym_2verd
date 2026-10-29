# PyInstaller (modo carpeta). Se corre desde la raíz del proyecto:  pyinstaller windows/gimnasio.spec --noconfirm
# Resultado: dist/GestionGimnasio/GestionGimnasio.exe  (ventana sin consola, con ícono, sin Python instalado)
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

RAIZ = Path(SPECPATH).parent

datos = [
    (str(RAIZ / "app" / "templates"), "app/templates"),
    (str(RAIZ / "app" / "static"), "app/static"),
    (str(RAIZ / "app" / "schema.sql"), "app"),
]
datos += collect_data_files("tzdata")            # zona horaria America/Argentina/Buenos_Aires en Windows

a = Analysis(
    [str(RAIZ / "windows" / "lanzador.py")],
    pathex=[str(RAIZ)],
    datas=datos,
    hiddenimports=collect_submodules("app") + collect_submodules("webview"),
    excludes=["pytest", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GestionGimnasio",
    console=False,                                # ventana propia, sin consola negra
    icon=str(RAIZ / "windows" / "icono.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="GestionGimnasio")
