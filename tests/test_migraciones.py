"""Una base creada con la primera versión se actualiza sin perder datos."""
import sqlite3
from pathlib import Path

import pytest

from app import db as dbm
from app import migraciones
from app.services import payments

SCHEMA_V1 = Path(dbm.SCHEMA)


@pytest.fixture
def base_vieja(tmp_path):
    """Base como la dejaba la primera versión del sistema (solo schema.sql), con datos reales adentro."""
    conn = sqlite3.connect(tmp_path / "vieja.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_V1.read_text(encoding="utf-8"))
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    conn.executescript("""
        INSERT INTO planes (id, nombre, precio_centavos, duracion_dias, clases_por_semana) VALUES (1, 'Mensual', 2500000, 30, NULL);
        INSERT INTO socios (id, nombre, dni, telefono, fecha_alta, estado, creado_en)
            VALUES (1, 'Ana Paz', '30111222', '11 5555-1234', '2026-10-01', 'activo', 'x');
        INSERT INTO membresias (id, socio_id, plan_id, fecha_inicio, fecha_vencimiento, creada_en)
            VALUES (1, 1, 1, '2026-10-01', '2026-10-31', 'x');
        INSERT INTO pagos (id, socio_id, membresia_id, monto_centavos, fecha, metodo, vencimiento_anterior, vencimiento_nuevo, creado_en)
            VALUES (1, 1, 1, 2500000, '2026-10-01', 'efectivo', '2026-10-31', '2026-10-31', 'x');
        INSERT INTO asistencias (id, socio_id, fecha, hora) VALUES (7, 1, '2026-10-05', '18:30:00');
    """)
    conn.commit()
    return conn


def test_la_base_vieja_llega_a_la_version_actual_conservando_todo(base_vieja):
    dbm.init_schema(base_vieja)

    assert base_vieja.execute("PRAGMA user_version").fetchone()[0] == migraciones.VERSION_ACTUAL
    assert base_vieja.execute("SELECT nombre, dni FROM socios").fetchone()[:] == ("Ana Paz", "30111222")
    pago = base_vieja.execute("SELECT * FROM pagos WHERE id = 1").fetchone()
    assert pago["monto_centavos"] == 2500000 and pago["vencimiento_nuevo"] == "2026-10-31"
    assert pago["anulado"] == 0 and pago["es_parcial"] == 0 and pago["cargado_por"] is None
    asistencia = base_vieja.execute("SELECT * FROM asistencias").fetchone()
    assert asistencia["id"] == 7 and asistencia["fecha"] == "2026-10-05" and asistencia["registrado_por"] is None
    assert base_vieja.execute("PRAGMA foreign_key_check").fetchall() == []
    assert base_vieja.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_las_membresias_viejas_guardan_la_duracion_y_el_precio_del_plan(base_vieja):
    dbm.init_schema(base_vieja)
    m = base_vieja.execute("SELECT * FROM membresias WHERE id = 1").fetchone()
    assert m["duracion_dias"] == 30 and m["precio_centavos"] == 2500000
    assert m["dias_extra"] == 0 and m["anulada"] == 0
    # editar el plan después no cambia lo ya vendido
    base_vieja.execute("UPDATE planes SET precio_centavos = 9900000, duracion_dias = 7")
    assert payments.reproducir(base_vieja, 1).vencimiento.isoformat() == "2026-10-31"


def test_el_vencimiento_recalculado_coincide_con_el_que_ya_estaba_guardado(base_vieja):
    dbm.init_schema(base_vieja)
    estado = payments.recalcular_membresia(base_vieja, 1)
    assert estado.vencimiento.isoformat() == "2026-10-31" and estado.saldo_pendiente_centavos == 0


def test_la_vista_de_socios_sigue_funcionando_y_hay_planes_activos(base_vieja):
    dbm.init_schema(base_vieja)
    socio = base_vieja.execute("SELECT * FROM vista_socios WHERE id = 1").fetchone()
    assert socio["plan_nombre"] == "Mensual" and socio["fecha_vencimiento"] == "2026-10-31" and socio["dias_extra"] == 0
    assert base_vieja.execute("SELECT activo FROM planes").fetchone()[0] == 1


def test_despues_de_migrar_se_permite_mas_de_un_ingreso_por_dia(base_vieja):
    dbm.init_schema(base_vieja)
    for hora in ("09:00:00", "18:00:00"):
        base_vieja.execute("INSERT INTO asistencias (socio_id, fecha, hora) VALUES (1, '2026-10-06', ?)", (hora,))
    assert base_vieja.execute("SELECT COUNT(*) FROM asistencias WHERE fecha = '2026-10-06'").fetchone()[0] == 2


def test_las_tablas_de_la_tienda_existen(base_vieja):
    dbm.init_schema(base_vieja)
    tablas = {r[0] for r in base_vieja.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"productos", "ventas", "venta_items", "movimientos_stock"} <= tablas


def test_correr_la_migracion_dos_veces_no_rompe_nada(base_vieja):
    dbm.init_schema(base_vieja)
    dbm.init_schema(base_vieja)
    assert base_vieja.execute("SELECT COUNT(*) FROM pagos").fetchone()[0] == 1
    assert base_vieja.execute("PRAGMA user_version").fetchone()[0] == migraciones.VERSION_ACTUAL


def test_una_base_nueva_arranca_directo_en_la_version_actual(tmp_path):
    conn = dbm.connect(str(tmp_path / "nueva.db"))
    dbm.init_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == migraciones.VERSION_ACTUAL


def test_una_migracion_que_falla_no_deja_la_base_a_medias(base_vieja, monkeypatch):
    dbm.init_schema(base_vieja)
    version = migraciones.VERSION_ACTUAL
    rota = "BEGIN; ALTER TABLE planes ADD COLUMN columna_nueva TEXT; SELECT * FROM tabla_que_no_existe; COMMIT;"
    monkeypatch.setattr(migraciones, "MIGRACIONES", migraciones.MIGRACIONES + [(version + 1, rota)])

    with pytest.raises(sqlite3.Error):
        migraciones.aplicar(base_vieja)

    assert base_vieja.execute("PRAGMA user_version").fetchone()[0] == version
    columnas = [r[1] for r in base_vieja.execute("PRAGMA table_info(planes)")]
    assert "columna_nueva" not in columnas                       # se deshizo
    assert base_vieja.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 1


def test_de_la_version_4_a_la_5_no_se_pierde_nada_y_aparecen_usuarios_e_importaciones(base_vieja, monkeypatch):
    todas = [m for m in migraciones.MIGRACIONES if m[0] <= 5]          # solo hasta la 5 (la 6 es de pagos por períodos)
    monkeypatch.setattr(migraciones, "MIGRACIONES", [m for m in todas if m[0] <= 4])
    dbm.init_schema(base_vieja)
    assert base_vieja.execute("PRAGMA user_version").fetchone()[0] == 4
    base_vieja.execute("INSERT INTO productos (nombre, precio_centavos, stock, creado_en) VALUES ('Whey', 4500000, 7, 'x')")
    base_vieja.execute("INSERT INTO ventas (fecha, hora, metodo, total_centavos, cargada_por, creada_en) VALUES ('2026-10-05', '10:00:00', 'efectivo', 4500000, 'recepcion', 'x')")
    base_vieja.commit()

    monkeypatch.setattr(migraciones, "MIGRACIONES", todas)
    dbm.init_schema(base_vieja)

    assert base_vieja.execute("PRAGMA user_version").fetchone()[0] == 5
    assert base_vieja.execute("SELECT stock FROM productos").fetchone()[0] == 7
    assert base_vieja.execute("SELECT cargada_por FROM ventas").fetchone()[0] == "recepcion"      # el nombre viejo se conserva
    assert base_vieja.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0
    assert base_vieja.execute("SELECT COUNT(*) FROM importaciones").fetchone()[0] == 0
    assert base_vieja.execute("SELECT nombre FROM socios").fetchone()[0] == "Ana Paz"
    base_vieja.execute("INSERT INTO usuarios (usuario, clave_hash, creado_en) VALUES ('Ana', 'h', 'x')")
    with pytest.raises(sqlite3.IntegrityError):                                                    # único sin importar mayúsculas
        base_vieja.execute("INSERT INTO usuarios (usuario, clave_hash, creado_en) VALUES ('ANA', 'h', 'x')")


def test_de_la_version_4_a_la_ultima_conviven_usuarios_y_pagos_por_periodos(base_vieja, monkeypatch):
    """Unión de las ramas: la V5 (usuarios, importaciones) y la V6 (descuento anual) se aplican seguidas sin perder datos."""
    todas = list(migraciones.MIGRACIONES)
    monkeypatch.setattr(migraciones, "MIGRACIONES", [m for m in todas if m[0] <= 4])
    dbm.init_schema(base_vieja)
    base_vieja.execute("INSERT INTO productos (nombre, precio_centavos, stock, creado_en) VALUES ('Whey', 4500000, 7, 'x')")
    base_vieja.commit()

    monkeypatch.setattr(migraciones, "MIGRACIONES", todas)
    dbm.init_schema(base_vieja)

    assert [n for n, _ in todas] == [2, 3, 4, 5, 6]
    assert base_vieja.execute("PRAGMA user_version").fetchone()[0] == 6 == migraciones.VERSION_ACTUAL
    assert base_vieja.execute("SELECT stock FROM productos").fetchone()[0] == 7
    assert base_vieja.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0
    assert "descuento_anual_tipo" in [r[1] for r in base_vieja.execute("PRAGMA table_info(planes)")]
    assert "descuento_centavos" in [r[1] for r in base_vieja.execute("PRAGMA table_info(pagos)")]
    assert base_vieja.execute("SELECT valor FROM configuracion LIMIT 1").fetchone() is None
