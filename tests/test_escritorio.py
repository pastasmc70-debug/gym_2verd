"""Versión de escritorio (Windows): carpeta de datos aparte, servidor local, apagado al cerrar, versión y archivos del instalador.

Lo que NO se prueba acá (no hay Windows, PyInstaller ni pywebview en este entorno): compilar el .exe, abrir la ventana real
y correr el instalador. Eso queda como prueba manual (ver README, sección «Instalador de Windows»)."""
import importlib.util
import re
import socket
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from app import create_app, escritorio
from app import db as dbm
from app.version import __version__

RAIZ = Path(__file__).resolve().parent.parent
WINDOWS = RAIZ / "windows"


def _cargar_lanzador():
    spec = importlib.util.spec_from_file_location("lanzador", WINDOWS / "lanzador.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def datos(tmp_path, monkeypatch):
    """Carpeta de datos de prueba: se pasa por GYM_DATA_DIR y sin variables de la app que molesten."""
    carpeta = tmp_path / "datos"
    monkeypatch.setenv("GYM_DATA_DIR", str(carpeta))
    for var in ("GYM_SECRET_KEY", "GYM_ADMIN_USER", "GYM_ADMIN_PASSWORD_HASH", "GYM_RECEPCION_USER",
                "GYM_RECEPCION_PASSWORD_HASH", "GYM_DB_PATH", "GYM_UPLOAD_DIR", "GYM_IMPORT_DIR", "GYM_NOMBRE"):
        monkeypatch.delenv(var, raising=False)
    return carpeta


def _puerto_abierto(puerto) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


# ------------------------------------------------------------- carpeta de datos
def test_la_variable_gym_data_dir_manda(tmp_path):
    assert escritorio.carpeta_de_datos({"GYM_DATA_DIR": str(tmp_path / "x"), "PROGRAMDATA": "C:\\PD"}, "win32") == tmp_path / "x"


def test_en_windows_los_datos_van_a_programdata(tmp_path):
    pd, ad = tmp_path / "ProgramData", tmp_path / "AppData"
    assert escritorio.carpeta_de_datos({"PROGRAMDATA": str(pd), "APPDATA": str(ad)}, "win32") == pd / "GestionGimnasio"
    assert (pd / "GestionGimnasio").is_dir()


def test_en_windows_si_programdata_no_se_puede_escribir_usa_appdata(tmp_path):
    bloqueada = tmp_path / "bloqueada"
    bloqueada.write_text("soy un archivo, no se puede crear una carpeta adentro")
    ad = tmp_path / "AppData"
    carpeta = escritorio.carpeta_de_datos({"PROGRAMDATA": str(bloqueada), "APPDATA": str(ad)}, "win32")
    assert carpeta == ad / "GestionGimnasio"


def test_en_windows_solo_con_appdata(tmp_path):
    assert escritorio.carpeta_de_datos({"APPDATA": str(tmp_path / "A")}, "win32") == tmp_path / "A" / "GestionGimnasio"


def test_en_otros_sistemas_va_a_la_carpeta_de_datos_del_usuario(tmp_path):
    assert escritorio.carpeta_de_datos({"XDG_DATA_HOME": str(tmp_path)}, "linux") == tmp_path / "GestionGimnasio"


def test_los_datos_nunca_quedan_dentro_de_la_carpeta_del_programa(tmp_path):
    for plataforma, env in (("win32", {"PROGRAMDATA": str(tmp_path / "PD")}), ("win32", {"APPDATA": str(tmp_path / "AD")}),
                            ("linux", {"XDG_DATA_HOME": str(tmp_path / "XDG")})):
        carpeta = escritorio.carpeta_de_datos(env, plataforma)
        assert not escritorio.esta_dentro(carpeta, escritorio.carpeta_del_programa())


def test_preparar_carpeta_crea_las_subcarpetas(tmp_path):
    carpeta = escritorio.preparar_carpeta(tmp_path / "d")
    for sub in ("fotos", "importaciones", "copias", "registros"):
        assert (carpeta / sub).is_dir()


def test_el_programa_instalado_se_niega_a_guardar_datos_dentro_de_si_mismo(tmp_path, monkeypatch):
    programa = tmp_path / "Program Files" / "Gestion de Gimnasio"
    programa.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(programa / "GestionGimnasio.exe"))
    with pytest.raises(RuntimeError, match="no puede estar dentro"):
        escritorio.preparar_carpeta(programa / "datos")
    assert escritorio.preparar_carpeta(tmp_path / "ProgramData" / "GestionGimnasio").is_dir()


# ------------------------------------------------------------------ la app
def test_la_app_guarda_todo_en_la_carpeta_de_datos(datos):
    app = escritorio.crear_app_de_escritorio(datos)
    assert Path(app.instance_path) == datos
    assert Path(app.config["DATABASE"]).parent == datos and Path(app.config["DATABASE"]).exists()
    assert Path(app.config["UPLOAD_DIR"]) == datos / "fotos"
    assert Path(app.config["IMPORT_DIR"]) == datos / "importaciones"
    assert (datos / "secret_key").exists()                          # la clave secreta se generó sola, junto a los datos


def test_los_datos_sobreviven_a_actualizar_el_programa(datos):
    """Actualizar = abrir una versión nueva del programa sobre la misma carpeta de datos."""
    app1 = escritorio.crear_app_de_escritorio(datos)
    clave1 = app1.config["SECRET_KEY"]
    conn = dbm.connect(app1.config["DATABASE"])
    with conn:
        conn.execute("INSERT INTO socios (nombre, dni, telefono, fecha_alta, estado, creado_en) "
                     "VALUES ('Ana Paz', '30111222', '11 5555-1234', '2026-10-01', 'activo', 'x')")
    conn.close()

    app2 = escritorio.crear_app_de_escritorio(datos)                 # «versión nueva»: otro proceso, misma carpeta
    conn = dbm.connect(app2.config["DATABASE"])
    assert conn.execute("SELECT nombre FROM socios").fetchone()[0] == "Ana Paz"
    conn.close()
    assert app2.config["SECRET_KEY"] == clave1                      # las sesiones abiertas siguen valiendo


def test_crear_la_app_sin_el_parametro_sigue_usando_la_carpeta_instance_de_siempre(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "x", "ADMIN_USER": "admin", "ADMIN_PASSWORD_HASH": "h",
                      "DATABASE": str(tmp_path / "a.db"), "UPLOAD_DIR": str(tmp_path / "f")})
    assert Path(app.instance_path).name == "instance"


# --------------------------------------------------------------------- servidor
def test_el_servidor_responde_y_al_detenerlo_libera_el_puerto(datos):
    app = escritorio.crear_app_de_escritorio(datos)
    servidor = escritorio.Servidor(app).iniciar()
    try:
        assert servidor.url.startswith("http://127.0.0.1:") and servidor.activo
        with urllib.request.urlopen(servidor.url, timeout=10) as r:        # sin administrador: lleva al asistente
            html = r.read().decode()
        assert r.status == 200 and "Mi Gimnasio" in html
        assert f"versión {__version__}" in html                              # la versión se ve en pantalla
    finally:
        servidor.detener()
    assert not servidor.activo and not _puerto_abierto(servidor.puerto)


def test_el_servidor_solo_escucha_en_esta_computadora(datos):
    servidor = escritorio.Servidor(escritorio.crear_app_de_escritorio(datos)).iniciar()
    try:
        assert servidor._servidor.server_address[0] == "127.0.0.1"
    finally:
        servidor.detener()


def test_cada_arranque_elige_un_puerto_libre(datos):
    a = escritorio.Servidor(escritorio.crear_app_de_escritorio(datos)).iniciar()
    try:
        b = escritorio.Servidor(escritorio.crear_app_de_escritorio(datos)).iniciar()
        try:
            assert a.puerto != b.puerto
        finally:
            b.detener()
    finally:
        a.detener()


# ----------------------------------------------------------------------- registro
def test_el_registro_va_a_un_archivo_y_sin_consola_no_falla(tmp_path, monkeypatch):
    import logging
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    antes = list(logging.getLogger().handlers)
    ruta = escritorio.configurar_registro(tmp_path)
    try:
        logging.getLogger("prueba").info("hola desde la prueba")
        for h in logging.getLogger().handlers:
            h.flush()
        assert "hola desde la prueba" in ruta.read_text(encoding="utf-8")
        print("esto no debe romper aunque no haya consola")
    finally:
        for h in list(logging.getLogger().handlers):
            if h not in antes:
                logging.getLogger().removeHandler(h)
                h.close()


# --------------------------------------------------------------------- lanzador
def test_autocomprobacion_ok_escribe_el_resultado_en_la_carpeta_de_datos(datos):
    lanzador = _cargar_lanzador()
    assert lanzador.autocomprobar(datos) == 0
    assert f"AUTOCOMPROBACION OK versión {__version__}" in (datos / "registros" / "autocomprobacion.txt").read_text(encoding="utf-8")


def test_autocomprobacion_que_falla_devuelve_1_y_lo_deja_escrito(datos, monkeypatch):
    lanzador = _cargar_lanzador()
    monkeypatch.setattr(lanzador.escritorio, "crear_app_de_escritorio", lambda c=None: (_ for _ in ()).throw(RuntimeError("roto")))
    assert lanzador.autocomprobar(datos) == 1
    assert "FALLA" in (datos / "registros" / "autocomprobacion.txt").read_text(encoding="utf-8")


def test_main_con_autocomprobar_no_abre_ventana(datos):
    lanzador = _cargar_lanzador()
    assert lanzador.main(["--autocomprobar"]) == 0


class _WebviewFalso:
    """Simula pywebview: `start` vuelve enseguida, como cuando el usuario cierra la ventana."""
    def __init__(self, falla=False):
        self.ventanas, self.iniciada, self.falla = [], False, falla

    def create_window(self, titulo, url, **kw):
        self.ventanas.append((titulo, url, kw))

    def start(self, **kw):
        self.iniciada = True
        if self.falla:
            raise RuntimeError("no hay WebView2")


def test_al_cerrar_la_ventana_se_apaga_el_servidor(datos, monkeypatch):
    lanzador = _cargar_lanzador()
    falso = _WebviewFalso()
    monkeypatch.setitem(sys.modules, "webview", falso)
    visto = {}
    real = falso.start
    falso.start = lambda **kw: (visto.update(abierto=_puerto_abierto(int(falso.ventanas[0][1].split(":")[2].rstrip("/")))), real(**kw))[1]

    assert lanzador.main([]) == 0

    titulo, url, kw = falso.ventanas[0]
    assert falso.iniciada and visto["abierto"] is True                      # mientras la ventana está abierta, el servidor responde
    assert titulo.endswith(__version__) and kw["width"] >= 800
    assert not _puerto_abierto(int(url.split(":")[2].rstrip("/")))          # al cerrarla, el servidor ya no escucha
    assert "Servidor apagado" in (datos / "registros" / "gimnasio.log").read_text(encoding="utf-8")


def test_si_no_se_puede_abrir_la_ventana_avisa_y_apaga_el_servidor(datos, monkeypatch):
    lanzador = _cargar_lanzador()
    falso = _WebviewFalso(falla=True)
    monkeypatch.setitem(sys.modules, "webview", falso)
    avisos = []
    monkeypatch.setattr(lanzador, "_aviso", avisos.append)

    assert lanzador.main([]) == 1

    assert avisos and "No se pudo abrir la ventana" in avisos[0]
    assert not _puerto_abierto(int(falso.ventanas[0][1].split(":")[2].rstrip("/")))


# ------------------------------------------- versión y archivos del instalador (controles de texto)
def test_la_version_es_semver_y_se_ve_en_la_pantalla(nav):
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    assert f"versión {__version__}" in nav.get("/configuracion/").get_data(as_text=True)


def test_el_instalador_toma_la_misma_version_que_la_app():
    iss = (WINDOWS / "instalador.iss").read_text(encoding="utf-8")
    assert f'#define AppVersion "{__version__}"' in iss
    assert "AppVersion={#AppVersion}" in iss
    assert "app.version" in (RAIZ / ".github" / "workflows" / "instalador-windows.yml").read_text(encoding="utf-8")
    assert "app.version" in (WINDOWS / "construir.ps1").read_text(encoding="utf-8")


def test_el_instalador_actualiza_sin_duplicar_y_no_borra_los_datos():
    iss = (WINDOWS / "instalador.iss").read_text(encoding="utf-8")
    assert re.search(r"^AppId=\{\{[0-9A-F-]{36}\}", iss, re.M)                          # id fijo: actualiza en lugar de duplicar
    assert "DefaultDirName={autopf}" in iss and "Spanish.isl" in iss and "SetupIconFile=icono.ico" in iss
    assert re.search(r'\[Dirs\]\s*(;.*\n)*Name: "\{commonappdata\}\\GestionGimnasio"; Permissions: users-modify; Flags: uninsneveruninstall', iss)
    assert not re.search(r"^\[UninstallDelete\]", iss, re.M)                              # nada borra datos al desinstalar
    assert "{commonappdata}" not in re.search(r"\[Files\](.*?)\n\[", iss, re.S).group(1)  # los datos no son archivos del programa
    assert '{group}\\Gestión de Gimnasio' in iss and "{autodesktop}" in iss and "{uninstallexe}" in iss
    assert (WINDOWS / "icono.ico").exists()


def test_el_spec_arma_una_carpeta_sin_consola_con_icono_y_los_archivos_de_la_app():
    spec = (WINDOWS / "gimnasio.spec").read_text(encoding="utf-8")
    assert "console=False" in spec and "icono.ico" in spec and "COLLECT(" in spec and "exclude_binaries=True" in spec
    for necesario in ('"app/templates"', '"app/static"', '"app"', 'collect_data_files("tzdata")', "lanzador.py"):
        assert necesario in spec
    assert "onefile" not in spec


def test_el_icono_es_un_ico_valido_con_tamano_256():
    datos_ico = (WINDOWS / "icono.ico").read_bytes()
    reservado, tipo, cantidad = struct.unpack("<HHH", datos_ico[:6])
    assert (reservado, tipo) == (0, 1) and cantidad >= 4
    tamanos = [datos_ico[6 + 16 * i] or 256 for i in range(cantidad)]
    assert 256 in tamanos and 16 in tamanos


def test_el_workflow_corre_en_windows_ejecuta_tests_y_deja_el_instalador_como_artefacto():
    wf = (RAIZ / ".github" / "workflows" / "instalador-windows.yml").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in wf and "workflow_dispatch" in wf
    assert "pytest" in wf and "pyinstaller windows/gimnasio.spec" in wf and "--autocomprobar" in wf
    assert "ISCC.exe" in wf and "actions/upload-artifact@v4" in wf and "if-no-files-found: error" in wf


def test_las_dependencias_de_empaquetado_no_se_mezclan_con_las_del_programa():
    ventana = (WINDOWS / "requirements-windows.txt").read_text(encoding="utf-8")
    assert re.search(r"^pyinstaller==", ventana, re.M) and re.search(r"^pywebview==", ventana, re.M)
    for archivo in ("requirements.txt", "requirements-dev.txt"):
        texto = (RAIZ / archivo).read_text(encoding="utf-8").lower()
        assert "pyinstaller" not in texto and "pywebview" not in texto
