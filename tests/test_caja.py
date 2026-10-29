"""Pantalla de caja diaria (cuotas)."""
from datetime import timedelta

from app.services import memberships, payments
from conftest import hoy_real

PRECIO = 2500000


def _pagos(db, plan, crear_socio):
    socio_id = crear_socio(nombre="Caja Uno", dni="41000001")
    memberships.asignar_plan(db, socio_id, plan, hoy_real())
    bueno = payments.registrar_pago(db, socio_id, PRECIO, hoy_real(), "efectivo")["pago_id"]
    malo = payments.registrar_pago(db, socio_id, 1000000, hoy_real(), "tarjeta", confirmar_parcial=True)["pago_id"]
    payments.anular_pago(db, malo, "error", "admin")
    return bueno, malo


def test_la_caja_suma_lo_vigente_por_metodo_y_marca_los_anulados(nav, db, plan, crear_socio):
    _pagos(db, plan, crear_socio)
    html = nav.get("/caja/").get_data(as_text=True)
    assert "Caja diaria" in html and "$ 25.000" in html
    assert "Efectivo: $ 25.000" in html and "Tarjeta: $ 0" in html
    assert 'class="anulado"' in html and "no suman en los totales" in html


def test_la_caja_de_otro_dia_y_fechas_raras(nav, db, plan, crear_socio):
    _pagos(db, plan, crear_socio)
    ayer = (hoy_real() - timedelta(days=1)).isoformat()
    assert "No hubo cobros" in nav.get(f"/caja/?fecha={ayer}").get_data(as_text=True)
    futuro = (hoy_real() + timedelta(days=5)).isoformat()
    assert hoy_real().strftime("%d/%m/%Y") in nav.get(f"/caja/?fecha={futuro}").get_data(as_text=True)   # no mira el futuro
    assert nav.get("/caja/?fecha=basura").status_code == 200


def test_recepcion_ve_la_caja_y_sin_sesion_no(nav_recepcion, anonimo):
    assert nav_recepcion.get("/caja/").status_code == 200
    assert anonimo.get("/caja/").status_code == 302


# ------------------------------------------------- tienda aparte de las cuotas (panel y caja)
def _venta_de_tienda(db, app, cantidad=2, anular=False):
    from app.services import tienda
    app.config["MODULO_TIENDA"] = True
    d, _ = tienda.validar_producto(db, dict(nombre="Whey", marca="ENA", categoria="", precio="10000", costo="",
                                            stock="50", stock_minimo="1"))
    pid = tienda.crear_producto(db, d, "admin")
    vid = tienda.registrar_venta(db, [(pid, cantidad)], "tarjeta", usuario="admin")["venta_id"]
    if anular:
        tienda.anular_venta(db, vid, "error", "admin")
    return vid


def test_la_caja_muestra_la_tienda_separada_de_las_cuotas(nav, app, db, plan, crear_socio):
    _pagos(db, plan, crear_socio)
    _venta_de_tienda(db, app)
    html = nav.get("/caja/").get_data(as_text=True)
    assert "Total del día (cuotas + tienda)" in html and "$ 45.000" in html      # 25.000 + 20.000
    assert "Tarjeta: $ 20.000" in html and html.count("Ventas de la tienda del día") == 1
    assert "Mostrador" in html


def test_la_venta_anulada_no_suma_en_la_caja(nav, app, db, plan, crear_socio):
    _pagos(db, plan, crear_socio)
    _venta_de_tienda(db, app, anular=True)
    html = nav.get("/caja/").get_data(as_text=True)
    assert "$ 25.000" in html and "$ 45.000" not in html and "Anulada" in html


def test_la_caja_sin_modulo_no_menciona_la_tienda(nav, db, plan, crear_socio):
    _pagos(db, plan, crear_socio)
    html = nav.get("/caja/").get_data(as_text=True)
    assert "tienda" not in html.lower().replace("tienda.", "") or "Ventas de la tienda" not in html
    assert "cuotas + tienda" not in html and "Ventas de la tienda del día" not in html


def test_el_panel_muestra_la_tienda_del_mes_solo_si_esta_activa(nav, app, db):
    assert "Tienda del mes" not in nav.get("/").get_data(as_text=True)
    _venta_de_tienda(db, app, cantidad=3)
    html = nav.get("/").get_data(as_text=True)
    assert "Tienda del mes" in html and "$ 30.000" in html
