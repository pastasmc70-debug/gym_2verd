"""Anular pagos y membresías: no se borra nada, se recalcula el vencimiento y no cuentan en totales."""
from datetime import timedelta

import pytest

from app import models
from app.services import caja, dashboard, memberships, payments
from app.services.errors import ErrorDeNegocio
from conftest import HOY, hoy_real, leer_csv

PRECIO = 2500000


def _vence(db, socio_id):
    return models.obtener_socio(db, socio_id)["fecha_vencimiento"]


def _dos_pagos(db, socio_con_plan):
    """Socio que vence en 10 días con dos períodos pagos: el inicial y uno de renovación."""
    socio_id = socio_con_plan(10)
    a = payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo", cargado_por="admin")
    b = payments.registrar_pago(db, socio_id, PRECIO, HOY, "transferencia", cargado_por="admin")
    assert _vence(db, socio_id) == (HOY + timedelta(days=40)).isoformat()
    return socio_id, a["pago_id"], b["pago_id"]


# ------------------------------------------------------------------ anular un pago
def test_anular_el_ultimo_pago_recalcula_el_vencimiento(db, socio_con_plan):
    socio_id, _, segundo = _dos_pagos(db, socio_con_plan)

    r = payments.anular_pago(db, segundo, "Se cargó dos veces", "admin")

    assert _vence(db, socio_id) == (HOY + timedelta(days=10)).isoformat()
    assert r["vencimiento"] == HOY + timedelta(days=10)


def test_anular_el_primer_pago_deja_un_solo_periodo_pago(db, socio_con_plan):
    # El que queda pasa a ser el primero: confirma el período inicial y no suma otro.
    socio_id, primero, _ = _dos_pagos(db, socio_con_plan)

    payments.anular_pago(db, primero, "Error de carga", "admin")

    assert _vence(db, socio_id) == (HOY + timedelta(days=10)).isoformat()


def test_anular_todos_los_pagos_deja_el_periodo_inicial_sin_pagar(db, socio_con_plan):
    socio_id, primero, segundo = _dos_pagos(db, socio_con_plan)
    payments.anular_pago(db, primero, "x", "admin")
    payments.anular_pago(db, segundo, "x", "admin")

    assert _vence(db, socio_id) == (HOY + timedelta(days=10)).isoformat()
    assert payments.saldo_del_socio(db, socio_id) == PRECIO   # vuelve a deber el período inicial


def test_el_pago_anulado_no_se_borra_y_guarda_quien_cuando_y_por_que(db, socio_con_plan):
    socio_id, _, segundo = _dos_pagos(db, socio_con_plan)

    payments.anular_pago(db, segundo, "  Se cargó dos veces  ", "recepcion")

    assert db.execute("SELECT COUNT(*) FROM pagos WHERE socio_id = ?", (socio_id,)).fetchone()[0] == 2
    p = models.obtener_pago(db, segundo)
    assert p["anulado"] == 1
    assert p["anulado_motivo"] == "Se cargó dos veces"       # sin espacios de más
    assert p["anulado_por"] == "recepcion"
    assert p["anulado_en"] and p["anulado_en"].startswith("20")
    assert p["monto_centavos"] == PRECIO                    # los datos originales quedan intactos


def test_el_motivo_es_obligatorio(db, socio_con_plan):
    _, _, segundo = _dos_pagos(db, socio_con_plan)
    for motivo in ("", "   ", None):
        with pytest.raises(ErrorDeNegocio, match="motivo"):
            payments.anular_pago(db, segundo, motivo, "admin")
    assert models.obtener_pago(db, segundo)["anulado"] == 0


def test_no_se_anula_dos_veces_el_mismo_pago(db, socio_con_plan):
    _, _, segundo = _dos_pagos(db, socio_con_plan)
    payments.anular_pago(db, segundo, "primera vez", "admin")
    with pytest.raises(ErrorDeNegocio, match="ya estaba anulado"):
        payments.anular_pago(db, segundo, "otra vez", "admin")
    assert models.obtener_pago(db, segundo)["anulado_motivo"] == "primera vez"


def test_pago_inexistente(db):
    with pytest.raises(ErrorDeNegocio, match="No encontramos el pago"):
        payments.anular_pago(db, 999, "x", "admin")


# --------------------------------------------------- los anulados no cuentan en totales
def test_el_pago_anulado_no_cuenta_en_el_panel(db, socio_con_plan):
    socio_id = socio_con_plan(20)
    pago = payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")["pago_id"]
    assert dashboard.resumen(db, HOY)["ingresos_mes_centavos"] == PRECIO

    payments.anular_pago(db, pago, "error", "admin")

    assert dashboard.resumen(db, HOY)["ingresos_mes_centavos"] == 0


def test_el_pago_anulado_se_lista_en_la_caja_pero_no_suma(db, socio_con_plan):
    socio_id = socio_con_plan(20)
    bueno = payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")["pago_id"]
    malo = payments.registrar_pago(db, socio_id, PRECIO, HOY, "tarjeta")["pago_id"]
    payments.anular_pago(db, malo, "error", "admin")

    dia = caja.cuotas_del_dia(db, HOY)

    assert dia["total_centavos"] == PRECIO
    assert dia["por_metodo"]["efectivo"] == PRECIO and dia["por_metodo"]["tarjeta"] == 0
    assert dia["cantidad"] == 1 and dia["anulados"] == 1
    assert {p["id"]: p["anulado"] for p in dia["pagos"]} == {bueno: 0, malo: 1}


def test_el_csv_de_pagos_marca_los_anulados(nav, db, plan, crear_socio):
    socio_id = crear_socio(nombre="Ana Paz", dni="30000001")
    memberships.asignar_plan(db, socio_id, plan, hoy_real() - timedelta(days=5))
    ok = payments.registrar_pago(db, socio_id, PRECIO, hoy_real(), "efectivo")["pago_id"]
    mal = payments.registrar_pago(db, socio_id, 1500000, hoy_real(), "tarjeta", confirmar_parcial=True)["pago_id"]
    payments.anular_pago(db, mal, "Monto mal cargado", "admin")

    filas = leer_csv(nav.get("/exportar/pagos.csv"))

    cab = filas[0]
    col = {nombre: i for i, nombre in enumerate(cab)}
    por_id = {f[col["ID"]]: f for f in filas[1:]}
    assert len(filas) == 3                                              # el anulado aparece
    bueno, anulado = por_id[str(ok)], por_id[str(mal)]
    assert bueno[col["Estado"]] == "Vigente" and bueno[col["Monto que cuenta (ARS)"]] == "25000,00"
    assert anulado[col["Estado"]] == "ANULADO"
    assert anulado[col["Monto (ARS)"]] == "15000,00"                    # se conserva el monto original
    assert anulado[col["Monto que cuenta (ARS)"]] == "0,00"             # pero no cuenta
    assert anulado[col["Motivo de anulación"]] == "Monto mal cargado" and anulado[col["Anulado por"]] == "admin"
    assert anulado[col["Anulado el"]] == hoy_real().strftime("%d/%m/%Y")


# ------------------------------------------------------------------ anular una membresía
def test_anular_membresia_sin_pagos_vuelve_a_la_anterior(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY - timedelta(days=10))               # vence en 20 días
    mala = memberships.asignar_plan(db, socio_id, plan, HOY)["membresia_id"]            # asignada por error
    assert _vence(db, socio_id) == (HOY + timedelta(days=30)).isoformat()

    payments.anular_membresia(db, mala, "Plan equivocado", "admin")

    assert _vence(db, socio_id) == (HOY + timedelta(days=20)).isoformat()
    m = models.obtener_membresia(db, mala)
    assert m["anulada"] == 1 and m["anulada_motivo"] == "Plan equivocado" and m["anulada_por"] == "admin"
    assert db.execute("SELECT COUNT(*) FROM membresias WHERE socio_id = ?", (socio_id,)).fetchone()[0] == 2


def test_anular_la_unica_membresia_deja_al_socio_sin_plan(db, plan, crear_socio):
    socio_id = crear_socio()
    m = memberships.asignar_plan(db, socio_id, plan, HOY)["membresia_id"]
    payments.anular_membresia(db, m, "error", "admin")
    assert models.obtener_socio(db, socio_id)["plan_nombre"] is None
    assert models.membresia_actual(db, socio_id) is None


def test_no_se_anula_una_membresia_con_pagos_vigentes(db, socio_con_plan):
    socio_id = socio_con_plan(20)
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    m = models.membresia_actual(db, socio_id)["id"]

    with pytest.raises(ErrorDeNegocio, match="Primero anulá esos pagos"):
        payments.anular_membresia(db, m, "error", "admin")

    # anulando el pago primero, ya se puede
    pago = db.execute("SELECT id FROM pagos WHERE membresia_id = ?", (m,)).fetchone()[0]
    payments.anular_pago(db, pago, "error", "admin")
    payments.anular_membresia(db, m, "error", "admin")
    assert models.obtener_membresia(db, m)["anulada"] == 1


def test_motivo_obligatorio_para_anular_membresia(db, plan, crear_socio):
    socio_id = crear_socio()
    m = memberships.asignar_plan(db, socio_id, plan, HOY)["membresia_id"]
    with pytest.raises(ErrorDeNegocio, match="motivo"):
        payments.anular_membresia(db, m, " ", "admin")


def test_membresia_ya_anulada(db, plan, crear_socio):
    socio_id = crear_socio()
    m = memberships.asignar_plan(db, socio_id, plan, HOY)["membresia_id"]
    payments.anular_membresia(db, m, "error", "admin")
    with pytest.raises(ErrorDeNegocio, match="ya estaba anulada"):
        payments.anular_membresia(db, m, "otra vez", "admin")


# -------------------------------------------------------------------------- pantallas
def _socio_con_pago_real(db, plan, crear_socio, dias_hasta_vencer=10):
    socio_id = crear_socio(nombre="Lucía Gómez", dni="34000001")
    memberships.asignar_plan(db, socio_id, plan, hoy_real() + timedelta(days=dias_hasta_vencer - 30))
    pago = payments.registrar_pago(db, socio_id, PRECIO, hoy_real(), "efectivo")["pago_id"]
    return socio_id, pago


def test_pantalla_de_anular_pago_pide_motivo_y_confirmacion(nav, db, plan, crear_socio):
    socio_id, pago = _socio_con_pago_real(db, plan, crear_socio)

    html = nav.get(f"/pagos/{pago}/anular").get_data(as_text=True)

    assert "Anular pago" in html and "Lucía Gómez" in html
    assert 'name="motivo"' in html and "required" in html
    assert "Confirmar anulación" in html and "confirm(" in html     # confirmación explícita


def test_anular_pago_sin_motivo_no_anula(nav, db, plan, crear_socio):
    _, pago = _socio_con_pago_real(db, plan, crear_socio)

    html = nav.post(f"/pagos/{pago}/anular", {"motivo": "  "}).get_data(as_text=True)

    assert "Escribí el motivo de la anulación" in html
    assert models.obtener_pago(db, pago)["anulado"] == 0


def test_anular_pago_desde_la_pantalla(nav, db, plan, crear_socio):
    socio_id, pago = _socio_con_pago_real(db, plan, crear_socio)

    r = nav.post(f"/pagos/{pago}/anular", {"motivo": "Cargado dos veces"}, follow_redirects=True)
    html = r.get_data(as_text=True)

    assert "Pago anulado" in html
    assert "Anulado" in html and "Cargado dos veces" in html          # queda a la vista en la ficha
    p = models.obtener_pago(db, pago)
    assert p["anulado"] == 1 and p["anulado_por"] == "admin"


def test_la_lista_de_pagos_muestra_los_anulados_marcados(nav, db, plan, crear_socio):
    _, pago = _socio_con_pago_real(db, plan, crear_socio)
    payments.anular_pago(db, pago, "error", "admin")
    html = nav.get("/pagos/").get_data(as_text=True)
    assert 'class="anulado"' in html and "Anulado" in html


def test_anular_membresia_desde_la_pantalla(nav, db, plan, crear_socio):
    socio_id = crear_socio()
    m = memberships.asignar_plan(db, socio_id, plan, hoy_real())["membresia_id"]

    assert "Confirmar anulación" in nav.get(f"/membresias/{m}/anular").get_data(as_text=True)
    assert "Escribí el motivo" in nav.post(f"/membresias/{m}/anular", {"motivo": ""}).get_data(as_text=True)
    assert models.obtener_membresia(db, m)["anulada"] == 0

    html = nav.post(f"/membresias/{m}/anular", {"motivo": "Plan equivocado"}, follow_redirects=True).get_data(as_text=True)
    assert "Membresía anulada" in html and "Plan equivocado" in html
    assert models.obtener_membresia(db, m)["anulada"] == 1


def test_pantalla_de_membresia_con_pagos_avisa_que_hay_que_anularlos_antes(nav, db, plan, crear_socio):
    _, _ = _socio_con_pago_real(db, plan, crear_socio)
    m = db.execute("SELECT id FROM membresias").fetchone()[0]
    html = nav.get(f"/membresias/{m}/anular").get_data(as_text=True)
    assert "Primero anulá esos pagos" in html
