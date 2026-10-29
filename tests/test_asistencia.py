"""Registro de ingresos y rechazo por membresía vencida."""
from datetime import timedelta

import pytest

from app import models
from app.services import attendance, memberships, payments
from app.services.attendance import ReglasIngreso
from app.services.errors import ErrorDeNegocio
from conftest import HOY, hoy_real

# Estos tests prueban el vencimiento y el aviso, no el cobro: el caso «sin pago» se prueba en test_reglas_ingreso.py
SIN_PAGO_OK = ReglasIngreso(acceso_sin_pago=True)


def _ingresos(db, socio_id):
    return db.execute("SELECT COUNT(*) FROM asistencias WHERE socio_id = ?", (socio_id,)).fetchone()[0]


def test_ingreso_rechazado_con_membresia_vencida(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=-5)  # venció hace 5 días

    with pytest.raises(ErrorDeNegocio) as error:
        attendance.registrar_ingreso(db, socio_id, hoy=HOY)

    mensaje = str(error.value)
    assert "Ingreso rechazado" in mensaje
    assert "hace 5 días" in mensaje
    assert "Registrá un pago" in mensaje
    assert _ingresos(db, socio_id) == 0  # no quedó registrado


def test_ingreso_rechazado_el_dia_siguiente_al_vencimiento(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=-1)
    with pytest.raises(ErrorDeNegocio, match="ayer"):
        attendance.registrar_ingreso(db, socio_id, hoy=HOY)


def test_ingreso_permitido_el_ultimo_dia(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=0)
    r = attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=SIN_PAGO_OK)
    assert r["estado"] == models.POR_VENCER
    assert "vence hoy" in r["aviso"]
    assert _ingresos(db, socio_id) == 1


def test_ingreso_con_membresia_vigente_no_avisa_nada(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=20)
    r = attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=SIN_PAGO_OK)
    assert r["estado"] == models.VIGENTE
    assert r["aviso"] is None


def test_ingreso_por_vencer_avisa_cuantos_dias_quedan(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=3)
    assert "vence en 3 días" in attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=SIN_PAGO_OK)["aviso"]


def test_no_se_registra_dos_veces_el_mismo_dia(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=20)
    attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=SIN_PAGO_OK)
    with pytest.raises(ErrorDeNegocio, match="ya registró su ingreso hoy"):
        attendance.registrar_ingreso(db, socio_id, hoy=HOY, reglas=SIN_PAGO_OK)
    assert _ingresos(db, socio_id) == 1
    # al día siguiente sí
    attendance.registrar_ingreso(db, socio_id, hoy=HOY + timedelta(days=1), reglas=SIN_PAGO_OK)
    assert _ingresos(db, socio_id) == 2


def test_socio_sin_plan_no_puede_ingresar(db, crear_socio):
    with pytest.raises(ErrorDeNegocio, match="no tiene un plan"):
        attendance.registrar_ingreso(db, crear_socio(), hoy=HOY)


@pytest.mark.parametrize("estado, texto", [("pausado", "pausada"), ("baja", "dado de baja")])
def test_socio_pausado_o_de_baja_no_puede_ingresar(db, plan, crear_socio, estado, texto):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY)
    with db:
        db.execute("UPDATE socios SET estado = ? WHERE id = ?", (estado, socio_id))
    with pytest.raises(ErrorDeNegocio, match=texto):
        attendance.registrar_ingreso(db, socio_id, hoy=HOY)


def test_busqueda_por_dni_con_o_sin_puntos(db, crear_socio):
    socio_id = crear_socio(nombre="Lucía Gómez", dni="30123456")
    assert [s["id"] for s in attendance.buscar_socios(db, "30123456")] == [socio_id]
    assert [s["id"] for s in attendance.buscar_socios(db, "30.123.456")] == [socio_id]


def test_busqueda_por_parte_del_nombre(db, crear_socio):
    crear_socio(nombre="Lucía Gómez")
    crear_socio(nombre="Lucas Pérez")
    assert len(attendance.buscar_socios(db, "luc")) == 2
    assert len(attendance.buscar_socios(db, "gómez")) == 1
    assert attendance.buscar_socios(db, "") == []


# ---- a través de la pantalla ------------------------------------------------
def _socio_real(db, plan, crear_socio, dias_hasta_vencer, pagado=False, **kw):
    socio_id = crear_socio(**kw)
    inicio = hoy_real() + timedelta(days=dias_hasta_vencer - 30)
    memberships.asignar_plan(db, socio_id, plan, inicio)
    if pagado:  # pago completo del período inicial: no cambia el vencimiento
        payments.registrar_pago(db, socio_id, 2500000, hoy_real(), "efectivo")
    return socio_id


def test_pantalla_muestra_el_rechazo_por_cuota_vencida(nav, db, plan, crear_socio):
    _socio_real(db, plan, crear_socio, -10, nombre="Pablo Vencido", dni="31111111")

    r = nav.post("/asistencia/ingreso", {"q": "31111111"}, follow_redirects=True)
    html = r.get_data(as_text=True)

    assert "Ingreso rechazado" in html
    assert "Pablo Vencido" in html
    assert "hace 10 días" in html
    assert "Todavía no hay ingresos registrados hoy" in html


def test_pantalla_registra_el_ingreso_de_un_socio_al_dia(nav, db, plan, crear_socio):
    _socio_real(db, plan, crear_socio, 20, pagado=True, nombre="Sofía Al Día", dni="32222222")

    html = nav.post("/asistencia/ingreso", {"q": "32222222"}, follow_redirects=True).get_data(as_text=True)

    assert "Ingreso registrado: Sofía Al Día" in html
    assert "Ingresos de hoy (1)" in html


def test_pantalla_pide_elegir_cuando_hay_varios_socios(nav, db, plan, crear_socio):
    _socio_real(db, plan, crear_socio, 20, nombre="Juan Pérez", dni="33333331")
    _socio_real(db, plan, crear_socio, 20, nombre="Juan Gómez", dni="33333332")

    html = nav.post("/asistencia/ingreso", {"q": "Juan"}).get_data(as_text=True)

    assert "Encontramos varios socios" in html
    assert "Juan Pérez" in html and "Juan Gómez" in html


def test_pantalla_avisa_si_no_encuentra_al_socio(nav):
    html = nav.post("/asistencia/ingreso", {"q": "99999999"}, follow_redirects=True).get_data(as_text=True)
    assert "No encontramos ningún socio" in html
