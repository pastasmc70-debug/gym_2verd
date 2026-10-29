"""Copia de seguridad automática: una por día, en la carpeta elegida, con las últimas 14 y avisos en el panel."""
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app import timeutils
from app.services import backup, backup_auto, configuracion

LUNES = datetime(2026, 10, 19, 23, 30, tzinfo=timeutils.TZ)


@pytest.fixture
def carpeta(app, tmp_path):
    destino = tmp_path / "copias"
    app.config["BACKUP_DIR"] = str(destino)
    return destino


def _zips(carpeta):
    return sorted(p.name for p in Path(carpeta).glob("copia-seguridad_*.zip"))


def _dias(n):
    return LUNES + timedelta(days=n)


# ------------------------------------------------------------------ la copia diaria
def test_sin_carpeta_no_hace_nada(app, db):
    app.config["BACKUP_DIR"] = ""
    assert backup_auto.ejecutar(db, app.config, LUNES) is None


def test_hace_una_copia_valida_con_la_base_y_las_fotos(app, db, carpeta, crear_socio, tmp_path):
    crear_socio(nombre="Ana Paz", dni="30000001")
    fotos = Path(app.config["UPLOAD_DIR"])
    fotos.mkdir(parents=True, exist_ok=True)
    (fotos / "a.jpg").write_bytes(b"\xff\xd8\xff-foto")

    r = backup_auto.ejecutar(db, app.config, LUNES)

    assert r["ok"] and r["fotos"] == 1
    assert _zips(carpeta) == ["copia-seguridad_2026-10-19_233000.zip"]
    z = zipfile.ZipFile(carpeta / _zips(carpeta)[0])
    assert sorted(z.namelist()) == ["LEEME.txt", "fotos/a.jpg", "gimnasio.db"]
    z.extract("gimnasio.db", tmp_path)
    copia = sqlite3.connect(tmp_path / "gimnasio.db")
    assert copia.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 1
    assert copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    copia.close()
    assert not (carpeta / backup_auto.TEMPORAL).exists()


def test_crea_la_carpeta_si_no_existe(app, db, tmp_path):
    app.config["BACKUP_DIR"] = str(tmp_path / "no" / "existe" / "todavia")
    assert backup_auto.ejecutar(db, app.config, LUNES)["ok"]


def test_una_sola_copia_por_dia_y_otra_al_dia_siguiente(app, db, carpeta):
    assert backup_auto.ejecutar(db, app.config, LUNES)["ok"]
    assert backup_auto.ejecutar(db, app.config, LUNES + timedelta(minutes=20)) is None   # mismo día
    assert backup_auto.ejecutar(db, app.config, _dias(1).replace(hour=0, minute=5))["ok"]  # pasó la medianoche
    assert len(_zips(carpeta)) == 2


def test_forzar_hace_otra_aunque_ya_haya_una_hoy(app, db, carpeta):
    backup_auto.ejecutar(db, app.config, LUNES)
    assert backup_auto.ejecutar(db, app.config, LUNES + timedelta(minutes=1), forzar=True)["ok"]
    assert len(_zips(carpeta)) == 2


def test_cambiar_de_carpeta_hace_la_copia_de_hoy_en_la_nueva(app, db, carpeta, tmp_path):
    backup_auto.ejecutar(db, app.config, LUNES)
    nueva = tmp_path / "pendrive"
    app.config["BACKUP_DIR"] = str(nueva)
    assert backup_auto.ejecutar(db, app.config, LUNES + timedelta(minutes=5))["ok"]
    assert len(_zips(nueva)) == 1 and len(_zips(carpeta)) == 1


# ---------------------------------------------------------------------- retención
def test_conserva_solo_las_ultimas_14_y_no_toca_otros_archivos(app, db, carpeta):
    carpeta.mkdir()
    (carpeta / "mis-fotos.zip").write_bytes(b"x")
    (carpeta / "notas.txt").write_text("importante")
    for dia in range(20):
        assert backup_auto.ejecutar(db, app.config, _dias(dia))["ok"]
    zips = _zips(carpeta)
    assert len(zips) == 14
    assert zips[0] == "copia-seguridad_2026-10-25_233000.zip" and zips[-1] == "copia-seguridad_2026-11-07_233000.zip"
    assert (carpeta / "mis-fotos.zip").exists() and (carpeta / "notas.txt").read_text() == "importante"


def test_con_menos_de_14_no_borra_nada(app, db, carpeta):
    for dia in range(5):
        backup_auto.ejecutar(db, app.config, _dias(dia))
    assert len(_zips(carpeta)) == 5


# ------------------------------------------------------------------------ fallas
def test_si_la_carpeta_no_se_puede_usar_queda_el_error_y_no_se_pierde_nada(app, db, carpeta, tmp_path):
    backup_auto.ejecutar(db, app.config, LUNES)                          # una copia buena de antes
    archivo = tmp_path / "es-un-archivo"
    archivo.write_text("no soy una carpeta")
    app.config["BACKUP_DIR"] = str(archivo)                               # p. ej. el pendrive desenchufado
    r = backup_auto.ejecutar(db, app.config, _dias(1))
    assert r["ok"] is False and r["error"]
    assert len(_zips(carpeta)) == 1                                       # las copias viejas siguen ahí
    g = configuracion.leer_todo(db)
    assert g["backup_error_msg"] and g["backup_ultimo_ok"].startswith("2026-10-19") and g["backup_en_curso"] == ""


def test_despues_de_una_falla_reintenta_y_limpia_el_error(app, db, carpeta, tmp_path):
    archivo = tmp_path / "es-un-archivo"
    archivo.write_text("x")
    app.config["BACKUP_DIR"] = str(archivo)
    assert backup_auto.ejecutar(db, app.config, LUNES)["ok"] is False
    app.config["BACKUP_DIR"] = str(carpeta)
    assert backup_auto.ejecutar(db, app.config, LUNES + timedelta(minutes=15))["ok"]
    assert configuracion.leer_todo(db)["backup_error_msg"] == ""


def test_si_falla_la_verificacion_no_queda_un_archivo_a_medias(app, db, carpeta, monkeypatch):
    def rota(*a, **k):
        Path(a[2]).write_bytes(b"medio zip")
        raise backup.ErrorDeNegocio("La copia no pasó la verificación.")
    monkeypatch.setattr(backup, "crear_respaldo", rota)
    assert backup_auto.ejecutar(db, app.config, LUNES)["ok"] is False
    assert list(carpeta.iterdir()) == []


def test_una_copia_en_curso_reciente_bloquea_a_otro_proceso_pero_una_vieja_no(app, db, carpeta):
    configuracion.guardar(db, {"backup_en_curso": LUNES.isoformat(timespec="seconds")})
    assert backup_auto.ejecutar(db, app.config, LUNES + timedelta(minutes=5)) is None
    assert backup_auto.ejecutar(db, app.config, LUNES + timedelta(minutes=20))["ok"]       # se colgó: se retoma


# ------------------------------------------------------------------------- avisos
@pytest.mark.parametrize("dias, nivel", [(0, "ok"), (1, "ok"), (3, "ok"), (4, "peligro"), (10, "peligro")])
def test_se_avisa_cuando_hace_mas_de_3_dias(app, db, carpeta, dias, nivel):
    backup_auto.ejecutar(db, app.config, LUNES)
    e = backup_auto.estado(db, app.config, _dias(dias))
    assert e["nivel"] == nivel and e["dias"] == dias
    if nivel == "peligro":
        assert f"Hace {dias} días" in e["mensaje"]


def test_avisa_si_nunca_se_hizo_o_si_no_esta_configurada(app, db, carpeta):
    assert backup_auto.estado(db, app.config, LUNES)["nivel"] == "aviso"
    assert "Todavía no se hizo" in backup_auto.estado(db, app.config, LUNES)["mensaje"]
    app.config["BACKUP_DIR"] = ""
    assert "no está configurada" in backup_auto.estado(db, app.config, LUNES)["mensaje"]


def test_el_estado_muestra_el_error_de_la_ultima_copia(app, db, carpeta, tmp_path):
    backup_auto.ejecutar(db, app.config, LUNES)
    archivo = tmp_path / "f"
    archivo.write_text("x")
    app.config["BACKUP_DIR"] = str(archivo)
    backup_auto.ejecutar(db, app.config, _dias(1))
    e = backup_auto.estado(db, app.config, _dias(1))
    assert e["nivel"] == "aviso" and "falló" in e["mensaje"]


# ------------------------------------------------------------- validar la carpeta
def test_validar_carpeta(tmp_path):
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    assert backup_auto.validar_carpeta("", str(fotos)) == ("", None)
    assert backup_auto.validar_carpeta("copias", str(fotos))[1] and "ruta completa" in backup_auto.validar_carpeta("copias")[1]
    assert "carpeta de fotos" in backup_auto.validar_carpeta(str(fotos / "sub"), str(fotos))[1]
    archivo = tmp_path / "a.txt"
    archivo.write_text("x")
    assert "No se puede guardar" in backup_auto.validar_carpeta(str(archivo))[1]
    ruta, error = backup_auto.validar_carpeta(f"  {tmp_path / 'nueva'}  ", str(fotos))
    assert error is None and ruta == str(tmp_path / "nueva") and (tmp_path / "nueva").is_dir()
    assert list((tmp_path / "nueva").iterdir()) == []                       # no deja el archivo de prueba


# ------------------------------------------------------- pantalla y panel
def test_elegir_la_carpeta_en_configuracion_hace_la_primera_copia(app, nav, tmp_path):
    destino = tmp_path / "drive"
    html = nav.post("/configuracion/", {"gym_nombre": "Gym", "backup_carpeta": str(destino)},
                    follow_redirects=True).get_data(as_text=True)
    assert "Se hizo la copia de seguridad" in html and "Última copia:" in html
    assert app.config["BACKUP_DIR"] == str(destino) and len(_zips(destino)) == 1


def test_una_carpeta_invalida_no_se_guarda(app, nav):
    html = nav.post("/configuracion/", {"gym_nombre": "Gym", "backup_carpeta": "relativa/carpeta"}).get_data(as_text=True)
    assert "ruta completa" in html and app.config["BACKUP_DIR"] == ""


def test_vaciar_la_carpeta_apaga_la_copia_automatica(app, nav, carpeta):
    nav.post("/configuracion/", {"gym_nombre": "Gym", "backup_carpeta": str(carpeta)})
    nav.post("/configuracion/", {"gym_nombre": "Gym", "backup_carpeta": ""})
    assert app.config["BACKUP_DIR"] == ""


def test_el_panel_del_administrador_muestra_la_fecha_de_la_ultima_copia(app, nav, db, carpeta):
    antes = nav.get("/").get_data(as_text=True)
    assert 'id="copia-seguridad"' in antes and "Todavía no se hizo ninguna copia" in antes
    backup_auto.ejecutar(db, app.config, timeutils.ahora())
    html = nav.get("/").get_data(as_text=True)
    assert "Última copia de seguridad:" in html and timeutils.ahora().strftime("%d/%m/%Y") in html
    assert "alert-warning" not in html.split('id="copia-seguridad"')[1]


def test_el_panel_avisa_si_hace_mas_de_3_dias(app, nav, db, carpeta):
    backup_auto.ejecutar(db, app.config, timeutils.ahora() - timedelta(days=4))
    html = nav.get("/").get_data(as_text=True)
    assert "Hace 4 días que no se hace una copia de seguridad" in html and "alert-danger" in html


def test_el_panel_de_recepcion_no_muestra_la_copia(nav_recepcion):
    assert "copia-seguridad" not in nav_recepcion.get("/").get_data(as_text=True)


# ----------------------------------------------------------------------- el hilo
def test_el_ciclo_del_hilo_usa_la_configuracion_guardada_y_hace_la_copia(app, db, tmp_path):
    destino = tmp_path / "desde-la-base"
    configuracion.guardar(db, {"backup_carpeta": str(destino)})
    r = backup_auto.ciclo(app)                                             # app.config todavía no lo sabía
    assert r["ok"] and len(_zips(destino)) == 1
    assert backup_auto.ciclo(app) is None                                  # ya hay una de hoy


def test_el_hilo_no_arranca_en_los_tests_y_arranca_una_sola_vez(app, monkeypatch):
    assert "backup_hilo" not in app.extensions
    llamadas = []
    monkeypatch.setattr(backup_auto, "ciclo", lambda a: llamadas.append(1))
    hilo = backup_auto.iniciar_hilo(app, intervalo=3600, espera_inicial=0)
    assert hilo.daemon and backup_auto.iniciar_hilo(app) is None
    hilo.join(0.5)
    assert llamadas == [1]


def test_un_error_en_una_revision_no_mata_al_hilo(app, monkeypatch):
    import time
    llamadas = []

    def falla(a):
        llamadas.append(1)
        raise RuntimeError("boom")
    monkeypatch.setattr(backup_auto, "ciclo", falla)
    hilo = backup_auto.iniciar_hilo(app, intervalo=0.05, espera_inicial=0)
    time.sleep(0.4)
    assert hilo.is_alive() and len(llamadas) >= 2
