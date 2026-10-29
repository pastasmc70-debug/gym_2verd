"""«Adentro ahora (aprox.)»: socios con un ingreso en las últimas N horas. No se registra la salida."""
from datetime import datetime

import pytest

from app import timeutils
from app.config import ErrorDeConfiguracion, config_desde_entorno, validar_config
from app.services import dashboard
from conftest import Navegador

AHORA = datetime(2026, 10, 25, 15, 0, 0, tzinfo=timeutils.TZ)


def _ingreso(db, socio_id, fecha, hora):
    with db:
        db.execute("INSERT INTO asistencias (socio_id, fecha, hora, registrado_por) VALUES (?, ?, ?, 'recepcion')",
                   (socio_id, fecha, hora))


def _nombres(db, ahora=AHORA, horas=2):
    return [f["nombre"] for f in dashboard.adentro_ahora(db, ahora, horas)]


@pytest.fixture
def socio(crear_socio):
    return lambda nombre: crear_socio(nombre=nombre)


# ----------------------------------------------------------------- horarios límite
@pytest.mark.parametrize("hora,adentro", [
    ("15:00:00", True),      # justo ahora
    ("14:00:00", True),      # hace 1 h
    ("13:00:01", True),      # a 1 segundo de cumplir las 2 h
    ("13:00:00", True),      # exactamente 2 h: se incluye
    ("12:59:59", False),     # 1 segundo más de 2 h: ya no
    ("08:00:00", False),
    ("15:00:01", False),     # en el futuro (no debería existir): no se cuenta
])
def test_limites_de_la_ventana_de_dos_horas(db, socio, hora, adentro):
    _ingreso(db, socio("Ana Paz"), "2026-10-25", hora)
    assert (_nombres(db) == ["Ana Paz"]) is adentro


@pytest.mark.parametrize("horas,esperados", [(1, ["Cerca"]), (2, ["Cerca", "Medio"]), (3, ["Cerca", "Medio", "Lejos"]),
                                             (12, ["Cerca", "Medio", "Lejos"])])
def test_la_cantidad_de_horas_es_configurable(db, socio, horas, esperados):
    _ingreso(db, socio("Cerca"), "2026-10-25", "14:30:00")      # hace 30 min
    _ingreso(db, socio("Medio"), "2026-10-25", "13:30:00")      # hace 1 h 30
    _ingreso(db, socio("Lejos"), "2026-10-25", "12:30:00")      # hace 2 h 30
    assert _nombres(db, horas=horas) == esperados


def test_cruza_la_medianoche(db, socio):
    ahora = datetime(2026, 10, 26, 0, 30, 0, tzinfo=timeutils.TZ)
    _ingreso(db, socio("Noche Tarde"), "2026-10-25", "23:30:00")     # hace 1 h, el día anterior
    _ingreso(db, socio("Noche Justo"), "2026-10-25", "22:30:00")     # exactamente 2 h
    _ingreso(db, socio("Noche Antes"), "2026-10-25", "22:29:59")     # 2 h y 1 s
    _ingreso(db, socio("Madrugada"), "2026-10-26", "00:10:00")
    assert _nombres(db, ahora) == ["Madrugada", "Noche Tarde", "Noche Justo"]


def test_ingresos_de_otros_dias_no_cuentan(db, socio):
    _ingreso(db, socio("Ayer"), "2026-10-24", "14:30:00")
    assert _nombres(db) == []


# ------------------------------------------------------------ sin duplicar al mismo socio
def test_un_socio_que_ingreso_varias_veces_cuenta_una_sola_vez_con_su_ultimo_ingreso(db, socio):
    ana = socio("Ana Paz")
    for hora in ("13:30:00", "14:15:00", "14:45:00"):
        _ingreso(db, ana, "2026-10-25", hora)
    resultado = dashboard.adentro_ahora(db, AHORA, 2)
    assert len(resultado) == 1 and resultado[0]["hora"] == "14:45"


def test_orden_del_mas_reciente_al_mas_antiguo_y_sin_datos_privados(db, socio):
    _ingreso(db, socio("Primero"), "2026-10-25", "13:30:00")
    _ingreso(db, socio("Segundo"), "2026-10-25", "14:30:00")
    resultado = dashboard.adentro_ahora(db, AHORA, 2)
    assert [f["nombre"] for f in resultado] == ["Segundo", "Primero"]
    assert set(resultado[0]) == {"socio_id", "nombre", "hora", "ingreso"}        # nada de teléfono, email ni deudas


def test_sin_ingresos_la_lista_esta_vacia(db):
    assert dashboard.adentro_ahora(db, AHORA, 2) == []


# ------------------------------------------------------------------------- panel
def test_el_panel_dice_aprox_y_que_no_se_registra_la_salida(nav):
    html = nav.get("/").get_data(as_text=True)
    assert "Adentro ahora (aprox.)" in html and "No se registra la salida" in html
    assert "No hay ingresos en las últimas 2 horas" in html


def test_el_panel_lista_a_quien_acaba_de_ingresar(nav, db, plan, crear_socio, app):
    app.config["ACCESO_SIN_PAGO"] = True
    from app.services import memberships
    from conftest import hoy_real
    socio_id = crear_socio(nombre="Lucía Gómez", dni="41222333")
    memberships.asignar_plan(db, socio_id, plan, hoy_real())
    nav.post("/asistencia/ingreso", {"q": "41222333"})

    html = nav.get("/").get_data(as_text=True)
    bloque = html[html.index('id="adentro-ahora"'):]
    assert "Lucía Gómez" in bloque and "Adentro ahora (aprox.): <span class=\"fw-bold\">1</span>" in bloque
    assert "41222333" not in bloque and "11 5555" not in bloque


def test_un_ingreso_viejo_no_aparece_en_el_panel(nav, db, socio):
    _ingreso(db, socio("De Ayer"), "2026-01-01", "10:00:00")
    assert "De Ayer" not in nav.get("/").get_data(as_text=True)


def test_el_panel_muestra_hora_en_singular_con_una_hora(nav, app):
    app.config["HORAS_ADENTRO"] = 1
    html = nav.get("/").get_data(as_text=True)
    assert "últimas 1 hora." in html and "últimas 1 horas" not in html


def test_recepcion_tambien_ve_el_bloque(nav_recepcion):
    assert "Adentro ahora (aprox.)" in nav_recepcion.get("/").get_data(as_text=True)


# ------------------------------------------------------------------ configuración
def _guardar(nav, **extra):
    datos = {"gym_nombre": "Mi Gimnasio"}
    datos.update(extra)
    return nav.post("/configuracion/", datos)


def test_por_defecto_son_dos_horas(app):
    assert app.config["HORAS_ADENTRO"] == 2


def test_el_administrador_cambia_las_horas_desde_configuracion_y_persiste(nav, app, db):
    r = _guardar(nav, horas_adentro="3")
    assert r.status_code == 302 and app.config["HORAS_ADENTRO"] == 3
    assert db.execute("SELECT valor FROM configuracion WHERE clave = 'horas_adentro'").fetchone()[0] == "3"
    assert "últimas 3 horas" in nav.get("/").get_data(as_text=True)
    assert 'name="horas_adentro"' in nav.get("/configuracion/").get_data(as_text=True)
    assert 'value="3"' in nav.get("/configuracion/").get_data(as_text=True)


def test_un_cambio_hecho_en_otro_proceso_se_toma_en_el_siguiente_pedido(nav, app, db):
    with db:
        db.execute("INSERT INTO configuracion (clave, valor, actualizada_en) VALUES ('horas_adentro', '5', 'x')")
    assert "últimas 5 horas" in nav.get("/").get_data(as_text=True)


@pytest.mark.parametrize("valor", ["0", "13", "-1", "abc", "", "2.5", "  "])
def test_valores_invalidos_de_horas_se_rechazan_y_no_se_guardan(nav, app, db, valor):
    r = _guardar(nav, horas_adentro=valor)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "entre 1 y 12" in html and "Revisá los campos" in html
    assert app.config["HORAS_ADENTRO"] == 2
    assert db.execute("SELECT COUNT(*) FROM configuracion WHERE clave = 'horas_adentro'").fetchone()[0] == 0


@pytest.mark.parametrize("valor", ["1", "12"])
def test_los_extremos_validos_se_aceptan(nav, app, valor):
    assert _guardar(nav, horas_adentro=valor).status_code == 302 and app.config["HORAS_ADENTRO"] == int(valor)


def test_si_el_formulario_no_trae_las_horas_no_las_cambia(nav, app):
    _guardar(nav, horas_adentro="4")
    assert _guardar(nav).status_code == 302 and app.config["HORAS_ADENTRO"] == 4


def test_recepcion_no_puede_cambiar_las_horas(nav_recepcion, app):
    assert _guardar(nav_recepcion, horas_adentro="9").status_code == 403 and app.config["HORAS_ADENTRO"] == 2


def test_variable_de_entorno_como_alternativa_y_validacion(monkeypatch, tmp_path):
    monkeypatch.delenv("GYM_HORAS_ADENTRO", raising=False)
    assert config_desde_entorno(str(tmp_path))["HORAS_ADENTRO"] == 2
    monkeypatch.setenv("GYM_HORAS_ADENTRO", "4")
    cfg = config_desde_entorno(str(tmp_path))
    assert cfg["HORAS_ADENTRO"] == 4
    for malo in (0, 13):
        with pytest.raises(ErrorDeConfiguracion, match="entre 1 y 12"):
            validar_config(dict(cfg, HORAS_ADENTRO=malo))
    monkeypatch.setenv("GYM_HORAS_ADENTRO", "mucho")
    with pytest.raises(ErrorDeConfiguracion, match="número entero"):
        config_desde_entorno(str(tmp_path))
