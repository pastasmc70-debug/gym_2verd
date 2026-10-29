"""Pagos menores al precio del plan: piden confirmación, no extienden y dejan saldo pendiente."""
from datetime import timedelta

import pytest

from app import models
from app.services import memberships, payments
from app.services.errors import RequiereConfirmacion
from conftest import HOY, hoy_real

PRECIO = 2500000


def _vence(db, socio_id):
    return models.obtener_socio(db, socio_id)["fecha_vencimiento"]


def _n_pagos(db, socio_id):
    return db.execute("SELECT COUNT(*) FROM pagos WHERE socio_id = ?", (socio_id,)).fetchone()[0]


def test_un_pago_menor_al_precio_pide_confirmacion_y_no_guarda_nada(db, socio_con_plan):
    socio_id = socio_con_plan(10)

    with pytest.raises(RequiereConfirmacion) as e:
        payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo")

    assert e.value.codigo == "pago_parcial"
    assert e.value.datos["faltante_centavos"] == PRECIO and e.value.datos["monto_centavos"] == 1000000
    assert _n_pagos(db, socio_id) == 0


def test_pago_parcial_confirmado_queda_registrado_pero_no_extiende(db, socio_con_plan):
    socio_id = socio_con_plan(10)
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")          # período inicial pago
    antes = _vence(db, socio_id)

    r = payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo", confirmar_parcial=True)

    assert r["es_parcial"] is True
    assert _vence(db, socio_id) == antes                                    # no se extendió
    assert r["saldo_pendiente_centavos"] == PRECIO - 1000000                # le faltan 15.000
    assert models.obtener_pago(db, r["pago_id"])["es_parcial"] == 1


def test_al_completar_el_precio_con_otro_pago_recien_ahi_se_extiende(db, socio_con_plan):
    socio_id = socio_con_plan(10)
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo", confirmar_parcial=True)

    # el resto (15.000) es justo lo que falta: no es parcial y completa el período
    r = payments.registrar_pago(db, socio_id, 1500000, HOY, "transferencia")

    assert r["es_parcial"] is False
    assert _vence(db, socio_id) == (HOY + timedelta(days=40)).isoformat()   # +30 días recién ahora
    assert r["saldo_pendiente_centavos"] == 0


def test_dos_parciales_que_juntos_completan_el_periodo(db, socio_con_plan):
    socio_id = socio_con_plan(10)
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo", confirmar_parcial=True)
    # 10.000 más: sigue faltando 5.000, así que vuelve a pedir confirmación
    with pytest.raises(RequiereConfirmacion) as e:
        payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo")
    assert e.value.datos["faltante_centavos"] == 1500000                     # lo que falta, no el precio entero
    r = payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo", confirmar_parcial=True)
    assert r["es_parcial"] is True and r["faltante_centavos"] == 500000
    assert _vence(db, socio_id) == (HOY + timedelta(days=10)).isoformat()   # todavía sin extender
    r = payments.registrar_pago(db, socio_id, 500000, HOY, "efectivo")
    assert _vence(db, socio_id) == (HOY + timedelta(days=40)).isoformat()


def test_el_primer_pago_parcial_deja_el_periodo_inicial_con_saldo(db, socio_con_plan):
    socio_id = socio_con_plan(10)
    payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo", confirmar_parcial=True)
    assert payments.saldo_del_socio(db, socio_id) == 1500000
    assert _vence(db, socio_id) == (HOY + timedelta(days=10)).isoformat()


def test_el_socio_sin_pagos_debe_el_periodo_inicial(db, socio_con_plan):
    assert payments.saldo_del_socio(db, socio_con_plan(10)) == PRECIO


def test_el_socio_al_dia_no_tiene_saldo(db, socio_con_plan):
    socio_id = socio_con_plan(10)
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    assert payments.saldo_del_socio(db, socio_id) == 0


def test_un_pago_de_mas_deja_credito_para_el_periodo_siguiente(db, socio_con_plan):
    socio_id = socio_con_plan(10)
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    payments.registrar_pago(db, socio_id, PRECIO + 500000, HOY, "efectivo", confirmar=True)   # 30.000: un período + 5.000 (de más: pide confirmar)
    assert _vence(db, socio_id) == (HOY + timedelta(days=40)).isoformat()
    assert payments.saldo_del_socio(db, socio_id) == 0                       # el sobrante no es una deuda
    # con 20.000 más se completa otro período (5.000 de crédito + 20.000)
    payments.registrar_pago(db, socio_id, 2000000, HOY, "efectivo", confirmar_parcial=True)
    assert _vence(db, socio_id) == (HOY + timedelta(days=70)).isoformat()


def test_anular_el_pago_que_completaba_vuelve_a_dejar_el_saldo(db, socio_con_plan):
    socio_id = socio_con_plan(10)
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo", confirmar_parcial=True)
    completa = payments.registrar_pago(db, socio_id, 1500000, HOY, "efectivo")["pago_id"]
    assert _vence(db, socio_id) == (HOY + timedelta(days=40)).isoformat()

    payments.anular_pago(db, completa, "Era otro socio", "admin")

    assert _vence(db, socio_id) == (HOY + timedelta(days=10)).isoformat()
    assert payments.saldo_del_socio(db, socio_id) == 1500000


def test_el_precio_que_cuenta_es_el_que_tenia_el_plan_al_asignarlo(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY)
    with db:
        db.execute("UPDATE planes SET precio_centavos = 9900000 WHERE id = ?", (plan,))   # el plan sube de precio
    r = payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")                  # igual alcanza para el período
    assert r["es_parcial"] is False and payments.saldo_del_socio(db, socio_id) == 0


# -------------------------------------------------------------------------- pantallas
def _socio_pago_real(db, plan, crear_socio):
    socio_id = crear_socio(nombre="Marta Díaz", dni="35000001")
    memberships.asignar_plan(db, socio_id, plan, hoy_real() - timedelta(days=20))
    payments.registrar_pago(db, socio_id, PRECIO, hoy_real(), "efectivo")
    return socio_id


def test_pantalla_avisa_y_pide_confirmar_un_pago_parcial(nav, db, plan, crear_socio):
    socio_id = _socio_pago_real(db, plan, crear_socio)
    datos = {"socio_id": socio_id, "monto": "10.000", "fecha": hoy_real().isoformat(), "metodo": "efectivo"}

    html = nav.post(f"/pagos/nuevo?socio_id={socio_id}", datos).get_data(as_text=True)

    assert "Este pago es menor a lo que falta" in html
    assert "pago parcial" in html and "no extiende la membresía" in html
    assert "Confirmar pago parcial" in html and 'name="confirmar_parcial"' in html
    assert db.execute("SELECT COUNT(*) FROM pagos WHERE socio_id = ?", (socio_id,)).fetchone()[0] == 1   # nada guardado


def test_pantalla_registra_el_parcial_al_confirmar_y_muestra_el_saldo(nav, db, plan, crear_socio):
    socio_id = _socio_pago_real(db, plan, crear_socio)
    datos = {"socio_id": socio_id, "monto": "10.000", "fecha": hoy_real().isoformat(), "metodo": "efectivo",
             "confirmar_parcial": "1"}

    html = nav.post(f"/pagos/nuevo?socio_id={socio_id}", datos, follow_redirects=True).get_data(as_text=True)

    assert "Pago parcial registrado" in html and "la membresía no se extendió" in html
    assert "Saldo pendiente: $ 15.000" in html and "Parcial" in html


def test_pago_completo_por_pantalla_no_pide_confirmacion(nav, db, plan, crear_socio):
    socio_id = _socio_pago_real(db, plan, crear_socio)
    datos = {"socio_id": socio_id, "monto": "25.000", "fecha": hoy_real().isoformat(), "metodo": "tarjeta"}
    html = nav.post(f"/pagos/nuevo?socio_id={socio_id}", datos, follow_redirects=True).get_data(as_text=True)
    assert "Pago registrado" in html and "Saldo pendiente" not in html


def test_el_formulario_de_pago_sugiere_lo_que_falta(nav, db, plan, crear_socio):
    socio_id = crear_socio(nombre="Nuevo Socio", dni="35000002")
    memberships.asignar_plan(db, socio_id, plan, hoy_real())
    html = nav.get(f"/pagos/nuevo?socio_id={socio_id}").get_data(as_text=True)
    assert 'value="25000"' in html and "Saldo pendiente: $ 25.000" in html
