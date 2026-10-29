"""Tarea H: pagos por varios períodos (1, 2, 3, 6, 12 y anual), descuento anual, confirmación del sobrante,
saldo a favor y anulación de un pago de varios períodos."""
from datetime import timedelta

import pytest

from app import db as dbm
from app import migraciones, models
from app.services import caja, memberships, payments
from app.services.errors import RequiereConfirmacion
from app.services.validation import validar_plan
from conftest import HOY, hoy_real

PRECIO = 2500000          # $ 25.000
DIA = timedelta(days=1)


# ----------------------------------------------------------------------------- ayudas
def _plan(db, nombre, precio=PRECIO, duracion=30, tipo=None, valor=None):
    with db:
        return models.crear_plan(db, dict(nombre=nombre, precio_centavos=precio, duracion_dias=duracion,
                                          clases_por_semana=None, descuento_anual_tipo=tipo,
                                          descuento_anual_valor=valor))


def _socio_al_dia(db, plan, crear_socio, hoy=HOY, **kw):
    """Socio que ya pagó su período inicial: vence en `hoy` + 10 días."""
    socio_id = crear_socio(**kw)
    memberships.asignar_plan(db, socio_id, plan, hoy - 20 * DIA)
    payments.registrar_pago(db, socio_id, models.membresia_actual(db, socio_id)["precio_centavos"], hoy, "efectivo")
    return socio_id


def _vence(db, socio_id):
    return models.obtener_socio(db, socio_id)["fecha_vencimiento"]


def _n_pagos(db, socio_id):
    return db.execute("SELECT COUNT(*) FROM pagos WHERE socio_id = ?", (socio_id,)).fetchone()[0]


# ------------------------------------------------------------------ cuentas puras
@pytest.mark.parametrize("duracion, anual", [(30, 12), (7, 52), (365, 1), (90, 4), (1, 365), (180, 2)])
def test_periodos_anuales_segun_la_duracion_del_plan(duracion, anual):
    assert payments.periodos_anuales(duracion) == anual


def test_descuento_anual_por_porcentaje_monto_y_sin_descuento():
    assert payments.descuento_anual(PRECIO, 12, "porcentaje", 10) == 3000000
    assert payments.descuento_anual(PRECIO, 12, "monto", 2000000) == 2000000
    assert payments.descuento_anual(PRECIO, 12, None, None) == 0
    assert payments.descuento_anual(PRECIO, 12, "monto", PRECIO * 12) == 0     # un descuento que deja el pago en cero no vale


# ------------------------------------------------------------ varios períodos (servicio)
def test_un_periodo_sigue_igual_que_siempre(db, plan, crear_socio):
    socio_id = _socio_al_dia(db, plan, crear_socio)
    r = payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    assert r["periodos_cubiertos"] == 1 and r["saldo_a_favor_centavos"] == 0
    assert _vence(db, socio_id) == (HOY + 40 * DIA).isoformat()


def test_dos_periodos_exactos_no_piden_confirmacion_y_suman_60_dias(db, plan, crear_socio):
    socio_id = _socio_al_dia(db, plan, crear_socio)                       # vence HOY + 10

    r = payments.registrar_pago(db, socio_id, 2 * PRECIO, HOY, "transferencia")

    assert r["periodos_cubiertos"] == 2
    assert r["vencimiento_anterior"] == HOY + 10 * DIA and r["vencimiento_nuevo"] == HOY + 70 * DIA
    assert r["saldo_pendiente_centavos"] == 0 and r["saldo_a_favor_centavos"] == 0
    assert _vence(db, socio_id) == (HOY + 70 * DIA).isoformat()


def test_doce_periodos_suman_360_dias(db, plan, crear_socio):
    socio_id = _socio_al_dia(db, plan, crear_socio)

    r = payments.registrar_pago(db, socio_id, 12 * PRECIO, HOY, "efectivo")

    assert r["periodos_cubiertos"] == 12
    assert _vence(db, socio_id) == (HOY + 370 * DIA).isoformat()           # 10 que ya tenía + 12 x 30


def test_el_primer_pago_de_dos_periodos_cubre_el_inicial_y_uno_mas(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY - 20 * DIA)           # vence HOY + 10, sin pagos

    r = payments.registrar_pago(db, socio_id, 2 * PRECIO, HOY, "efectivo")

    assert r["periodos_cubiertos"] == 2
    assert _vence(db, socio_id) == (HOY + 40 * DIA).isoformat()           # el inicial no suma días, el segundo sí


def test_una_membresia_vencida_cuenta_los_periodos_desde_la_fecha_del_pago(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY - 100 * DIA)          # venció hace 70 días
    payments.registrar_pago(db, socio_id, PRECIO, HOY - 90 * DIA, "efectivo")

    payments.registrar_pago(db, socio_id, 3 * PRECIO, HOY, "efectivo")

    assert _vence(db, socio_id) == (HOY + 90 * DIA).isoformat()


# ----------------------------------------------------- monto que no es múltiplo exacto
def test_monto_de_mas_pide_confirmacion_y_no_guarda_nada(db, crear_socio):
    plan23 = _plan(db, "Mensual 23", precio=2300000)
    socio_id = _socio_al_dia(db, plan23, crear_socio)

    with pytest.raises(RequiereConfirmacion) as e:
        payments.registrar_pago(db, socio_id, 5000000, HOY, "efectivo")     # $ 50.000 en un plan de $ 23.000

    assert e.value.codigo == "pago_sobrante"
    assert e.value.datos["periodos_cubiertos"] == 2
    assert e.value.datos["sobrante_centavos"] == 400000                    # sobran $ 4.000
    assert e.value.datos["faltante_proximo_centavos"] == 1900000           # y faltan $ 19.000 para el tercero
    assert "cubre 2 período" in str(e.value) and "$ 4.000" in str(e.value)
    assert _n_pagos(db, socio_id) == 1                                     # solo el pago inicial
    assert _vence(db, socio_id) == (HOY + 10 * DIA).isoformat()


def test_monto_de_mas_confirmado_deja_saldo_a_favor_y_lo_siguiente_lo_aprovecha(db, crear_socio):
    plan23 = _plan(db, "Mensual 23", precio=2300000)
    socio_id = _socio_al_dia(db, plan23, crear_socio)

    r = payments.registrar_pago(db, socio_id, 5000000, HOY, "efectivo", confirmar=True)

    assert r["periodos_cubiertos"] == 2 and r["es_parcial"] is False
    assert r["saldo_a_favor_centavos"] == 400000 and r["saldo_pendiente_centavos"] == 0
    assert _vence(db, socio_id) == (HOY + 70 * DIA).isoformat()
    assert payments.saldo_del_socio(db, socio_id) == 0                     # el sobrante no es deuda
    # con el saldo a favor, para el período siguiente alcanzan $ 19.000 (exacto: sin confirmación)
    r = payments.registrar_pago(db, socio_id, 1900000, HOY, "efectivo")
    assert r["periodos_cubiertos"] == 1 and r["saldo_a_favor_centavos"] == 0
    assert _vence(db, socio_id) == (HOY + 100 * DIA).isoformat()


def test_tres_periodos_y_medio_cubren_tres_y_dejan_medio_a_favor(db, plan, crear_socio):
    socio_id = _socio_al_dia(db, plan, crear_socio)
    with pytest.raises(RequiereConfirmacion) as e:
        payments.registrar_pago(db, socio_id, 8750000, HOY, "efectivo")
    assert e.value.datos["periodos_cubiertos"] == 3
    assert e.value.datos["sobrante_centavos"] == 1250000 and e.value.datos["faltante_proximo_centavos"] == 1250000


def test_monto_de_menos_sigue_siendo_pago_parcial(db, plan, crear_socio):
    socio_id = _socio_al_dia(db, plan, crear_socio)

    with pytest.raises(RequiereConfirmacion) as e:
        payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo")

    assert e.value.codigo == "pago_parcial"
    assert e.value.datos["faltante_centavos"] == PRECIO and e.value.datos["periodos_cubiertos"] == 0
    assert e.value.datos["faltante_proximo_centavos"] == 1500000
    r = payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo", confirmar_parcial=True)   # nombre anterior
    assert r["es_parcial"] is True and r["saldo_pendiente_centavos"] == 1500000
    assert r["saldo_a_favor_centavos"] == 0 and _vence(db, socio_id) == (HOY + 10 * DIA).isoformat()


def test_previsualizar_no_escribe_nada(db, plan, crear_socio):
    socio_id = _socio_al_dia(db, plan, crear_socio)
    membresia = models.membresia_actual(db, socio_id)

    vista = payments.previsualizar_pago(db, membresia["id"], 3 * PRECIO, HOY)

    assert vista.exacto and vista.periodos_cubiertos == 3 and vista.vencimiento_nuevo == HOY + 100 * DIA
    assert _n_pagos(db, socio_id) == 1 and _vence(db, socio_id) == (HOY + 10 * DIA).isoformat()


# ------------------------------------------------------------------- pago anual
def test_pago_anual_con_descuento_porcentual(db, crear_socio):
    plan10 = _plan(db, "Mensual -10% anual", tipo="porcentaje", valor=10)
    socio_id = _socio_al_dia(db, plan10, crear_socio)

    r = payments.registrar_pago(db, socio_id, 27000000, HOY, "transferencia", anual=True)  # 12 x 25.000 - 10%

    assert r["periodos_cubiertos"] == 12 and r["descuento_centavos"] == 3000000
    assert r["saldo_pendiente_centavos"] == 0 and r["saldo_a_favor_centavos"] == 0
    assert _vence(db, socio_id) == (HOY + 370 * DIA).isoformat()
    pago = models.obtener_pago(db, r["pago_id"])
    assert pago["monto_centavos"] == 27000000 and pago["descuento_centavos"] == 3000000
    # la caja suma la plata que entró de verdad (el pago inicial + el anual), no el descuento
    assert caja.cuotas_del_dia(db, HOY)["total_centavos"] == PRECIO + 27000000


def test_pago_anual_con_descuento_de_monto_fijo(db, crear_socio):
    plan_fijo = _plan(db, "Mensual -20000", tipo="monto", valor=2000000)
    socio_id = _socio_al_dia(db, plan_fijo, crear_socio)

    r = payments.registrar_pago(db, socio_id, 28000000, HOY, "efectivo", anual=True)

    assert r["periodos_cubiertos"] == 12 and r["descuento_centavos"] == 2000000
    assert _vence(db, socio_id) == (HOY + 370 * DIA).isoformat()


def test_el_descuento_anual_no_se_aplica_si_el_monto_no_alcanza(db, crear_socio):
    plan10 = _plan(db, "Mensual -10% anual", tipo="porcentaje", valor=10)
    socio_id = _socio_al_dia(db, plan10, crear_socio)

    with pytest.raises(RequiereConfirmacion) as e:
        payments.registrar_pago(db, socio_id, 26000000, HOY, "efectivo", anual=True)   # $ 1.000 menos que el anual con descuento

    assert e.value.datos["descuento_centavos"] == 0
    assert e.value.datos["periodos_cubiertos"] == 10 and e.value.datos["sobrante_centavos"] == 1000000


def test_el_descuento_anual_solo_vale_si_se_elige_anual(db, crear_socio):
    plan10 = _plan(db, "Mensual -10% anual", tipo="porcentaje", valor=10)
    socio_id = _socio_al_dia(db, plan10, crear_socio)
    with pytest.raises(RequiereConfirmacion) as e:          # 12 períodos "comunes" por el monto con descuento: no cierra
        payments.registrar_pago(db, socio_id, 27000000, HOY, "efectivo")
    assert e.value.datos["descuento_centavos"] == 0 and e.value.datos["periodos_cubiertos"] == 10


def test_pago_anual_en_un_plan_sin_descuento_son_doce_periodos_al_precio_completo(db, plan, crear_socio):
    socio_id = _socio_al_dia(db, plan, crear_socio)
    r = payments.registrar_pago(db, socio_id, 12 * PRECIO, HOY, "efectivo", anual=True)
    assert r["descuento_centavos"] == 0 and r["periodos_cubiertos"] == 12


def test_el_saldo_a_favor_cuenta_para_el_pago_anual(db, crear_socio):
    plan10 = _plan(db, "Mensual -10% anual", tipo="porcentaje", valor=10)
    socio_id = _socio_al_dia(db, plan10, crear_socio)
    payments.registrar_pago(db, socio_id, 3500000, HOY, "efectivo", confirmar=True)    # 1 período + $ 10.000 a favor
    # al anual le faltan 270.000 - 10.000 = 260.000 (exacto: sin confirmación)
    r = payments.registrar_pago(db, socio_id, 26000000, HOY, "efectivo", anual=True)
    assert r["periodos_cubiertos"] == 12 and r["descuento_centavos"] == 3000000
    assert r["saldo_a_favor_centavos"] == 0


# ------------------------------------------------------------------ opciones del formulario
def test_opciones_de_periodos_calculan_precio_por_periodos(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY)
    m = models.membresia_actual(db, socio_id)

    opciones = payments.opciones_de_periodos(m, payments.reproducir(db, m["id"]))

    assert [o["valor"] for o in opciones] == ["1", "2", "3", "6", "12", "anual"]
    assert [o["monto_centavos"] for o in opciones] == [PRECIO * n for n in (1, 2, 3, 6, 12, 12)]
    assert opciones[-1]["periodos"] == 12 and opciones[-1]["descuento_centavos"] == 0


def test_opciones_de_periodos_con_descuento_y_con_un_parcial_a_medio_completar(db, crear_socio):
    plan10 = _plan(db, "Mensual -10% anual", tipo="porcentaje", valor=10)
    socio_id = _socio_al_dia(db, plan10, crear_socio)
    payments.registrar_pago(db, socio_id, 1000000, HOY, "efectivo", confirmar=True)   # parcial de $ 10.000
    m = models.membresia_actual(db, socio_id)

    opciones = {o["valor"]: o for o in payments.opciones_de_periodos(m, payments.reproducir(db, m["id"]))}

    assert opciones["1"]["monto_centavos"] == 1500000                      # lo que falta, no el precio entero
    assert opciones["2"]["monto_centavos"] == 4000000
    assert opciones["anual"]["descuento_centavos"] == 3000000
    assert opciones["anual"]["monto_centavos"] == 27000000 - 1000000


# ------------------------------------------------------------------------- anulaciones
def test_anular_un_pago_de_doce_periodos_recalcula_el_vencimiento(db, plan, crear_socio):
    socio_id = _socio_al_dia(db, plan, crear_socio)
    grande = payments.registrar_pago(db, socio_id, 12 * PRECIO, HOY, "efectivo")["pago_id"]
    assert _vence(db, socio_id) == (HOY + 370 * DIA).isoformat()

    r = payments.anular_pago(db, grande, "Se cargó por error", "admin")

    assert r["vencimiento"] == HOY + 10 * DIA and _vence(db, socio_id) == (HOY + 10 * DIA).isoformat()
    assert payments.saldo_del_socio(db, socio_id) == 0


def test_anular_un_pago_anual_con_descuento_saca_tambien_el_descuento(db, crear_socio):
    plan10 = _plan(db, "Mensual -10% anual", tipo="porcentaje", valor=10)
    socio_id = _socio_al_dia(db, plan10, crear_socio)
    anual = payments.registrar_pago(db, socio_id, 27000000, HOY, "efectivo", anual=True)["pago_id"]

    payments.anular_pago(db, anual, "Era otro socio", "admin")

    assert _vence(db, socio_id) == (HOY + 10 * DIA).isoformat()
    assert caja.cuotas_del_dia(db, HOY)["total_centavos"] == PRECIO        # lo anulado no suma
    assert payments.reproducir(db, models.membresia_actual(db, socio_id)["id"]).saldo_a_favor_centavos == 0


def test_anular_el_pago_del_medio_reordena_los_siguientes(db, plan, crear_socio):
    socio_id = _socio_al_dia(db, plan, crear_socio)
    dos = payments.registrar_pago(db, socio_id, 2 * PRECIO, HOY, "efectivo")["pago_id"]       # +60
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")                              # +30
    assert _vence(db, socio_id) == (HOY + 100 * DIA).isoformat()

    payments.anular_pago(db, dos, "Error de carga", "admin")

    assert _vence(db, socio_id) == (HOY + 40 * DIA).isoformat()


def test_anular_el_pago_con_sobrante_quita_el_saldo_a_favor(db, crear_socio):
    plan23 = _plan(db, "Mensual 23", precio=2300000)
    socio_id = _socio_al_dia(db, plan23, crear_socio)
    pago = payments.registrar_pago(db, socio_id, 5000000, HOY, "efectivo", confirmar=True)["pago_id"]

    payments.anular_pago(db, pago, "Error", "admin")

    estado = payments.reproducir(db, models.membresia_actual(db, socio_id)["id"])
    assert estado.saldo_a_favor_centavos == 0 and estado.vencimiento == HOY + 10 * DIA


# ---------------------------------------------------------- validación del plan (descuento)
def _form_plan(**extra):
    return dict(nombre="Mensual", precio="25000", duracion_dias="30", ilimitado="1", **extra)


def test_plan_sin_descuento_por_defecto(db):
    datos, errores = validar_plan(db, _form_plan())
    assert errores == {} and datos["descuento_anual_tipo"] is None and datos["descuento_anual_valor"] is None


def test_plan_con_descuento_porcentual_y_con_monto_fijo(db):
    datos, errores = validar_plan(db, _form_plan(descuento_tipo="porcentaje", descuento_valor="10"))
    assert errores == {} and (datos["descuento_anual_tipo"], datos["descuento_anual_valor"]) == ("porcentaje", 10)
    datos, errores = validar_plan(db, _form_plan(descuento_tipo="monto", descuento_valor="20.000"))
    assert errores == {} and (datos["descuento_anual_tipo"], datos["descuento_anual_valor"]) == ("monto", 2000000)


@pytest.mark.parametrize("tipo, valor", [("porcentaje", "0"), ("porcentaje", "100"), ("porcentaje", "abc"),
                                         ("porcentaje", "10,5"), ("porcentaje", ""), ("monto", "0"), ("monto", "xx"),
                                         ("monto", "300000"), ("monto", "-5")])
def test_plan_rechaza_descuentos_invalidos(db, tipo, valor):
    _, errores = validar_plan(db, _form_plan(descuento_tipo=tipo, descuento_valor=valor))
    assert "descuento_valor" in errores


def test_plan_rechaza_un_tipo_de_descuento_desconocido(db):
    _, errores = validar_plan(db, _form_plan(descuento_tipo="regalo", descuento_valor="10"))
    assert "descuento_tipo" in errores


def test_monto_fijo_justo_por_debajo_del_precio_anual_es_valido(db):
    datos, errores = validar_plan(db, _form_plan(descuento_tipo="monto", descuento_valor="299999"))
    assert errores == {} and datos["descuento_anual_valor"] == 29999900


# ------------------------------------------------------------------------------ pantallas
def _socio_pantalla(db, plan, crear_socio, **kw):
    """Socio con el período inicial pago, a fecha real (las pantallas usan la fecha de hoy)."""
    socio_id = crear_socio(**kw)
    memberships.asignar_plan(db, socio_id, plan, hoy_real() - 20 * DIA)
    payments.registrar_pago(db, socio_id, models.membresia_actual(db, socio_id)["precio_centavos"], hoy_real(), "efectivo")
    return socio_id


def _post(nav, socio_id, monto, periodos="1", **extra):
    datos = {"socio_id": socio_id, "monto": monto, "periodos": periodos, "fecha": hoy_real().isoformat(),
             "metodo": "efectivo", **extra}
    return nav.post(f"/pagos/nuevo?socio_id={socio_id}", datos)


def test_el_formulario_ofrece_los_periodos_y_calcula_el_monto_de_cada_uno(nav, db, plan, crear_socio):
    socio_id = _socio_pantalla(db, plan, crear_socio)

    html = nav.get(f"/pagos/nuevo?socio_id={socio_id}").get_data(as_text=True)

    assert "Cuántos períodos paga" in html
    for valor, monto in [("1", "25000"), ("2", "50000"), ("3", "75000"), ("6", "150000"), ("12", "300000"), ("anual", "300000")]:
        assert f'<option value="{valor}" data-monto="{monto}"' in html
    assert "Anual (12 períodos)" in html and "js/pagos.js" in html
    assert 'value="25000"' in html                                         # el monto precargado es el de 1 período


def test_el_formulario_marca_el_descuento_anual(nav, db, crear_socio):
    plan10 = _plan(db, "Mensual -10% anual", tipo="porcentaje", valor=10)
    socio_id = _socio_pantalla(db, plan10, crear_socio)
    html = nav.get(f"/pagos/nuevo?socio_id={socio_id}").get_data(as_text=True)
    assert 'data-monto="270000" data-descuento="$ 30.000"' in html and "con descuento" in html


def test_monto_de_mas_muestra_la_pantalla_de_confirmacion_y_no_guarda(nav, db, crear_socio):
    plan23 = _plan(db, "Mensual 23", precio=2300000)
    socio_id = _socio_pantalla(db, plan23, crear_socio, nombre="Eva Sosa", dni="35111111")

    r = _post(nav, socio_id, "50.000")
    html = r.get_data(as_text=True)

    assert r.status_code == 200
    assert "Confirmar pago" in html and "El monto no es un múltiplo exacto del precio" in html
    assert "Esto cubre" in html and "2 períodos" in html and "sobra" in html and "$ 4.000" in html and "a favor" in html
    assert "Vencimiento actual" in html and "Vencimiento nuevo" in html
    assert 'name="confirmar" value="1"' in html and "Confirmar pago de $ 50.000" in html
    assert _n_pagos(db, socio_id) == 1


def test_confirmar_el_monto_de_mas_registra_y_muestra_el_resultado_y_el_saldo_a_favor(nav, db, crear_socio):
    plan23 = _plan(db, "Mensual 23", precio=2300000)
    socio_id = _socio_pantalla(db, plan23, crear_socio, nombre="Eva Sosa", dni="35111111")
    antes = _vence(db, socio_id)

    r = _post(nav, socio_id, "50.000", confirmar="1")
    assert r.status_code == 302 and f"/socios/{socio_id}" in r.headers["Location"]
    html = nav.get(r.headers["Location"]).get_data(as_text=True)

    assert _n_pagos(db, socio_id) == 2 and _vence(db, socio_id) != antes
    assert 'id="resultado-pago"' in html and "Pago registrado: $ 50.000" in html
    assert "Vencimiento anterior" in html and "Vencimiento nuevo" in html and "Períodos cubiertos" in html
    assert "A favor: $ 4.000" in html                                      # en la tarjeta del resultado
    assert 'id="saldo-a-favor"' in html and "Saldo a favor: $ 4.000" in html   # y en la ficha del socio
    assert "Saldo pendiente" not in html


def test_el_resultado_muestra_vencimiento_anterior_y_nuevo_reales(nav, db, plan, crear_socio):
    socio_id = _socio_pantalla(db, plan, crear_socio)                     # vence hoy + 10
    r = _post(nav, socio_id, "75.000", periodos="3")
    html = nav.get(r.headers["Location"]).get_data(as_text=True)
    anterior = (hoy_real() + 10 * DIA).strftime("%d/%m/%Y")
    nuevo = (hoy_real() + 100 * DIA).strftime("%d/%m/%Y")
    assert anterior in html and f"<strong>{nuevo}</strong>" in html
    assert "Al día: sin saldo" in html


def test_monto_de_menos_pide_confirmar_y_dice_cuanto_falta(nav, db, crear_socio):
    plan23 = _plan(db, "Mensual 23", precio=2300000)
    socio_id = _socio_pantalla(db, plan23, crear_socio)

    html = _post(nav, socio_id, "10.000").get_data(as_text=True)

    assert "Este pago es menor a lo que falta" in html and "Confirmar pago parcial" in html
    assert "Falta $ 13.000 para el próximo período" in html and 'name="confirmar_parcial"' in html
    assert _n_pagos(db, socio_id) == 1


def test_volver_y_corregir_devuelve_el_formulario_con_lo_escrito(nav, db, crear_socio):
    plan23 = _plan(db, "Mensual 23", precio=2300000)
    socio_id = _socio_pantalla(db, plan23, crear_socio)

    html = _post(nav, socio_id, "50.000", periodos="2", confirmar="1", corregir="1").get_data(as_text=True)

    assert 'value="50.000"' in html and "Registrar pago" in html and "Confirmar pago" not in html
    assert _n_pagos(db, socio_id) == 1


def test_pago_anual_por_pantalla_aplica_el_descuento_y_lo_muestra(nav, db, crear_socio):
    plan10 = _plan(db, "Mensual -10% anual", tipo="porcentaje", valor=10)
    socio_id = _socio_pantalla(db, plan10, crear_socio)

    r = _post(nav, socio_id, "270.000", periodos="anual")
    assert r.status_code == 302                                           # exacto: sin pantalla de confirmación
    html = nav.get(r.headers["Location"]).get_data(as_text=True)

    pago = db.execute("SELECT * FROM pagos WHERE socio_id = ? ORDER BY id DESC LIMIT 1", (socio_id,)).fetchone()
    assert pago["monto_centavos"] == 27000000 and pago["descuento_centavos"] == 3000000
    assert "incluye descuento por pago anual de $ 30.000" in html and "Períodos cubiertos" in html
    assert (hoy_real() + 370 * DIA).strftime("%d/%m/%Y") in html


def test_sin_monto_escrito_se_usa_el_calculado_para_los_periodos(nav, db, plan, crear_socio):
    socio_id = _socio_pantalla(db, plan, crear_socio)
    r = _post(nav, socio_id, "", periodos="3")
    assert r.status_code == 302
    ultimo = db.execute("SELECT monto_centavos FROM pagos WHERE socio_id = ? ORDER BY id DESC LIMIT 1", (socio_id,)).fetchone()
    assert ultimo["monto_centavos"] == 3 * PRECIO


def test_periodos_invalidos_se_rechazan_sin_guardar(nav, db, plan, crear_socio):
    socio_id = _socio_pantalla(db, plan, crear_socio)
    html = _post(nav, socio_id, "25.000", periodos="7").get_data(as_text=True)
    assert "Elegí cuántos períodos paga" in html and _n_pagos(db, socio_id) == 1


def test_la_tarjeta_de_resultado_no_se_muestra_con_el_pago_de_otro_socio(nav, db, plan, crear_socio):
    uno = _socio_pantalla(db, plan, crear_socio, nombre="Uno Uno", dni="35000010")
    otro = _socio_pantalla(db, plan, crear_socio, nombre="Otro Otro", dni="35000011")
    pago_de_uno = db.execute("SELECT id FROM pagos WHERE socio_id = ?", (uno,)).fetchone()["id"]
    assert 'id="resultado-pago"' not in nav.get(f"/socios/{otro}?pago={pago_de_uno}").get_data(as_text=True)
    assert 'id="resultado-pago"' in nav.get(f"/socios/{uno}?pago={pago_de_uno}").get_data(as_text=True)


def test_un_pago_anulado_no_muestra_tarjeta_de_resultado(nav, db, plan, crear_socio):
    socio_id = _socio_pantalla(db, plan, crear_socio)
    pago = db.execute("SELECT id FROM pagos WHERE socio_id = ?", (socio_id,)).fetchone()["id"]
    payments.anular_pago(db, pago, "Error", "admin")
    assert 'id="resultado-pago"' not in nav.get(f"/socios/{socio_id}?pago={pago}").get_data(as_text=True)


def test_recepcion_tambien_cobra_varios_periodos_con_confirmacion(nav_recepcion, db, plan, crear_socio):
    socio_id = _socio_pantalla(db, plan, crear_socio)
    html = _post(nav_recepcion, socio_id, "35.000").get_data(as_text=True)         # 1 período + $ 10.000
    assert "Esto cubre" in html and "1 período" in html and "$ 10.000" in html
    r = _post(nav_recepcion, socio_id, "35.000", confirmar="1")
    assert r.status_code == 302
    cargado = db.execute("SELECT cargado_por FROM pagos WHERE socio_id = ? ORDER BY id DESC LIMIT 1", (socio_id,)).fetchone()
    assert cargado["cargado_por"] == "recepcion"


# ------------------------------------------------------- pantalla de planes (descuento)
def test_el_administrador_configura_el_descuento_anual_en_el_plan(nav, db, plan):
    r = nav.post(f"/planes/{plan}/editar", {"nombre": "Mensual", "precio": "25000", "duracion_dias": "30",
                                            "ilimitado": "1", "descuento_tipo": "porcentaje", "descuento_valor": "10"})
    assert r.status_code == 302
    p = models.obtener_plan(db, plan)
    assert (p["descuento_anual_tipo"], p["descuento_anual_valor"]) == ("porcentaje", 10)
    assert "Anual: 10% de descuento" in nav.get("/planes/").get_data(as_text=True)
    form = nav.get(f"/planes/{plan}/editar").get_data(as_text=True)
    assert '<option value="porcentaje" selected>' in form and 'value="10"' in form


def test_el_plan_muestra_el_error_de_un_descuento_invalido_y_no_guarda(nav, db, plan):
    html = nav.post(f"/planes/{plan}/editar", {"nombre": "Mensual", "precio": "25000", "duracion_dias": "30",
                                              "ilimitado": "1", "descuento_tipo": "porcentaje",
                                              "descuento_valor": "150"}).get_data(as_text=True)
    assert "entre 1 y 99" in html
    assert models.obtener_plan(db, plan)["descuento_anual_tipo"] is None


def test_crear_un_plan_nuevo_con_descuento_de_monto_fijo(nav, db):
    r = nav.post("/planes/nuevo", {"nombre": "Trimestral", "precio": "60000", "duracion_dias": "90", "ilimitado": "1",
                                   "descuento_tipo": "monto", "descuento_valor": "20.000"})
    assert r.status_code == 302
    p = db.execute("SELECT * FROM planes WHERE nombre = 'Trimestral'").fetchone()
    assert (p["descuento_anual_tipo"], p["descuento_anual_valor"]) == ("monto", 2000000)
    assert "Anual: $ 20.000 de descuento" in nav.get("/planes/").get_data(as_text=True)


def test_recepcion_no_puede_configurar_descuentos(nav_recepcion, plan):
    r = nav_recepcion.post(f"/planes/{plan}/editar", {"nombre": "Mensual", "precio": "25000", "duracion_dias": "30",
                                                      "ilimitado": "1", "descuento_tipo": "porcentaje",
                                                      "descuento_valor": "10"})
    assert r.status_code in (302, 403)


# ---------------------------------------------------------------------------- migración
def test_la_migracion_agrega_las_columnas_sin_tocar_los_datos(tmp_path):
    conn = dbm.connect(str(tmp_path / "previa.db"))
    conn.executescript(dbm.SCHEMA.read_text(encoding="utf-8"))
    for numero, sql in migraciones.MIGRACIONES:
        if numero < 6:                                                    # la base como estaba antes de esta tarea (V6; era V5 antes de unir con las cuentas de usuario)
            conn.executescript(sql)
    conn.executescript("""
        INSERT INTO planes (id, nombre, precio_centavos, duracion_dias) VALUES (1, 'Mensual', 2500000, 30);
        INSERT INTO socios (id, nombre, dni, telefono, fecha_alta, creado_en) VALUES (1, 'Ana', '30111222', '11 5555-1234', '2026-10-01', 'x');
        INSERT INTO membresias (id, socio_id, plan_id, fecha_inicio, fecha_vencimiento, creada_en, duracion_dias, precio_centavos)
            VALUES (1, 1, 1, '2026-10-01', '2026-10-31', 'x', 30, 2500000);
        INSERT INTO pagos (id, socio_id, membresia_id, monto_centavos, fecha, metodo, vencimiento_anterior, vencimiento_nuevo, creado_en)
            VALUES (1, 1, 1, 2500000, '2026-10-01', 'efectivo', '2026-10-31', '2026-10-31', 'x');
    """)
    conn.commit()
    assert migraciones.version(conn) == 5

    assert migraciones.aplicar(conn) == migraciones.VERSION_ACTUAL >= 6

    pago = conn.execute("SELECT * FROM pagos WHERE id = 1").fetchone()
    plan = conn.execute("SELECT * FROM planes WHERE id = 1").fetchone()
    assert pago["monto_centavos"] == 2500000 and pago["descuento_centavos"] == 0
    assert plan["descuento_anual_tipo"] is None and plan["descuento_anual_valor"] is None
    assert payments.reproducir(conn, 1).vencimiento.isoformat() == "2026-10-31"
    conn.close()
