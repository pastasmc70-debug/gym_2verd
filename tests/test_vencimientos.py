"""Cálculo de vencimientos y estado de las membresías."""
from datetime import date

import pytest

from app import models
from app.services import memberships
from app.services.errors import ErrorDeNegocio
from conftest import HOY


def test_vencimiento_es_inicio_mas_duracion():
    assert memberships.calcular_vencimiento(date(2026, 10, 1), 30) == date(2026, 10, 31)


@pytest.mark.parametrize("inicio, dias, esperado", [
    (date(2026, 1, 31), 30, date(2026, 3, 2)),    # cruza febrero
    (date(2026, 2, 1), 30, date(2026, 3, 3)),     # febrero de 28 días
    (date(2028, 2, 1), 30, date(2028, 3, 2)),     # año bisiesto
    (date(2026, 12, 15), 30, date(2027, 1, 14)),  # cruza de año
    (date(2026, 10, 25), 7, date(2026, 11, 1)),   # plan semanal
    (date(2026, 10, 25), 90, date(2027, 1, 23)),  # plan trimestral
])
def test_vencimiento_en_casos_de_calendario(inicio, dias, esperado):
    assert memberships.calcular_vencimiento(inicio, dias) == esperado


@pytest.mark.parametrize("vencimiento, esperado", [
    (date(2026, 10, 24), models.VENCIDA),      # venció ayer
    (date(2026, 9, 1), models.VENCIDA),
    (date(2026, 10, 25), models.POR_VENCER),   # vence hoy: todavía puede entrar
    (date(2026, 11, 1), models.POR_VENCER),    # faltan 7 días: justo en el límite
    (date(2026, 11, 2), models.VIGENTE),       # faltan 8 días
    (date(2027, 3, 1), models.VIGENTE),
    (None, models.SIN_MEMBRESIA),
])
def test_estado_de_la_membresia(vencimiento, esperado):
    assert memberships.estado_membresia(vencimiento, HOY) == esperado


def test_estado_acepta_fecha_como_texto_iso():
    assert memberships.estado_membresia("2026-10-20", HOY) == models.VENCIDA


def test_ventana_de_alerta_es_configurable():
    assert memberships.estado_membresia(date(2026, 11, 5), HOY, dias_alerta=15) == models.POR_VENCER
    assert memberships.estado_membresia(date(2026, 11, 5), HOY, dias_alerta=7) == models.VIGENTE


def test_asignar_plan_guarda_el_vencimiento_calculado(db, plan, crear_socio):
    socio_id = crear_socio()
    r = memberships.asignar_plan(db, socio_id, plan, date(2026, 10, 1))
    assert r["fecha_vencimiento"] == date(2026, 10, 31)
    guardada = models.membresia_actual(db, socio_id)
    assert guardada["fecha_inicio"] == "2026-10-01"
    assert guardada["fecha_vencimiento"] == "2026-10-31"


def test_la_membresia_actual_es_la_mas_reciente(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, date(2026, 1, 1))
    memberships.asignar_plan(db, socio_id, plan, date(2026, 10, 1))
    assert models.membresia_actual(db, socio_id)["fecha_inicio"] == "2026-10-01"
    assert len(models.historial_membresias(db, socio_id)) == 2


def test_no_se_asigna_plan_a_un_socio_de_baja(db, plan, crear_socio):
    socio_id = crear_socio(estado="baja")
    with pytest.raises(ErrorDeNegocio, match="dado de baja"):
        memberships.asignar_plan(db, socio_id, plan, HOY)


def test_no_se_asigna_un_plan_inexistente(db, crear_socio):
    with pytest.raises(ErrorDeNegocio, match="plan válido"):
        memberships.asignar_plan(db, crear_socio(), 999, HOY)
