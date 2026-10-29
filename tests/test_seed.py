"""seed.py: datos de ejemplo coherentes, con los ingresos de hoy en horas que ya pasaron."""
import sqlite3
import sys
from datetime import datetime

import pytest

import seed
from app import db as dbm
from app import timeutils
from app.services import dashboard


def _cargar(tmp_path, monkeypatch, hora=None):
    if hora:
        falso = datetime(2026, 10, 25, hora[0], hora[1], tzinfo=timeutils.TZ)
        monkeypatch.setattr(timeutils, "ahora", lambda: falso)
    conn = dbm.connect(str(tmp_path / "seed.db"))
    dbm.init_schema(conn)
    totales = seed.cargar(conn)
    return conn, totales


def test_carga_3_planes_y_30_socios_con_pagos(tmp_path, monkeypatch):
    conn, totales = _cargar(tmp_path, monkeypatch, (12, 0))
    assert totales["planes"] == 3 and totales["socios"] == 30
    assert totales["pagos"] > 30 and totales["asistencias"] > 0
    estados = dict(conn.execute("SELECT estado, COUNT(*) FROM socios GROUP BY estado").fetchall())
    assert estados == {"activo": 27, "pausado": 2, "baja": 1}


def test_las_membresias_quedan_en_distintos_estados(tmp_path, monkeypatch):
    conn, _ = _cargar(tmp_path, monkeypatch, (12, 0))
    r = dashboard.resumen(conn, timeutils.hoy())
    assert r["por_vencer"] == 6 and r["vencidos"] == 6
    sin_plan = conn.execute("SELECT COUNT(*) FROM vista_socios WHERE plan_id IS NULL").fetchone()[0]
    assert sin_plan == 2


@pytest.mark.parametrize("hora", [(9, 15), (0, 10), (6, 0), (23, 59)])
def test_los_ingresos_de_hoy_no_quedan_en_horas_que_todavia_no_pasaron(tmp_path, monkeypatch, hora):
    conn, _ = _cargar(tmp_path, monkeypatch, hora)
    horas = [f[0] for f in conn.execute("SELECT hora FROM asistencias WHERE fecha = ?", (timeutils.hoy().isoformat(),))]
    assert len(horas) == 6
    assert max(horas) <= f"{hora[0]:02d}:{hora[1]:02d}:59"


def test_hay_un_pago_parcial_y_uno_anulado_de_ejemplo(tmp_path, monkeypatch):
    conn, _ = _cargar(tmp_path, monkeypatch, (12, 0))
    anulados = conn.execute("SELECT anulado_motivo, anulado_por FROM pagos WHERE anulado = 1").fetchall()
    assert [tuple(a) for a in anulados] == [("Pago cargado dos veces por error", "ejemplo")]
    assert conn.execute("SELECT COUNT(*) FROM pagos WHERE es_parcial = 1 AND anulado = 0").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM pagos WHERE cargado_por IS NULL").fetchone()[0] == 0


def test_el_pago_anulado_de_ejemplo_no_cambia_los_vencimientos(tmp_path, monkeypatch):
    conn, _ = _cargar(tmp_path, monkeypatch, (12, 0))
    for fila in conn.execute("SELECT id FROM membresias WHERE anulada = 0").fetchall():
        from app.services import payments
        guardado = conn.execute("SELECT fecha_vencimiento FROM membresias WHERE id = ?", (fila[0],)).fetchone()[0]
        assert payments.reproducir(conn, fila[0]).vencimiento.isoformat() == guardado


def test_la_base_pasa_la_verificacion_de_integridad(tmp_path, monkeypatch):
    conn, _ = _cargar(tmp_path, monkeypatch, (12, 0))
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_el_script_se_niega_a_pisar_una_base_con_datos(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GYM_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setattr(sys, "argv", ["seed.py"])
    assert seed.main() == 0
    assert seed.main() == 1
    assert "--reset" in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", ["seed.py", "--reset"])
    assert seed.main() == 0
