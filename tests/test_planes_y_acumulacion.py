"""Baja lógica de planes y acumulación de días al reasignar un plan."""
from datetime import timedelta

import pytest

from app import models
from app.services import memberships, payments
from app.services.errors import ErrorDeNegocio
from conftest import HOY, hoy_real


# ------------------------------------------------------------------ 6. planes activos
def test_un_plan_desactivado_no_se_puede_asignar(db, plan, crear_socio):
    with db:
        models.cambiar_activo_plan(db, plan, False)
    with pytest.raises(ErrorDeNegocio) as e:
        memberships.asignar_plan(db, crear_socio(), plan, HOY)
    assert e.value.codigo == "plan_inactivo" and "desactivado" in str(e.value)


def test_listar_planes_solo_activos(db, plan):
    with db:
        otro = models.crear_plan(db, dict(nombre="Otro", precio_centavos=100, duracion_dias=30, clases_por_semana=None))
        models.cambiar_activo_plan(db, otro, False)
    assert [p["nombre"] for p in models.listar_planes(db)] == ["Otro", "Mensual"]
    assert [p["nombre"] for p in models.listar_planes(db, solo_activos=True)] == ["Mensual"]


def test_desactivar_no_borra_ni_toca_a_los_socios_que_ya_lo_tienen(nav, db, plan, crear_socio):
    socio_id = crear_socio(nombre="Con Plan", dni="37000001")
    memberships.asignar_plan(db, socio_id, plan, hoy_real())
    vence = models.obtener_socio(db, socio_id)["fecha_vencimiento"]

    r = nav.post(f"/planes/{plan}/desactivar", follow_redirects=True)

    assert "desactivado" in r.get_data(as_text=True)
    assert models.obtener_plan(db, plan)["activo"] == 0
    socio = models.obtener_socio(db, socio_id)
    assert socio["plan_nombre"] == "Mensual" and socio["fecha_vencimiento"] == vence
    # y puede seguir pagando su plan
    payments.registrar_pago(db, socio_id, 2500000, hoy_real(), "efectivo")


def test_un_plan_desactivado_no_aparece_al_asignar_y_se_puede_reactivar(nav, db, plan, crear_socio):
    socio_id = crear_socio(nombre="Sin Plan", dni="37000002")
    with db:
        otro = models.crear_plan(db, dict(nombre="Trimestral", precio_centavos=6000000, duracion_dias=90, clases_por_semana=None))
    nav.post(f"/planes/{plan}/desactivar")

    html = nav.get(f"/socios/{socio_id}/membresia").get_data(as_text=True)
    assert "Trimestral" in html and "Mensual —" not in html

    nav.post(f"/planes/{otro}/desactivar")
    assert "No hay planes activos" in nav.get(f"/socios/{socio_id}/membresia").get_data(as_text=True)

    nav.post(f"/planes/{plan}/activar")
    assert "Mensual —" in nav.get(f"/socios/{socio_id}/membresia").get_data(as_text=True)


def test_por_pantalla_no_se_puede_asignar_un_plan_desactivado_aunque_se_fuerce_el_formulario(nav, db, plan, crear_socio):
    socio_id = crear_socio(nombre="Forzado", dni="37000003")
    nav.post(f"/planes/{plan}/desactivar")
    html = nav.post(f"/socios/{socio_id}/membresia", {"plan_id": plan, "fecha_inicio": hoy_real().isoformat()},
                    follow_redirects=True).get_data(as_text=True)
    assert "está desactivado" in html
    assert models.membresia_actual(db, socio_id) is None


def test_la_lista_de_planes_marca_el_estado(nav, db, plan):
    assert "Activo" in nav.get("/planes/").get_data(as_text=True)
    nav.post(f"/planes/{plan}/desactivar")
    html = nav.get("/planes/").get_data(as_text=True)
    assert "Desactivado" in html and "Activar" in html


def test_accion_invalida_sobre_un_plan(nav, plan):
    assert nav.post(f"/planes/{plan}/borrar_todo").status_code == 404
    assert nav.post("/planes/999/desactivar").status_code == 404


def test_un_plan_en_uso_sigue_sin_poder_eliminarse(nav, db, plan, crear_socio):
    memberships.asignar_plan(db, crear_socio(), plan, HOY)
    html = nav.post(f"/planes/{plan}/eliminar", follow_redirects=True).get_data(as_text=True)
    assert "No se puede eliminar" in html and models.obtener_plan(db, plan) is not None


# -------------------------------------------------------------- 7. acumular días
def test_dias_vigentes_a_acumular(db, plan, crear_socio):
    socio_id = crear_socio()
    assert memberships.dias_vigentes_a_acumular(db, socio_id, HOY) == 0          # sin membresía
    memberships.asignar_plan(db, socio_id, plan, HOY - timedelta(days=10))       # vence en 20 días
    assert memberships.dias_vigentes_a_acumular(db, socio_id, HOY) == 20
    assert memberships.dias_vigentes_a_acumular(db, socio_id, HOY + timedelta(days=5)) == 15   # contados desde el nuevo inicio
    assert memberships.dias_vigentes_a_acumular(db, socio_id, HOY + timedelta(days=40)) == 0   # ya vencida para entonces


def test_acumular_suma_los_dias_restantes_al_plan_nuevo(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY - timedelta(days=10))       # vence en 20 días

    r = memberships.asignar_plan(db, socio_id, plan, HOY, acumular=True)

    assert r["dias_acumulados"] == 20
    assert r["fecha_vencimiento"] == HOY + timedelta(days=50)                    # 30 del plan + 20 que le quedaban
    assert models.obtener_socio(db, socio_id)["dias_extra"] == 20


def test_sin_acumular_los_dias_restantes_se_pierden(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY - timedelta(days=10))
    r = memberships.asignar_plan(db, socio_id, plan, HOY)
    assert r["dias_acumulados"] == 0 and r["fecha_vencimiento"] == HOY + timedelta(days=30)


def test_acumular_con_una_membresia_vencida_no_suma_nada(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY - timedelta(days=60))       # venció hace 30 días
    assert memberships.asignar_plan(db, socio_id, plan, HOY, acumular=True)["dias_acumulados"] == 0


def test_el_vencimiento_con_dias_acumulados_se_mantiene_al_pagar(db, plan, crear_socio):
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY - timedelta(days=10))
    memberships.asignar_plan(db, socio_id, plan, HOY, acumular=True)             # vence HOY + 50
    payments.registrar_pago(db, socio_id, 2500000, HOY, "efectivo")              # primer pago: confirma el período inicial
    assert models.obtener_socio(db, socio_id)["fecha_vencimiento"] == (HOY + timedelta(days=50)).isoformat()
    payments.registrar_pago(db, socio_id, 2500000, HOY, "efectivo")              # el siguiente sí suma
    assert models.obtener_socio(db, socio_id)["fecha_vencimiento"] == (HOY + timedelta(days=80)).isoformat()


# ---- pantalla
def _socio_con_dias(db, plan, crear_socio, dias_restantes=20):
    socio_id = crear_socio(nombre="Con Días", dni="38000001")
    memberships.asignar_plan(db, socio_id, plan, hoy_real() - timedelta(days=30 - dias_restantes))
    return socio_id


def _datos(plan, **extra):
    return {"plan_id": plan, "fecha_inicio": hoy_real().isoformat(), **extra}


def test_la_pantalla_avisa_cuando_quedan_dias_y_no_asigna_hasta_decidir(nav, db, plan, crear_socio):
    socio_id = _socio_con_dias(db, plan, crear_socio)

    html = nav.post(f"/socios/{socio_id}/membresia", _datos(plan)).get_data(as_text=True)

    assert "todavía tiene 20 días vigentes" in html
    assert "Asignar y acumular 20 días" in html and "Asignar sin acumular" in html
    assert "esos días se pierden" in html
    assert db.execute("SELECT COUNT(*) FROM membresias WHERE socio_id = ?", (socio_id,)).fetchone()[0] == 1


def test_la_pantalla_acumula_si_se_elige(nav, db, plan, crear_socio):
    socio_id = _socio_con_dias(db, plan, crear_socio)

    html = nav.post(f"/socios/{socio_id}/membresia", _datos(plan, acumular="1"), follow_redirects=True).get_data(as_text=True)

    assert "Se acumularon 20 días" in html
    assert models.obtener_socio(db, socio_id)["dias_extra"] == 20


def test_la_pantalla_no_acumula_si_se_elige_que_no(nav, db, plan, crear_socio):
    socio_id = _socio_con_dias(db, plan, crear_socio)
    html = nav.post(f"/socios/{socio_id}/membresia", _datos(plan, acumular="0"), follow_redirects=True).get_data(as_text=True)
    assert "acumularon" not in html
    assert models.obtener_socio(db, socio_id)["dias_extra"] == 0


def test_la_pantalla_no_pregunta_si_no_quedan_dias(nav, db, plan, crear_socio):
    socio_id = crear_socio(nombre="Vencido", dni="38000002")
    memberships.asignar_plan(db, socio_id, plan, hoy_real() - timedelta(days=60))
    html = nav.post(f"/socios/{socio_id}/membresia", _datos(plan), follow_redirects=True).get_data(as_text=True)
    assert "Plan «Mensual» asignado" in html


def test_la_pantalla_no_pregunta_a_un_socio_sin_plan(nav, db, plan, crear_socio):
    socio_id = crear_socio(nombre="Nuevo", dni="38000003")
    html = nav.post(f"/socios/{socio_id}/membresia", _datos(plan), follow_redirects=True).get_data(as_text=True)
    assert "Plan «Mensual» asignado" in html
