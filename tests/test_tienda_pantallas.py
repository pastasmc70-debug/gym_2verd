"""Tienda: pantallas, permisos y módulo apagado."""
import pytest

from app.services import tienda
from conftest import Navegador


@pytest.fixture
def encendida(app):
    app.config["MODULO_TIENDA"] = True
    return app


@pytest.fixture
def producto(db, encendida):
    d, _ = tienda.validar_producto(db, dict(nombre="Whey", marca="ENA", categoria="Proteínas", precio="45000",
                                            costo="30000", stock="10", stock_minimo="3"))
    return tienda.crear_producto(db, d, "admin")


def _stock(db, pid):
    return db.execute("SELECT stock FROM productos WHERE id = ?", (pid,)).fetchone()[0]


# ------------------------------------------------------------ módulo apagado
def test_apagada_no_hay_menu_ni_pantallas(nav, nav_recepcion):
    assert "/tienda/" not in nav.get("/").get_data(as_text=True)
    for ruta in ("/tienda/", "/tienda/ventas", "/tienda/productos", "/tienda/faltantes", "/tienda/mas-vendidos"):
        assert nav.get(ruta).status_code == 404, ruta
    for ruta in ("/tienda/", "/tienda/ventas"):
        assert nav_recepcion.get(ruta).status_code == 404, ruta
    assert nav_recepcion.get("/tienda/productos").status_code in (403, 404)    # lo de admin ni siquiera se insinúa
    assert nav.post("/tienda/", {"metodo": "efectivo"}).status_code == 404


def test_encendida_aparece_en_el_menu(encendida, nav, nav_recepcion):
    assert "/tienda/" in nav.get("/").get_data(as_text=True)
    assert "/tienda/" in nav_recepcion.get("/").get_data(as_text=True)


def test_sin_sesion_pide_login(encendida, anonimo):
    r = anonimo.get("/tienda/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


# --------------------------------------------------------------------- venta
def test_vender_desde_la_pantalla(nav, db, producto, crear_socio):
    crear_socio(nombre="Ana Paz", dni="30111222")
    pantalla = nav.get("/tienda/").get_data(as_text=True)
    assert "Whey" in pantalla and f"cant_{producto}" in pantalla

    r = nav.post("/tienda/", {f"cant_{producto}": "2", "metodo": "tarjeta", "socio_dni": "30111222"}, follow_redirects=True)

    assert "Venta registrada por $ 90.000" in r.get_data(as_text=True).replace("\xa0", " ") or "Venta registrada" in r.get_data(as_text=True)
    assert _stock(db, producto) == 8
    v = db.execute("SELECT * FROM ventas").fetchone()
    assert v["metodo"] == "tarjeta" and v["total_centavos"] == 9000000 and v["cargada_por"] == "admin" and v["socio_id"]


def test_recepcion_puede_vender_y_queda_registrado_quien(nav_recepcion, db, producto):
    nav_recepcion.post("/tienda/", {f"cant_{producto}": "1", "metodo": "efectivo"})
    assert db.execute("SELECT cargada_por FROM ventas").fetchone()[0] == "recepcion"


def test_stock_insuficiente_avisa_y_no_vende(nav, db, producto):
    r = nav.post("/tienda/", {f"cant_{producto}": "11", "metodo": "efectivo"})
    texto = r.get_data(as_text=True)
    assert "No alcanza el stock" in texto and "pediste 11, hay 10" in texto
    assert _stock(db, producto) == 10 and db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0
    assert 'value="11"' in texto                                                    # conserva lo que se cargó


@pytest.mark.parametrize("datos,mensaje", [
    ({}, "al menos un producto"),
    ({"cant_X": "abc"}, "números enteros"),
    ({"cant_X": "-2"}, "números enteros"),
    ({"cant_X": "1", "metodo": "bitcoin"}, "Elegí cómo pagó"),
    ({"cant_X": "1", "socio_dni": "99999999"}, "No encontramos ningún socio"),
])
def test_validaciones_de_la_venta(nav, db, producto, datos, mensaje):
    cuerpo = {"metodo": "efectivo"}
    cuerpo.update({k.replace("X", str(producto)): v for k, v in datos.items()})
    r = nav.post("/tienda/", cuerpo)
    assert mensaje in r.get_data(as_text=True)
    assert db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0 and _stock(db, producto) == 10


def test_sin_csrf_no_se_vende(nav, db, producto):
    r = nav.client.post("/tienda/", data={f"cant_{producto}": "1", "metodo": "efectivo"})
    assert r.status_code in (400, 403) and db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0


def test_un_producto_desactivado_no_aparece_para_vender(nav, db, producto):
    nav.post(f"/tienda/productos/{producto}/desactivar")
    assert f"cant_{producto}" not in nav.get("/tienda/").get_data(as_text=True)


# ------------------------------------------------------- ventas, detalle, anular
def test_listado_detalle_y_anulacion(nav, nav_recepcion, db, producto):
    nav.post("/tienda/", {f"cant_{producto}": "3", "metodo": "efectivo"})
    vid = db.execute("SELECT id FROM ventas").fetchone()[0]

    assert "Mostrador" in nav_recepcion.get("/tienda/ventas").get_data(as_text=True)
    detalle = nav_recepcion.get(f"/tienda/ventas/{vid}").get_data(as_text=True)
    assert "Whey" in detalle and "Anular venta" not in detalle                     # recepción no ve el botón
    assert "Anular venta" in nav.get(f"/tienda/ventas/{vid}").get_data(as_text=True)

    r = nav.post(f"/tienda/ventas/{vid}/anular", {"motivo": "  "})
    assert "motivo" in r.get_data(as_text=True) and _stock(db, producto) == 7
    r = nav.post(f"/tienda/ventas/{vid}/anular", {"motivo": "Se equivocó"}, follow_redirects=True)
    assert "Venta anulada" in r.get_data(as_text=True) and "Se equivocó" in r.get_data(as_text=True)
    assert _stock(db, producto) == 10
    assert "ya fue anulada" in nav.get(f"/tienda/ventas/{vid}/anular").get_data(as_text=True)


def test_ventas_de_otra_fecha_y_fecha_invalida(nav, producto):
    assert nav.get("/tienda/ventas?fecha=2020-01-01").status_code == 200
    assert nav.get("/tienda/ventas?fecha=basura").status_code == 200
    assert nav.get("/tienda/ventas?fecha=2999-01-01").status_code == 200           # se corrige a hoy
    assert nav.get("/tienda/ventas/9999").status_code == 404


# ------------------------------------------------------------------ permisos
@pytest.mark.parametrize("metodo,ruta", [
    ("get", "/tienda/productos"), ("get", "/tienda/productos/nuevo"), ("get", "/tienda/productos/1/editar"),
    ("get", "/tienda/productos/1/stock"), ("post", "/tienda/productos/1/stock/entrada"),
    ("post", "/tienda/productos/1/stock/ajuste"), ("post", "/tienda/productos/1/desactivar"),
    ("get", "/tienda/faltantes"), ("get", "/tienda/mas-vendidos"),
    ("get", "/tienda/ventas/1/anular"), ("post", "/tienda/ventas/1/anular"),
])
def test_recepcion_no_administra_la_tienda(nav_recepcion, db, producto, metodo, ruta):
    r = getattr(nav_recepcion, metodo)(ruta)
    assert r.status_code in (302, 403)
    if r.status_code == 302:
        assert "/tienda" not in r.headers["Location"].split("?")[0] or r.headers["Location"].endswith("/")
    assert _stock(db, producto) == 10


def test_el_kiosco_no_entra_a_la_tienda(encendida, app):
    from conftest import CLAVE_KIOSCO
    k = Navegador(app.test_client())
    k.post("/kiosco/entrar", {"clave": CLAVE_KIOSCO})
    r = k.get("/tienda/")
    assert r.status_code == 302 and "/kiosco" in r.headers["Location"]


# ----------------------------------------------------------------- productos
def test_crear_y_editar_producto(nav, db, encendida):
    r = nav.post("/tienda/productos/nuevo", {"nombre": "Creatina", "marca": "Star", "categoria": "Suplementos",
                                             "precio": "20000", "costo": "", "stock": "5", "stock_minimo": "2"}, follow_redirects=True)
    assert "Producto «Creatina» creado" in r.get_data(as_text=True)
    p = db.execute("SELECT * FROM productos").fetchone()
    assert p["stock"] == 5 and p["precio_centavos"] == 2000000 and p["costo_centavos"] is None

    r = nav.post(f"/tienda/productos/{p['id']}/editar", {"nombre": "Creatina", "marca": "Star", "precio": "25000",
                                                         "stock_minimo": "2", "stock": "999"}, follow_redirects=True)
    assert "Producto actualizado" in r.get_data(as_text=True)
    p = db.execute("SELECT * FROM productos").fetchone()
    assert p["precio_centavos"] == 2500000 and p["stock"] == 5


def test_producto_con_errores_o_repetido(nav, producto):
    r = nav.post("/tienda/productos/nuevo", {"nombre": "", "precio": "0", "stock_minimo": "-1"})
    t = r.get_data(as_text=True)
    assert "Revisá los campos" in t and "is-invalid" in t
    r = nav.post("/tienda/productos/nuevo", {"nombre": "whey", "marca": "ena", "precio": "10", "stock": "0", "stock_minimo": "0"})
    assert "Ya existe un producto" in r.get_data(as_text=True)
    assert nav.get("/tienda/productos/999/editar").status_code == 404
    assert nav.post("/tienda/productos/1/borrar").status_code == 404


def test_buscar_y_activar(nav, producto):
    assert "Whey" in nav.get("/tienda/productos?q=ena").get_data(as_text=True)
    assert "No hay productos que coincidan" in nav.get("/tienda/productos?q=zzz").get_data(as_text=True)
    nav.post(f"/tienda/productos/{producto}/desactivar")
    assert "Desactivado" in nav.get("/tienda/productos").get_data(as_text=True)
    nav.post(f"/tienda/productos/{producto}/activar")
    assert f"cant_{producto}" in nav.get("/tienda/").get_data(as_text=True)


# --------------------------------------------------------------------- stock
def test_entrada_y_ajuste_desde_la_pantalla(nav, db, producto):
    r = nav.post(f"/tienda/productos/{producto}/stock/entrada", {"cantidad": "5", "motivo": "Compra"}, follow_redirects=True)
    assert "Stock actual: 15" in r.get_data(as_text=True) and _stock(db, producto) == 15
    nav.post(f"/tienda/productos/{producto}/stock/ajuste", {"stock_real": "12", "motivo": "Conteo"})
    assert _stock(db, producto) == 12
    t = nav.get(f"/tienda/productos/{producto}/stock").get_data(as_text=True)
    assert "Compra" in t and "Conteo" in t and "Stock inicial" in t


@pytest.mark.parametrize("operacion,datos,mensaje", [
    ("entrada", {"cantidad": "5", "motivo": ""}, "motivo"),
    ("entrada", {"cantidad": "0", "motivo": "x"}, "mayor a cero"),
    ("ajuste", {"stock_real": "3", "motivo": " "}, "motivo"),
    ("ajuste", {"stock_real": "10", "motivo": "x"}, "igual al que figura"),
    ("ajuste", {"stock_real": "-4", "motivo": "x"}, "número entero"),
])
def test_stock_invalido_muestra_el_error_y_no_cambia(nav, db, producto, operacion, datos, mensaje):
    r = nav.post(f"/tienda/productos/{producto}/stock/{operacion}", datos)
    assert r.status_code == 400 and mensaje in r.get_data(as_text=True) and _stock(db, producto) == 10
    assert nav.post(f"/tienda/productos/{producto}/stock/otra", datos).status_code == 404


# ------------------------------------------------------------------ reportes
def test_faltantes_y_mas_vendidos(nav, db, producto):
    assert "No falta nada" in nav.get("/tienda/faltantes").get_data(as_text=True)
    nav.post("/tienda/", {f"cant_{producto}": "8", "metodo": "efectivo"})
    assert "Whey" in nav.get("/tienda/faltantes").get_data(as_text=True)
    t = nav.get("/tienda/mas-vendidos").get_data(as_text=True)
    assert "Whey" in t and ">8<" in t
    assert "no puede ser posterior" in nav.get("/tienda/mas-vendidos?desde=2026-10-20&hasta=2026-10-01").get_data(as_text=True)
    assert nav.get("/tienda/mas-vendidos?desde=x&hasta=y").status_code == 200
