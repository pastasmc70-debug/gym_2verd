"""Reglas configurables del ingreso: pago previo, reingreso del mismo día y clases por semana."""
from datetime import date, timedelta

import pytest

from app import config as cfg_mod
from app import models
from app.services import attendance, memberships, payments
from app.services.attendance import ReglasIngreso
from app.services.errors import ErrorDeNegocio
from conftest import HOY, hoy_real

PRECIO = 2500000
SIN_PAGO_OK = ReglasIngreso(acceso_sin_pago=True)
LUNES = date(2026, 10, 19)      # HOY (25/10/2026) es domingo: la semana va del 19 al 25


def _ingresos(db, socio_id):
    return db.execute("SELECT COUNT(*) FROM asistencias WHERE socio_id = ?", (socio_id,)).fetchone()[0]


@pytest.fixture
def plan_de(db):
    def _crear(clases, nombre="Plan"):
        with db:
            return models.crear_plan(db, dict(nombre=nombre, precio_centavos=PRECIO, duracion_dias=30,
                                              clases_por_semana=clases))
    return _crear


@pytest.fixture
def socio_en(db, crear_socio):
    def _crear(plan_id, nombre="Ana Paz"):
        socio_id = crear_socio(nombre=nombre)
        memberships.asignar_plan(db, socio_id, plan_id, HOY - timedelta(days=10))
        return socio_id
    return _crear


# ------------------------------------------------------------- 3. acceso sin pago
def test_por_defecto_un_plan_sin_ningun_pago_no_habilita_el_ingreso(db, socio_con_plan):
    socio_id = socio_con_plan(20)
    with pytest.raises(ErrorDeNegocio) as e:
        attendance.registrar_ingreso(db, socio_id, hoy=HOY)
    assert e.value.codigo == "sin_pago"
    assert "todavía no registra ningún pago" in str(e.value) and "Registrá el pago" in str(e.value)
    assert _ingresos(db, socio_id) == 0


def test_con_un_pago_registrado_puede_ingresar(db, socio_con_plan):
    socio_id = socio_con_plan(20)
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    assert attendance.registrar_ingreso(db, socio_id, hoy=HOY)["estado"] == models.VIGENTE


def test_se_puede_permitir_el_acceso_sin_pago(db, socio_con_plan):
    socio_id = socio_con_plan(20)
    attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=SIN_PAGO_OK)
    assert _ingresos(db, socio_id) == 1


def test_si_anulan_el_unico_pago_vuelve_a_quedar_sin_acceso(db, socio_con_plan):
    socio_id = socio_con_plan(20)
    pago = payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")["pago_id"]
    payments.anular_pago(db, pago, "error", "admin")
    with pytest.raises(ErrorDeNegocio, match="ningún pago"):
        attendance.registrar_ingreso(db, socio_id, hoy=HOY)


def test_los_dias_acumulados_de_una_membresia_paga_no_exigen_otro_pago(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY - timedelta(days=10))
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    memberships.asignar_plan(db, socio_id, plan, HOY, acumular=True)        # plan nuevo, todavía sin pagar
    assert attendance.registrar_ingreso(db, socio_id, hoy=HOY)["socio"]["dias_extra"] == 20


def test_la_vencida_se_rechaza_por_vencida_antes_que_por_falta_de_pago(db, socio_con_plan):
    socio_id = socio_con_plan(-3)
    with pytest.raises(ErrorDeNegocio) as e:
        attendance.registrar_ingreso(db, socio_id, hoy=HOY)
    assert e.value.codigo == "vencida"


# ---------------------------------------------------------------- 4. reingreso
def test_por_defecto_se_rechaza_el_segundo_ingreso_del_dia(db, socio_con_plan):
    socio_id = socio_con_plan(20)
    attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=SIN_PAGO_OK)
    with pytest.raises(ErrorDeNegocio) as e:
        attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=SIN_PAGO_OK)
    assert e.value.codigo == "reingreso" and "ya registró su ingreso hoy" in str(e.value)
    assert _ingresos(db, socio_id) == 1


def test_con_reingreso_permitido_se_registra_el_segundo(db, socio_con_plan):
    reglas = ReglasIngreso(acceso_sin_pago=True, permitir_reingreso=True)
    socio_id = socio_con_plan(20)
    primero = attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=reglas)
    segundo = attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=reglas)
    assert primero["reingreso"] is False and segundo["reingreso"] is True
    assert _ingresos(db, socio_id) == 2


def test_el_panel_cuenta_personas_no_ingresos(db, socio_con_plan):
    from app.services import dashboard
    reglas = ReglasIngreso(acceso_sin_pago=True, permitir_reingreso=True)
    socio_id = socio_con_plan(20)
    attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=reglas)
    attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=reglas)
    assert dashboard.resumen(db, HOY)["asistencias_hoy"] == 1


# ------------------------------------------------------------ 5. clases por semana
def test_se_rechaza_el_ingreso_cuando_se_agotaron_las_clases_de_la_semana(db, plan_de, socio_en):
    socio_id = socio_en(plan_de(2))
    attendance.registrar_ingreso(db, socio_id, hoy=LUNES, reglas=SIN_PAGO_OK)
    attendance.registrar_ingreso(db, socio_id, hoy=LUNES + timedelta(days=2), reglas=SIN_PAGO_OK)

    with pytest.raises(ErrorDeNegocio) as e:
        attendance.registrar_ingreso(db, socio_id, hoy=LUNES + timedelta(days=4), reglas=SIN_PAGO_OK)

    assert e.value.codigo == "limite_clases"
    assert "ya usó las 2 clases por semana de su plan" in str(e.value)
    assert "de lunes a domingo" in str(e.value)
    assert _ingresos(db, socio_id) == 2


def test_avisa_en_cada_ingreso_cuantas_clases_lleva(db, plan_de, socio_en):
    socio_id = socio_en(plan_de(2))
    primero = attendance.registrar_ingreso(db, socio_id, hoy=LUNES, reglas=SIN_PAGO_OK)
    ultimo = attendance.registrar_ingreso(db, socio_id, hoy=LUNES + timedelta(days=1), reglas=SIN_PAGO_OK)
    assert primero["aviso_clases"] == "Clase 1 de 2 de la semana."
    assert ultimo["aviso_clases"] == "Esta fue su última clase de la semana (2 de 2)."


def test_la_semana_nueva_empieza_el_lunes(db, plan_de, socio_en):
    socio_id = socio_en(plan_de(1))
    domingo = LUNES + timedelta(days=6)
    attendance.registrar_ingreso(db, socio_id, hoy=domingo, reglas=SIN_PAGO_OK)
    with pytest.raises(ErrorDeNegocio, match="clases por semana"):
        attendance.registrar_ingreso(db, socio_id, hoy=domingo - timedelta(days=1), reglas=SIN_PAGO_OK)   # sábado, misma semana
    attendance.registrar_ingreso(db, socio_id, hoy=domingo + timedelta(days=1), reglas=SIN_PAGO_OK)       # lunes: semana nueva
    assert _ingresos(db, socio_id) == 2


def test_se_puede_desactivar_el_limite_por_configuracion(db, plan_de, socio_en):
    reglas = ReglasIngreso(acceso_sin_pago=True, limitar_clases=False)
    socio_id = socio_en(plan_de(1))
    for dia in range(3):
        r = attendance.registrar_ingreso(db, socio_id, hoy=LUNES + timedelta(days=dia), reglas=reglas)
    assert _ingresos(db, socio_id) == 3 and r["aviso_clases"] is None


def test_un_plan_ilimitado_no_tiene_limite(db, plan_de, socio_en):
    socio_id = socio_en(plan_de(None))
    for dia in range(6):
        attendance.registrar_ingreso(db, socio_id, hoy=LUNES + timedelta(days=dia), reglas=SIN_PAGO_OK)
    assert _ingresos(db, socio_id) == 6


def test_el_reingreso_del_mismo_dia_no_gasta_otra_clase(db, plan_de, socio_en):
    reglas = ReglasIngreso(acceso_sin_pago=True, permitir_reingreso=True)
    socio_id = socio_en(plan_de(1))
    attendance.registrar_ingreso(db, socio_id, hoy=LUNES, reglas=reglas)
    r = attendance.registrar_ingreso(db, socio_id, hoy=LUNES, reglas=reglas)   # vuelve el mismo día: no se rechaza
    assert r["reingreso"] is True and r["aviso_clases"] is None
    assert attendance.clases_usadas_en_la_semana(db, socio_id, LUNES) == 1


def test_inicio_de_semana():
    assert attendance.inicio_de_semana(date(2026, 10, 25)) == date(2026, 10, 19)   # domingo
    assert attendance.inicio_de_semana(date(2026, 10, 19)) == date(2026, 10, 19)   # lunes
    assert attendance.inicio_de_semana(date(2026, 10, 21)) == date(2026, 10, 19)   # miércoles


# ------------------------------------------------- configuración por variables de entorno
@pytest.mark.parametrize("valor,esperado", [("1", True), ("sí", True), ("si", True), ("TRUE", True), ("on", True),
                                            ("0", False), ("no", False), ("False", False), ("off", False)])
def test_las_variables_de_entorno_aceptan_si_y_no(monkeypatch, valor, esperado):
    monkeypatch.setenv("GYM_ACCESO_SIN_PAGO", valor)
    monkeypatch.setenv("GYM_PERMITIR_REINGRESO", valor)
    cfg = cfg_mod.config_desde_entorno("/tmp/instancia")
    assert cfg["ACCESO_SIN_PAGO"] is esperado and cfg["PERMITIR_REINGRESO"] is esperado


def test_valores_por_defecto_de_la_configuracion(monkeypatch):
    for nombre in ("GYM_ACCESO_SIN_PAGO", "GYM_PERMITIR_REINGRESO", "GYM_LIMITAR_CLASES_SEMANA", "GYM_MODULO_TIENDA"):
        monkeypatch.delenv(nombre, raising=False)
    cfg = cfg_mod.config_desde_entorno("/tmp/instancia")
    assert cfg["ACCESO_SIN_PAGO"] is False        # por defecto: sin pago no se entra
    assert cfg["PERMITIR_REINGRESO"] is False
    assert cfg["LIMITAR_CLASES_SEMANA"] is True
    assert cfg["MODULO_TIENDA"] is False


def test_un_valor_raro_en_la_configuracion_se_informa(monkeypatch):
    monkeypatch.setenv("GYM_ACCESO_SIN_PAGO", "quizás")
    with pytest.raises(cfg_mod.ErrorDeConfiguracion, match="usá 1 o 0"):
        cfg_mod.config_desde_entorno("/tmp/instancia")


# -------------------------------------------------------------------------- pantalla
def test_la_pantalla_respeta_la_configuracion(app, nav, db, plan, crear_socio):
    socio_id = crear_socio(nombre="Sin Pagar", dni="36000001")
    memberships.asignar_plan(db, socio_id, plan, hoy_real())

    rechazado = nav.post("/asistencia/ingreso", {"q": "36000001"}, follow_redirects=True).get_data(as_text=True)
    assert "todavía no registra ningún pago" in rechazado

    app.config["ACCESO_SIN_PAGO"] = True
    aceptado = nav.post("/asistencia/ingreso", {"q": "36000001"}, follow_redirects=True).get_data(as_text=True)
    assert "Ingreso registrado: Sin Pagar" in aceptado

    app.config["PERMITIR_REINGRESO"] = True
    otra_vez = nav.post("/asistencia/ingreso", {"q": "36000001"}, follow_redirects=True).get_data(as_text=True)
    assert "Ingreso registrado: Sin Pagar" in otra_vez and "Ingresos de hoy (2)" in otra_vez


def test_la_pantalla_muestra_el_aviso_de_clases(app, nav, db, crear_socio):
    app.config["ACCESO_SIN_PAGO"] = True
    with db:
        plan_2 = models.crear_plan(db, dict(nombre="Dos por semana", precio_centavos=PRECIO, duracion_dias=30, clases_por_semana=2))
    socio_id = crear_socio(nombre="Dos Veces", dni="36000002")
    memberships.asignar_plan(db, socio_id, plan_2, hoy_real())
    html = nav.post("/asistencia/ingreso", {"q": "36000002"}, follow_redirects=True).get_data(as_text=True)
    assert "Clase 1 de 2 de la semana" in html
