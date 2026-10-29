"""Tienda: productos, ventas con control de stock, entradas, ajustes, anulaciones y reportes."""
from datetime import date, datetime, timedelta

import pytest

from app import timeutils
from app.services import tienda
from app.services.errors import ErrorDeNegocio
from conftest import HOY

AHORA = datetime(2026, 10, 25, 11, 30, tzinfo=timeutils.TZ)


def _form(**kw):
    base = dict(nombre="Proteína Whey", marca="ENA", categoria="Proteínas", precio="45.000", costo="30000",
                stock="10", stock_minimo="3")
    base.update(kw)
    return base


@pytest.fixture
def producto(db):
    def _crear(**kw):
        datos, errores = tienda.validar_producto(db, _form(**kw))
        assert not errores, errores
        return tienda.crear_producto(db, datos, "admin")
    return _crear


def _stock(db, producto_id):
    return db.execute("SELECT stock FROM productos WHERE id = ?", (producto_id,)).fetchone()[0]


# ------------------------------------------------------------------ productos
def test_producto_valido(db):
    d, errores = tienda.validar_producto(db, _form())
    assert not errores
    assert d["precio_centavos"] == 4500000 and d["costo_centavos"] == 3000000 and d["stock"] == 10 and d["stock_minimo"] == 3
    assert d["marca"] == "ENA" and d["categoria"] == "Proteínas"


def test_costo_marca_y_categoria_son_opcionales(db):
    d, errores = tienda.validar_producto(db, _form(costo="", marca="", categoria=""))
    assert not errores and d["costo_centavos"] is None and d["marca"] is None and d["categoria"] is None


@pytest.mark.parametrize("campo,valor,clave", [
    ("nombre", "  ", "nombre"), ("precio", "0", "precio"), ("precio", "-5", "precio"), ("precio", "abc", "precio"),
    ("costo", "-1", "costo"), ("costo", "xx", "costo"), ("stock", "-1", "stock"), ("stock", "1,5", "stock"),
    ("stock_minimo", "-2", "stock_minimo"), ("nombre", "x" * 81, "nombre"), ("marca", "m" * 61, "marca"),
])
def test_validaciones_de_producto(db, campo, valor, clave):
    _, errores = tienda.validar_producto(db, _form(**{campo: valor}))
    assert clave in errores


def test_no_se_repite_nombre_y_marca(db, producto):
    producto()
    _, errores = tienda.validar_producto(db, _form(nombre="proteína whey", marca="ena"))
    assert "Ya existe un producto" in errores["nombre"]
    assert not tienda.validar_producto(db, _form(marca="Otra"))[1]             # otra marca: sí
    assert not tienda.validar_producto(db, _form(nombre="Creatina"))[1]


def test_editar_un_producto_puede_conservar_su_propio_nombre(db, producto):
    pid = producto()
    _, errores = tienda.validar_producto(db, _form(precio="50000"), producto_id=pid)
    assert not errores


def test_el_stock_inicial_deja_un_movimiento(db, producto):
    pid = producto(stock="10")
    m = tienda.movimientos(db, pid)
    assert len(m) == 1 and m[0]["tipo"] == "entrada" and m[0]["cantidad"] == 10 and m[0]["motivo"] == "Stock inicial"
    assert tienda.movimientos(db, producto(nombre="Sin stock", stock="0")) == []


def test_editar_no_toca_el_stock(db, producto):
    pid = producto(stock="10")
    d, _ = tienda.validar_producto(db, _form(precio="50000", stock="999"), producto_id=pid)
    tienda.actualizar_producto(db, pid, d)
    p = tienda.obtener_producto(db, pid)
    assert p["precio_centavos"] == 5000000 and p["stock"] == 10


def test_activar_y_desactivar(db, producto):
    pid = producto()
    tienda.cambiar_activo(db, pid, False)
    assert tienda.obtener_producto(db, pid)["activo"] == 0
    assert tienda.listar_productos(db, solo_activos=True) == []
    assert len(tienda.listar_productos(db)) == 1
    assert len(tienda.listar_productos(db, q="whey")) == 1 and tienda.listar_productos(db, q="zzz") == []


def test_categorias(db, producto):
    producto(categoria="Proteínas"); producto(nombre="Creatina", categoria="Creatinas"); producto(nombre="Sin cat", categoria="")
    assert tienda.categorias(db) == ["Creatinas", "Proteínas"]


# --------------------------------------------------------------------- ventas
def test_una_venta_descuenta_el_stock_y_guarda_el_detalle(db, producto):
    a = producto(precio="45000", costo="30000", stock="10")
    b = producto(nombre="Creatina", marca="Star", precio="20000", costo="", stock="5")

    r = tienda.registrar_venta(db, [(a, 2), (b, 1)], "efectivo", usuario="recepcion", ahora=AHORA)

    assert r["total_centavos"] == 2 * 4500000 + 2000000
    assert _stock(db, a) == 8 and _stock(db, b) == 4
    v = tienda.obtener_venta(db, r["venta_id"])
    assert v["fecha"] == "2026-10-25" and v["hora"] == "11:30:00" and v["cargada_por"] == "recepcion" and v["socio_id"] is None
    items = tienda.items_de_venta(db, r["venta_id"])
    assert [(i["nombre_producto"], i["cantidad"], i["precio_unitario_centavos"]) for i in items] == [
        ("Proteína Whey (ENA)", 2, 4500000), ("Creatina (Star)", 1, 2000000)]
    assert items[0]["costo_unitario_centavos"] == 3000000 and items[1]["costo_unitario_centavos"] is None
    mov = tienda.movimientos(db, a)[0]
    assert (mov["tipo"], mov["cantidad"], mov["stock_resultante"]) == ("venta", -2, 8) and mov["usuario"] == "recepcion"


def test_la_venta_puede_ser_de_un_socio(db, producto, crear_socio):
    socio_id = crear_socio(nombre="Ana Paz")
    r = tienda.registrar_venta(db, [(producto(), 1)], "tarjeta", socio_id=socio_id, ahora=AHORA)
    assert tienda.obtener_venta(db, r["venta_id"])["socio_nombre"] == "Ana Paz"


def test_aviso_si_no_alcanza_el_stock_y_no_se_vende_nada(db, producto):
    a = producto(stock="10")
    b = producto(nombre="Creatina", stock="2")

    with pytest.raises(ErrorDeNegocio) as e:
        tienda.registrar_venta(db, [(a, 3), (b, 5)], "efectivo")

    assert e.value.codigo == "sin_stock"
    assert "No alcanza el stock" in str(e.value) and "«Creatina» (pediste 5, hay 2)" in str(e.value)
    assert "Proteína" not in str(e.value)                                       # el que sí alcanza no se menciona
    assert _stock(db, a) == 10 and _stock(db, b) == 2                           # nada se descontó
    assert db.execute("SELECT COUNT(*) FROM ventas").fetchone()[0] == 0


def test_se_puede_vender_todo_el_stock_pero_ni_una_unidad_mas(db, producto):
    a = producto(stock="4")
    tienda.registrar_venta(db, [(a, 4)], "efectivo")
    assert _stock(db, a) == 0
    with pytest.raises(ErrorDeNegocio, match="hay 0"):
        tienda.registrar_venta(db, [(a, 1)], "efectivo")


def test_un_mismo_producto_repetido_se_suma_antes_de_controlar_el_stock(db, producto):
    a = producto(stock="5")
    with pytest.raises(ErrorDeNegocio, match="pediste 6, hay 5"):
        tienda.registrar_venta(db, [(a, 3), (a, 3)], "efectivo")


@pytest.mark.parametrize("items,codigo", [([], "sin_items"), ([(1, 0)], "cantidad"), ([(1, -1)], "cantidad"),
                                          ([(1, "x")], "cantidad"), ([(1, 1.5)], "cantidad"), ([(1, 5000)], "cantidad")])
def test_cantidades_invalidas(db, producto, items, codigo):
    producto()
    with pytest.raises(ErrorDeNegocio) as e:
        tienda.registrar_venta(db, items, "efectivo")
    assert e.value.codigo == codigo


def test_metodo_producto_y_socio_invalidos(db, producto):
    a = producto()
    with pytest.raises(ErrorDeNegocio, match="Elegí cómo pagó"):
        tienda.registrar_venta(db, [(a, 1)], "bitcoin")
    with pytest.raises(ErrorDeNegocio, match="ya no existe"):
        tienda.registrar_venta(db, [(999, 1)], "efectivo")
    with pytest.raises(ErrorDeNegocio, match="No encontramos al socio"):
        tienda.registrar_venta(db, [(a, 1)], "efectivo", socio_id=999)


def test_un_producto_desactivado_no_se_vende(db, producto):
    a = producto()
    tienda.cambiar_activo(db, a, False)
    with pytest.raises(ErrorDeNegocio, match="desactivado"):
        tienda.registrar_venta(db, [(a, 1)], "efectivo")


def test_editar_el_precio_no_cambia_ventas_ya_hechas(db, producto):
    a = producto(precio="45000")
    v = tienda.registrar_venta(db, [(a, 1)], "efectivo", ahora=AHORA)["venta_id"]
    d, _ = tienda.validar_producto(db, _form(precio="99000"), producto_id=a)
    tienda.actualizar_producto(db, a, d)
    assert tienda.items_de_venta(db, v)[0]["precio_unitario_centavos"] == 4500000
    assert tienda.obtener_venta(db, v)["total_centavos"] == 4500000


# ------------------------------------------------------------------ anulación
def test_anular_una_venta_devuelve_el_stock_y_no_borra_nada(db, producto):
    a = producto(stock="10"); b = producto(nombre="Creatina", stock="5")
    v = tienda.registrar_venta(db, [(a, 3), (b, 2)], "efectivo", ahora=AHORA)["venta_id"]

    tienda.anular_venta(db, v, "  Se equivocó de producto  ", "admin")

    assert _stock(db, a) == 10 and _stock(db, b) == 5
    venta = tienda.obtener_venta(db, v)
    assert venta["anulada"] == 1 and venta["anulada_motivo"] == "Se equivocó de producto" and venta["anulada_por"] == "admin"
    assert venta["anulada_en"] and len(tienda.items_de_venta(db, v)) == 2          # el detalle queda
    mov = tienda.movimientos(db, a)[0]
    assert mov["tipo"] == "anulacion_venta" and mov["cantidad"] == 3 and mov["stock_resultante"] == 10
    assert "Se equivocó de producto" in mov["motivo"] and mov["usuario"] == "admin"


def test_anular_exige_motivo_y_no_se_hace_dos_veces(db, producto):
    a = producto(stock="10")
    v = tienda.registrar_venta(db, [(a, 3)], "efectivo")["venta_id"]
    for motivo in ("", "  ", None):
        with pytest.raises(ErrorDeNegocio, match="motivo"):
            tienda.anular_venta(db, v, motivo, "admin")
    assert _stock(db, a) == 7
    tienda.anular_venta(db, v, "error", "admin")
    with pytest.raises(ErrorDeNegocio, match="ya estaba anulada"):
        tienda.anular_venta(db, v, "otra vez", "admin")
    assert _stock(db, a) == 10                                                      # no devolvió dos veces
    with pytest.raises(ErrorDeNegocio, match="No encontramos la venta"):
        tienda.anular_venta(db, 999, "x", "admin")


def test_se_puede_anular_aunque_el_producto_este_desactivado(db, producto):
    a = producto(stock="10")
    v = tienda.registrar_venta(db, [(a, 3)], "efectivo")["venta_id"]
    tienda.cambiar_activo(db, a, False)
    tienda.anular_venta(db, v, "error", "admin")
    assert _stock(db, a) == 10


# --------------------------------------------------------------- entradas y ajustes
def test_entrada_de_mercaderia(db, producto):
    a = producto(stock="2")
    assert tienda.entrada_mercaderia(db, a, "10", "Compra a proveedor", "admin") == 12
    assert _stock(db, a) == 12
    m = tienda.movimientos(db, a)[0]
    assert (m["tipo"], m["cantidad"], m["stock_resultante"], m["motivo"], m["usuario"]) == ("entrada", 10, 12, "Compra a proveedor", "admin")


@pytest.mark.parametrize("cantidad,motivo,texto", [("0", "x", "mayor a cero"), ("-3", "x", "mayor a cero"), ("1,5", "x", "mayor a cero"),
                                                   ("abc", "x", "mayor a cero"), ("5", "", "motivo"), ("5", "  ", "motivo")])
def test_entrada_invalida(db, producto, cantidad, motivo, texto):
    a = producto(stock="2")
    with pytest.raises(ErrorDeNegocio, match=texto):
        tienda.entrada_mercaderia(db, a, cantidad, motivo, "admin")
    assert _stock(db, a) == 2


def test_ajuste_de_stock_con_motivo(db, producto):
    a = producto(stock="10")
    assert tienda.ajustar_stock(db, a, "7", "Conteo del inventario", "admin") == -3
    assert _stock(db, a) == 7
    m = tienda.movimientos(db, a)[0]
    assert (m["tipo"], m["cantidad"], m["stock_resultante"], m["motivo"]) == ("ajuste", -3, 7, "Conteo del inventario")
    assert tienda.ajustar_stock(db, a, "9", "Apareció una caja", "admin") == 2


def test_ajuste_invalido(db, producto):
    a = producto(stock="10")
    with pytest.raises(ErrorDeNegocio, match="motivo"):
        tienda.ajustar_stock(db, a, "5", "", "admin")
    with pytest.raises(ErrorDeNegocio, match="igual al que figura"):
        tienda.ajustar_stock(db, a, "10", "x", "admin")
    for malo in ("-1", "x", ""):
        with pytest.raises(ErrorDeNegocio, match="número entero"):
            tienda.ajustar_stock(db, a, malo, "x", "admin")
    assert _stock(db, a) == 10


def test_el_stock_nunca_queda_negativo_ni_siquiera_por_la_base(db, producto):
    import sqlite3
    a = producto(stock="1")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE productos SET stock = -1 WHERE id = ?", (a,))


# -------------------------------------------------------------------- faltantes
def test_lista_de_faltantes(db, producto):
    producto(nombre="Bajo", stock="2", stock_minimo="5")           # por debajo del mínimo
    producto(nombre="Justo", stock="5", stock_minimo="5")          # en el mínimo: también avisa
    producto(nombre="Agotado", stock="0", stock_minimo="0")        # agotado aunque no tenga mínimo
    producto(nombre="Bien", stock="20", stock_minimo="5")
    inactivo = producto(nombre="Inactivo", stock="0", stock_minimo="5")
    tienda.cambiar_activo(db, inactivo, False)

    assert [p["nombre"] for p in tienda.faltantes(db)] == ["Bajo", "Justo", "Agotado"] or \
           [p["nombre"] for p in tienda.faltantes(db)] == ["Bajo", "Agotado", "Justo"]
    assert {p["nombre"] for p in tienda.faltantes(db)} == {"Bajo", "Justo", "Agotado"}


def test_vender_hace_aparecer_el_producto_en_faltantes(db, producto):
    a = producto(stock="6", stock_minimo="5")
    assert tienda.faltantes(db) == []
    tienda.registrar_venta(db, [(a, 2)], "efectivo")
    assert [p["nombre"] for p in tienda.faltantes(db)] == ["Proteína Whey"]


# ------------------------------------------------------------ caja y reportes
def test_caja_del_dia_por_metodo_sin_contar_anuladas(db, producto):
    a = producto(precio="10000", stock="50")
    tienda.registrar_venta(db, [(a, 2)], "efectivo", ahora=AHORA)
    tienda.registrar_venta(db, [(a, 1)], "tarjeta", ahora=AHORA)
    mala = tienda.registrar_venta(db, [(a, 5)], "transferencia", ahora=AHORA)["venta_id"]
    tienda.anular_venta(db, mala, "error", "admin")
    tienda.registrar_venta(db, [(a, 1)], "efectivo", fecha=HOY - timedelta(days=1), ahora=AHORA)    # otro día

    caja = tienda.caja_del_dia(db, HOY)

    assert caja["total_centavos"] == 3000000 and caja["cantidad"] == 2 and caja["anuladas"] == 1
    assert caja["por_metodo"] == {"efectivo": 2000000, "transferencia": 0, "tarjeta": 1000000}
    assert len(caja["ventas"]) == 3                                                  # la anulada se lista, marcada
    assert [v["unidades"] for v in caja["ventas"]] == [5, 1, 2]


def test_ingresos_del_mes_solo_cuentan_el_mes_y_lo_vigente(db, producto):
    a = producto(precio="10000", stock="100")
    tienda.registrar_venta(db, [(a, 1)], "efectivo", fecha=date(2026, 9, 30), ahora=AHORA)       # mes anterior
    tienda.registrar_venta(db, [(a, 2)], "efectivo", fecha=date(2026, 10, 1), ahora=AHORA)
    tienda.registrar_venta(db, [(a, 3)], "efectivo", fecha=HOY, ahora=AHORA)
    anulada = tienda.registrar_venta(db, [(a, 9)], "efectivo", fecha=HOY, ahora=AHORA)["venta_id"]
    tienda.anular_venta(db, anulada, "error", "admin")
    assert tienda.ingresos_del_mes(db, HOY) == 5 * 1000000


def test_mas_vendidos(db, producto):
    a = producto(nombre="Whey", precio="45000", costo="30000", stock="100")
    b = producto(nombre="Creatina", marca="", precio="20000", costo="", stock="100")
    c = producto(nombre="Barra", marca="", precio="3000", costo="1000", stock="500")
    tienda.registrar_venta(db, [(a, 2), (b, 5)], "efectivo", fecha=HOY, ahora=AHORA)
    tienda.registrar_venta(db, [(a, 1), (c, 5)], "tarjeta", fecha=HOY - timedelta(days=10), ahora=AHORA)
    tienda.registrar_venta(db, [(c, 40)], "efectivo", fecha=HOY - timedelta(days=60), ahora=AHORA)     # fuera del período
    anulada = tienda.registrar_venta(db, [(c, 90)], "efectivo", fecha=HOY, ahora=AHORA)["venta_id"]
    tienda.anular_venta(db, anulada, "error", "admin")

    desde, hasta = tienda.periodo_por_defecto(HOY)
    ranking = tienda.mas_vendidos(db, desde, hasta)

    assert [(r["nombre"], r["unidades"]) for r in ranking] == [("Creatina", 5), ("Barra", 5), ("Whey", 3)] or \
           [(r["nombre"], r["unidades"]) for r in ranking] == [("Barra", 5), ("Creatina", 5), ("Whey", 3)]
    whey = next(r for r in ranking if r["nombre"] == "Whey")
    assert whey["importe_centavos"] == 3 * 4500000 and whey["ganancia_centavos"] == 3 * 1500000
    assert next(r for r in ranking if r["nombre"] == "Creatina")["ganancia_centavos"] is None        # sin costo cargado
    assert [r["nombre"] for r in tienda.mas_vendidos(db, desde, hasta, limite=1)] == [ranking[0]["nombre"]]


def test_periodo_por_defecto():
    assert tienda.periodo_por_defecto(date(2026, 10, 25)) == (date(2026, 9, 26), date(2026, 10, 25))
