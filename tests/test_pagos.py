"""Pagos: renuevan o extienden la membresía."""
from datetime import date, timedelta

import pytest

from app import models
from app.services import memberships, payments
from app.services.errors import ErrorDeNegocio
from app.services.validation import parse_monto, validar_pago
from conftest import HOY, hoy_real

PRECIO = 2500000


def _vencimiento(db, socio_id):
    return models.membresia_actual(db, socio_id)["fecha_vencimiento"]


def test_pago_extiende_la_membresia_vigente(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=10)          # vence el 4/11
    vencimiento = date(2026, 11, 4)

    primero = payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")   # confirma el período inicial
    assert primero["vencimiento_nuevo"] == vencimiento

    segundo = payments.registrar_pago(db, socio_id, PRECIO, HOY, "transferencia")
    assert segundo["vencimiento_anterior"] == vencimiento
    assert segundo["vencimiento_nuevo"] == vencimiento + timedelta(days=30)    # a continuación, sin perder días
    assert _vencimiento(db, socio_id) == "2026-12-04"


def test_el_primer_pago_confirma_el_periodo_inicial_sin_regalar_otro(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=30)          # recién inscripto: vence el 24/11
    r = payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    assert r["cubrio_periodo_inicial"] is True
    assert r["vencimiento_nuevo"] == r["vencimiento_anterior"] == date(2026, 11, 24)


def test_pago_con_membresia_vencida_cuenta_desde_la_fecha_del_pago(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=-20)         # venció el 5/10
    r = payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    assert r["vencimiento_nuevo"] == HOY + timedelta(days=30)
    assert r["cubrio_periodo_inicial"] is False
    assert memberships.estado_membresia(_vencimiento(db, socio_id), HOY) == models.VIGENTE


def test_pago_atrasado_registrado_con_fecha_pasada(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=-20)         # venció el 5/10
    r = payments.registrar_pago(db, socio_id, PRECIO, date(2026, 10, 10), "efectivo")
    assert r["vencimiento_nuevo"] == date(2026, 11, 9)       # 10/10 + 30 días


def test_el_pago_queda_en_el_historial_con_sus_datos(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=5)
    payments.registrar_pago(db, socio_id, 2500050, HOY, "tarjeta", "pagó en dos cuotas", confirmar=True)  # $ 50 de más: pide confirmar
    pago = models.pagos_de_socio(db, socio_id)[0]
    assert pago["monto_centavos"] == 2500050
    assert pago["metodo"] == "tarjeta"
    assert pago["nota"] == "pagó en dos cuotas"
    assert pago["fecha"] == "2026-10-25"
    assert pago["plan_nombre"] == "Mensual"


def test_un_pago_que_falla_no_modifica_la_membresia(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=10)
    antes = _vencimiento(db, socio_id)
    with pytest.raises(ErrorDeNegocio):
        payments.registrar_pago(db, socio_id, PRECIO, HOY, "bitcoin")
    assert _vencimiento(db, socio_id) == antes
    assert models.pagos_de_socio(db, socio_id) == []


@pytest.mark.parametrize("monto", [0, -100])
def test_monto_cero_o_negativo_rechazado_en_el_servicio(db, socio_con_plan, monto):
    socio_id = socio_con_plan(dias_hasta_vencer=10)
    with pytest.raises(ErrorDeNegocio, match="mayor a cero"):
        payments.registrar_pago(db, socio_id, monto, HOY, "efectivo")


def test_no_se_puede_pagar_sin_plan(db, crear_socio):
    with pytest.raises(ErrorDeNegocio, match="no tiene un plan"):
        payments.registrar_pago(db, crear_socio(), PRECIO, HOY, "efectivo")


def test_no_se_puede_pagar_a_un_socio_de_baja(db, socio_con_plan):
    socio_id = socio_con_plan(dias_hasta_vencer=10)
    with db:
        db.execute("UPDATE socios SET estado = 'baja' WHERE id = ?", (socio_id,))
    with pytest.raises(ErrorDeNegocio, match="dado de baja"):
        payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")


# ---- validación del formulario ----------------------------------------------
@pytest.mark.parametrize("texto, centavos", [
    ("25000", 2500000), ("25.000", 2500000), ("25.000,50", 2500050), ("25000,5", 2500050),
    ("$ 25.000", 2500000), ("1.5", 150), ("0,99", 99), ("1.500.000", 150000000),
])
def test_parse_monto_entiende_el_formato_argentino(texto, centavos):
    assert parse_monto(texto) == centavos


@pytest.mark.parametrize("texto", ["", "abc", "12,345", "1e5", "NaN", "Infinity"])
def test_parse_monto_rechaza_lo_que_no_es_un_monto(texto):
    with pytest.raises(ValueError):
        parse_monto(texto)


@pytest.mark.parametrize("monto", ["0", "-500", "abc", ""])
def test_formulario_rechaza_montos_invalidos(monto):
    _, errores = validar_pago({"monto": monto, "metodo": "efectivo"}, HOY)
    assert "monto" in errores


def test_formulario_rechaza_fecha_futura_y_metodo_invalido():
    _, errores = validar_pago({"monto": "1000", "metodo": "cheque", "fecha": "2026-11-30"}, HOY)
    assert "fecha" in errores and "metodo" in errores


def test_formulario_acepta_un_pago_correcto():
    datos, errores = validar_pago({"monto": "25.000", "metodo": "transferencia", "fecha": "2026-10-20"}, HOY)
    assert errores == {}
    assert datos["monto_centavos"] == 2500000 and datos["fecha"] == date(2026, 10, 20)


# ---- a través de la pantalla ------------------------------------------------
def _socio_real_vencido(db, plan, crear_socio):
    socio_id = crear_socio(nombre="Marta Atrasada", dni="34444444")
    memberships.asignar_plan(db, socio_id, plan, hoy_real() - timedelta(days=50))   # venció hace 20 días
    return socio_id


def test_pantalla_registra_el_pago_y_renueva(nav, db, plan, crear_socio):
    socio_id = _socio_real_vencido(db, plan, crear_socio)

    r = nav.post("/pagos/nuevo", {"socio_id": socio_id, "monto": "25.000", "metodo": "efectivo",
                                  "fecha": hoy_real().isoformat()}, follow_redirects=True)
    html = r.get_data(as_text=True)

    assert "Pago registrado" in html
    assert "$ 25.000" in html                      # aparece en el historial del socio
    assert _vencimiento(db, socio_id) == (hoy_real() + timedelta(days=30)).isoformat()


def test_pantalla_rechaza_monto_negativo_y_no_guarda_nada(nav, db, plan, crear_socio):
    socio_id = _socio_real_vencido(db, plan, crear_socio)

    html = nav.post("/pagos/nuevo", {"socio_id": socio_id, "monto": "-5", "metodo": "efectivo"}).get_data(as_text=True)

    assert "mayor a cero" in html
    assert models.pagos_de_socio(db, socio_id) == []
