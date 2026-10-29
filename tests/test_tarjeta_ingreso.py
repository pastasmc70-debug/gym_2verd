"""Tarjeta que recepción ve al registrar un ingreso: foto, nombre, plan, estado, días restantes y saldo."""
from datetime import timedelta

import pytest

from app import models
from app.services import attendance, memberships, payments
from conftest import hoy_real

PRECIO = 2500000


@pytest.fixture
def con_plan(db, plan, crear_socio, app):
    app.config["ACCESO_SIN_PAGO"] = True       # estos tests miran la tarjeta, no la regla de pago

    def _crear(dias_hasta_vencer, dni="37000001", nombre="Lucía Gómez", foto=None):
        socio_id = crear_socio(nombre=nombre, dni=dni)
        if foto:
            with db:
                db.execute("UPDATE socios SET foto = ? WHERE id = ?", (foto, socio_id))
        memberships.asignar_plan(db, socio_id, plan, hoy_real() + timedelta(days=dias_hasta_vencer - 30))
        return socio_id
    return _crear


def _ingresar(nav, dni="37000001"):
    """Registra el ingreso y devuelve el HTML de la pantalla a la que redirige (como lo ve recepción)."""
    return nav.post("/asistencia/ingreso", {"q": dni}, follow_redirects=True).get_data(as_text=True)


def test_despues_del_ingreso_se_muestra_la_tarjeta_con_los_datos_del_socio(nav, con_plan):
    con_plan(12)
    html = _ingresar(nav)
    assert 'id="tarjeta-ingreso"' in html
    assert "Lucía Gómez" in html and "DNI 37000001" in html and "Plan Mensual" in html
    assert "Vigente" in html and "Le quedan 12 días" in html
    assert "Ingreso registrado a las" in html


def test_la_tarjeta_aparece_una_sola_vez(nav, con_plan):
    con_plan(12)
    assert 'id="tarjeta-ingreso"' in _ingresar(nav)
    assert 'id="tarjeta-ingreso"' not in nav.get("/asistencia/").get_data(as_text=True)


def test_la_tarjeta_muestra_la_foto_o_la_inicial(nav, con_plan, app):
    con_plan(12, foto="abc123.jpg")
    html = _ingresar(nav)
    assert 'class="foto-tarjeta"' in html and "/fotos/abc123.jpg" in html and "Foto de Lucía Gómez" in html
    con_plan(12, dni="37000002", nombre="Marcos Paz")
    html = _ingresar(nav, "37000002")
    assert 'class="foto-tarjeta sin-foto">M<' in html


@pytest.mark.parametrize("dias, texto, estado", [
    (1, "Le quedan 1 día ", "Por vencer"),
    (0, "Vence hoy", "Por vencer"),
    (30, "Le quedan 30 días", "Vigente"),
])
def test_dias_restantes_y_estado(nav, con_plan, dias, texto, estado):
    con_plan(dias)
    html = _ingresar(nav)
    assert texto in html and estado in html


def test_si_debe_una_cuota_parcial_la_tarjeta_lo_dice(nav, db, con_plan):
    socio = con_plan(12)
    payments.registrar_pago(db, socio, 1000000, hoy_real(), "efectivo", confirmar_parcial=True)
    html = _ingresar(nav)
    assert 'id="tarjeta-saldo"' in html and "Debe" in html and "$ 15.000" in html
    assert f"/pagos/nuevo?socio_id={socio}" in html


def test_si_no_debe_nada_no_aparece_el_aviso_de_deuda(nav, db, con_plan):
    socio = con_plan(12)
    payments.registrar_pago(db, socio, PRECIO, hoy_real(), "efectivo")
    assert 'id="tarjeta-saldo"' not in _ingresar(nav)


def test_quien_entra_sin_haber_pagado_nada_figura_con_todo_el_precio_pendiente(nav, con_plan):
    con_plan(12)                                           # entra porque la regla «acceso sin pago» está activa
    html = _ingresar(nav)
    assert 'id="tarjeta-saldo"' in html and "$ 25.000" in html


def test_un_ingreso_rechazado_no_muestra_tarjeta(nav, con_plan):
    con_plan(-5)                                          # cuota vencida
    html = _ingresar(nav)
    assert "Ingreso rechazado" in html and 'id="tarjeta-ingreso"' not in html


def test_un_reingreso_rechazado_no_muestra_tarjeta_nueva(nav, con_plan):
    con_plan(12)
    _ingresar(nav)
    html = _ingresar(nav)
    assert "ya registró su ingreso hoy" in html and 'id="tarjeta-ingreso"' not in html


def test_la_tarjeta_tambien_la_ve_recepcion(nav_recepcion, con_plan):
    con_plan(12)
    html = _ingresar(nav_recepcion)
    assert 'id="tarjeta-ingreso"' in html and "Lucía Gómez" in html


def test_el_nombre_se_escapa_en_la_tarjeta(nav, db, con_plan):
    con_plan(12, nombre="<b>Hack</b>")
    html = _ingresar(nav)
    assert "<b>Hack</b>" not in html and "&lt;b&gt;Hack&lt;/b&gt;" in html


def test_el_servicio_arma_la_tarjeta(db, con_plan):
    socio = con_plan(5)
    t = attendance.tarjeta_ingreso(db, socio, hoy_real())
    assert (t["nombre"], t["plan_nombre"], t["estado"], t["dias_restantes"], t["saldo_centavos"]) == \
           ("Lucía Gómez", "Mensual", models.POR_VENCER, 5, PRECIO)   # nunca pagó: debe el período inicial
    assert attendance.tarjeta_ingreso(db, 99999) is None


def test_el_servicio_arma_la_tarjeta_de_un_socio_sin_plan(db, crear_socio):
    t = attendance.tarjeta_ingreso(db, crear_socio(), hoy_real())
    assert t["estado"] == models.SIN_MEMBRESIA and t["dias_restantes"] is None and t["plan_nombre"] is None
