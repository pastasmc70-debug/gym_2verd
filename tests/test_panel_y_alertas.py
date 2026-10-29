"""Panel de inicio, alertas y links de WhatsApp."""
from urllib.parse import parse_qs, urlparse

import pytest

from app.services import dashboard, payments
from app.services.whatsapp import link_whatsapp, normalizar_telefono_ar
from conftest import HOY


def test_resumen_del_panel(db, socio_con_plan, crear_socio):
    vigente = socio_con_plan(20, nombre="Vigente")
    socio_con_plan(3, nombre="Por Vencer")
    socio_con_plan(-4, nombre="Vencido Uno")
    socio_con_plan(-30, nombre="Vencido Dos")
    socio_con_plan(2, nombre="Pausado", estado="pausado")      # no cuenta en alertas ni en activos
    crear_socio(nombre="Sin Plan")                             # activo, sin membresía
    payments.registrar_pago(db, vigente, 2500000, HOY, "efectivo")

    r = dashboard.resumen(db, HOY)

    assert r["socios_activos"] == 5
    assert r["por_vencer"] == 1
    assert r["vencidos"] == 2
    assert r["ingresos_mes_centavos"] == 2500000
    assert r["asistencias_hoy"] == 0


def test_ingresos_del_mes_solo_cuentan_el_mes_en_curso(db, socio_con_plan):
    from datetime import date
    socio_id = socio_con_plan(20)
    payments.registrar_pago(db, socio_id, 1000000, date(2026, 9, 30), "efectivo", confirmar_parcial=True)   # mes anterior
    payments.registrar_pago(db, socio_id, 2500000, date(2026, 10, 1), "efectivo", confirmar=True)   # primer día del mes (sobra el parcial anterior: pide confirmar)
    payments.registrar_pago(db, socio_id, 500000, date(2026, 10, 25), "tarjeta", confirmar_parcial=True)
    assert dashboard.resumen(db, HOY)["ingresos_mes_centavos"] == 3000000


def test_alertas_ordenadas_por_urgencia_y_solo_activos(db, socio_con_plan):
    socio_con_plan(3, nombre="Vence En Tres")
    socio_con_plan(-10, nombre="Vencido Hace Diez")
    socio_con_plan(-2, nombre="Vencido Hace Dos")
    socio_con_plan(30, nombre="Al Día")
    socio_con_plan(-5, nombre="Pausado", estado="pausado")

    nombres = [s["nombre"] for s in dashboard.socios_con_alerta(db, HOY)]

    assert nombres == ["Vencido Hace Diez", "Vencido Hace Dos", "Vence En Tres"]


def test_pantalla_de_alertas_tiene_boton_de_whatsapp(nav, db, plan, crear_socio):
    from datetime import timedelta
    from app.services import memberships
    from conftest import hoy_real
    socio_id = crear_socio(nombre="Carla Deudora", telefono="011 15 1234-5678")
    memberships.asignar_plan(db, socio_id, plan, hoy_real() - timedelta(days=45))

    html = nav.get("/alertas/").get_data(as_text=True)

    assert "Carla Deudora" in html
    assert "https://wa.me/5491112345678?text=" in html


def test_panel_se_muestra(nav):
    html = nav.get("/").get_data(as_text=True)
    assert "Socios activos" in html and "Ingresos del mes" in html and "Asistencias de hoy" in html


@pytest.mark.parametrize("entrada, esperado", [
    ("+54 9 11 1234-5678", "5491112345678"),
    ("5491112345678", "5491112345678"),
    ("+54 11 1234-5678", "5491112345678"),         # sin el 9
    ("11 1234-5678", "5491112345678"),
    ("011 1234-5678", "5491112345678"),
    ("011 15 1234-5678", "5491112345678"),         # formato viejo con 15
    ("0221 15-4567890", "5492214567890"),          # área de 3 dígitos
    ("(0351) 4567890", "5493514567890"),
])
def test_normaliza_telefonos_argentinos_para_whatsapp(entrada, esperado):
    assert normalizar_telefono_ar(entrada) == esperado


def test_link_de_whatsapp_trae_el_mensaje_prellenado():
    socio = {"nombre": "Carla Deudora", "telefono": "11 1234-5678", "fecha_vencimiento": "2026-10-20",
             "estado_membresia": "vencida", "dias_restantes": -5}
    url = urlparse(link_whatsapp(socio, "Gimnasio Don Juan"))
    texto = parse_qs(url.query)["text"][0]
    assert url.netloc == "wa.me" and url.path == "/5491112345678"
    assert "Hola Carla" in texto and "Gimnasio Don Juan" in texto and "venció el 20/10/2026" in texto


def test_mensaje_para_cuota_por_vencer():
    socio = {"nombre": "Luis Atento", "telefono": "11 1234-5678", "fecha_vencimiento": "2026-10-28",
             "estado_membresia": "por_vencer", "dias_restantes": 3}
    texto = parse_qs(urlparse(link_whatsapp(socio, "Mi Gimnasio")).query)["text"][0]
    assert "vence el 28/10/2026" in texto


def test_los_montos_del_panel_no_se_parten_en_varias_lineas():
    """Regresión visual: se verificó en Chromium (390, 320 y 1280 px); acá se cuida que la regla no se pierda."""
    from pathlib import Path
    import app as paquete
    css = (Path(paquete.__file__).parent / "static" / "css" / "app.css").read_text(encoding="utf-8")
    regla = next(l for l in css.splitlines() if l.startswith(".tarjeta-dato .numero"))
    assert "white-space: nowrap" in regla and "clamp(" in regla and "cqw" in regla
    assert "container-type: inline-size" in css
