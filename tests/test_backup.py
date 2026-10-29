"""Copia de seguridad descargable y script backup.py."""
import io
import sqlite3
import zipfile
from pathlib import Path

import pytest

import backup as script            # backup.py de la raíz del proyecto
from app.services import backup
from app.services.errors import ErrorDeNegocio


@pytest.fixture
def con_datos(app, db, crear_socio):
    crear_socio(nombre="Ana Paz", dni="30000001")
    crear_socio(nombre="Beto Gil", dni="30000002")
    fotos = Path(app.config["UPLOAD_DIR"])
    fotos.mkdir(parents=True, exist_ok=True)
    (fotos / "aaa.jpg").write_bytes(b"\xff\xd8\xff-foto-a")
    (fotos / "bbb.png").write_bytes(b"\x89PNG-foto-b")
    return app


def _abrir_db_del_zip(contenido: zipfile.ZipFile, tmp_path) -> sqlite3.Connection:
    contenido.extract("gimnasio.db", tmp_path)
    return sqlite3.connect(tmp_path / "gimnasio.db")


def test_el_respaldo_trae_la_base_las_fotos_y_las_instrucciones(con_datos, tmp_path):
    cfg = con_datos.config
    salida = io.BytesIO()

    fotos = backup.crear_respaldo(cfg["DATABASE"], cfg["UPLOAD_DIR"], salida)

    assert fotos == 2
    z = zipfile.ZipFile(salida)
    assert sorted(z.namelist()) == ["LEEME.txt", "fotos/aaa.jpg", "fotos/bbb.png", "gimnasio.db"]
    assert z.read("fotos/aaa.jpg") == b"\xff\xd8\xff-foto-a"
    assert "Cómo restaurarla" in z.read("LEEME.txt").decode("utf-8")
    copia = _abrir_db_del_zip(z, tmp_path)
    assert copia.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 2
    assert copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    copia.close()


def test_el_respaldo_incluye_lo_que_todavia_esta_en_el_wal(con_datos, db, tmp_path):
    # la base está en modo WAL: lo recién guardado puede no estar aún en el archivo .db principal
    with db:
        db.execute("INSERT INTO planes (nombre, precio_centavos, duracion_dias) VALUES ('Recién creado', 100, 30)")
    salida = io.BytesIO()
    backup.crear_respaldo(con_datos.config["DATABASE"], con_datos.config["UPLOAD_DIR"], salida)
    copia = _abrir_db_del_zip(zipfile.ZipFile(salida), tmp_path)
    assert copia.execute("SELECT COUNT(*) FROM planes WHERE nombre = 'Recién creado'").fetchone()[0] == 1
    copia.close()


def test_el_respaldo_no_modifica_la_base_original(con_datos):
    cfg = con_datos.config
    antes = Path(cfg["DATABASE"]).stat().st_size
    backup.crear_respaldo(cfg["DATABASE"], cfg["UPLOAD_DIR"], io.BytesIO())
    conn = sqlite3.connect(cfg["DATABASE"])
    assert conn.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 2
    conn.close()
    assert Path(cfg["DATABASE"]).stat().st_size >= antes


def test_sin_carpeta_de_fotos_igual_hace_el_respaldo(app, tmp_path):
    salida = io.BytesIO()
    assert backup.crear_respaldo(app.config["DATABASE"], str(tmp_path / "no-existe"), salida) == 0
    assert "gimnasio.db" in zipfile.ZipFile(salida).namelist()


def test_si_no_existe_la_base_avisa(tmp_path):
    with pytest.raises(ErrorDeNegocio, match="No encontramos la base de datos"):
        backup.crear_respaldo(str(tmp_path / "nada.db"), str(tmp_path), io.BytesIO())


def test_nombre_del_archivo_lleva_fecha_y_hora():
    from datetime import datetime
    from app.timeutils import TZ
    nombre = backup.nombre_de_archivo(datetime(2026, 10, 25, 23, 5, 9, tzinfo=TZ))
    assert nombre == "copia-seguridad_2026-10-25_230509.zip"


# ------------------------------------------------------------------------ pantalla
def test_el_administrador_descarga_la_copia(nav, con_datos, tmp_path):
    r = nav.post("/datos/respaldo/")

    assert r.status_code == 200
    assert r.mimetype == "application/zip"
    assert "attachment" in r.headers["Content-Disposition"] and "copia-seguridad_" in r.headers["Content-Disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.get_data()))
    assert {"gimnasio.db", "fotos/aaa.jpg"} <= set(z.namelist())


def test_la_pagina_de_datos_ofrece_el_boton(nav):
    html = nav.get("/exportar/").get_data(as_text=True)
    assert "Descargar copia de seguridad" in html and "Importar socios desde CSV" in html


def test_recepcion_no_puede_descargar_la_copia(nav_recepcion, con_datos):
    assert nav_recepcion.post("/datos/respaldo/").status_code == 403


def test_sin_sesion_no_se_descarga_nada(anonimo):
    r = anonimo.post("/datos/respaldo/")
    assert r.status_code in (302, 400) and r.mimetype != "application/zip"


def test_la_descarga_exige_post_con_token(nav, con_datos):
    assert nav.get("/datos/respaldo/").status_code == 405
    assert nav.client.post("/datos/respaldo/", data={}).status_code == 400   # sin token CSRF


# --------------------------------------------------------------------- backup.py
@pytest.fixture
def entorno(con_datos, db, monkeypatch):
    db.close()   # como si el sistema estuviera apagado
    monkeypatch.setenv("GYM_DB_PATH", con_datos.config["DATABASE"])
    monkeypatch.setenv("GYM_UPLOAD_DIR", con_datos.config["UPLOAD_DIR"])


def test_el_script_genera_el_zip_en_la_carpeta_pedida(entorno, tmp_path, capsys):
    destino = tmp_path / "respaldos"

    assert script.main(["--destino", str(destino)]) == 0

    zips = list(destino.glob("copia-seguridad_*.zip"))
    assert len(zips) == 1
    z = zipfile.ZipFile(zips[0])
    assert "gimnasio.db" in z.namelist() and "fotos/bbb.png" in z.namelist()
    assert "Copia de seguridad lista" in capsys.readouterr().out


def test_el_script_conserva_solo_los_ultimos(entorno, tmp_path):
    destino = tmp_path / "respaldos"
    destino.mkdir()
    for dia in ("2026-10-01", "2026-10-02", "2026-10-03"):
        (destino / f"copia-seguridad_{dia}_230000.zip").write_bytes(b"viejo")
    (destino / "otro-archivo.zip").write_bytes(b"no es un respaldo")

    assert script.main(["--destino", str(destino), "--conservar", "2"]) == 0

    nombres = sorted(p.name for p in destino.iterdir())
    assert "otro-archivo.zip" in nombres                      # no toca lo que no es un respaldo
    respaldos = [n for n in nombres if n.startswith("copia-seguridad_")]
    assert len(respaldos) == 2
    assert "copia-seguridad_2026-10-01_230000.zip" not in respaldos and "copia-seguridad_2026-10-02_230000.zip" not in respaldos


def test_conservar_cero_no_borra_nada(entorno, tmp_path):
    destino = tmp_path / "r"
    destino.mkdir()
    for dia in ("01", "02", "03"):
        (destino / f"copia-seguridad_2026-10-{dia}_230000.zip").write_bytes(b"x")
    assert script.main(["--destino", str(destino), "--conservar", "0"]) == 0
    assert len(list(destino.glob("copia-seguridad_*.zip"))) == 4


def test_el_script_falla_con_codigo_1_si_no_hay_base(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GYM_DB_PATH", str(tmp_path / "no-hay.db"))
    monkeypatch.setenv("GYM_UPLOAD_DIR", str(tmp_path / "fotos"))
    destino = tmp_path / "r"

    assert script.main(["--destino", str(destino)]) == 1

    assert "No se pudo generar la copia de seguridad" in capsys.readouterr().err
    assert list(destino.glob("*.zip")) == []                  # no deja un zip a medias
