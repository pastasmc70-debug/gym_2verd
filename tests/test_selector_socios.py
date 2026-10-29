"""Tarea I: lista de socios visible al elegir un socio (nuevo pago, asignar plan, ingreso, venta de tienda)."""
import pytest

from app import models
from app.services import payments, selector
from conftest import CLAVE_KIOSCO, HOY, Navegador, hoy_real


# ----------------------------------------------------------------------------- ayudas
@pytest.fixture
def grupo(db, socio_con_plan, crear_socio):
    """Cinco socios en distintos estados (fecha real, para las pantallas)."""
    h = hoy_real()
    ids = {
        "zeta": socio_con_plan(-5, hoy=h, nombre="Zeta Vencida", dni="30000005"),
        "beta": socio_con_plan(3, hoy=h, nombre="Beta Porvencer", dni="30000002"),
        "alfa": socio_con_plan(20, hoy=h, nombre="Alfa Vigente", dni="30000001"),
        "omega": socio_con_plan(-40, hoy=h, nombre="Omega Vencida", dni="30000004"),
        "sin": crear_socio(nombre="Sergio Sinplan", dni="30000003"),
    }
    return ids


def _nombres(sel):
    return [s["nombre"] for s in sel["socios"]]


def _posiciones(html, *nombres):
    return [html.index(n) for n in nombres]


@pytest.fixture
def kiosco_nav(app):
    n = Navegador(app.test_client())
    assert n.post("/kiosco/entrar", {"clave": CLAVE_KIOSCO}).status_code == 302
    return n


# ---------------------------------------------------------------------------- servicio
def test_orden_por_defecto_vencidos_y_por_vencer_arriba_y_despues_alfabetico(db, grupo):
    sel = selector.listar(db, hoy=hoy_real())
    assert sel["orden"] == "prioridad"
    assert _nombres(sel) == ["Omega Vencida", "Zeta Vencida", "Beta Porvencer", "Alfa Vigente", "Sergio Sinplan"]


def test_se_puede_cambiar_a_solo_alfabetico(db, grupo):
    sel = selector.listar(db, orden="alfabetico", hoy=hoy_real())
    assert _nombres(sel) == ["Alfa Vigente", "Beta Porvencer", "Omega Vencida", "Sergio Sinplan", "Zeta Vencida"]


def test_un_orden_desconocido_vuelve_al_de_prioridad(db, grupo):
    assert selector.listar(db, orden="cualquiera", hoy=hoy_real())["orden"] == "prioridad"


def test_cada_socio_trae_su_estado_y_dias_restantes(db, grupo):
    por_nombre = {s["nombre"]: s for s in selector.listar(db, hoy=hoy_real())["socios"]}
    assert por_nombre["Omega Vencida"]["estado_membresia"] == models.VENCIDA
    assert por_nombre["Beta Porvencer"]["estado_membresia"] == models.POR_VENCER
    assert por_nombre["Alfa Vigente"]["estado_membresia"] == models.VIGENTE
    assert por_nombre["Sergio Sinplan"]["estado_membresia"] == models.SIN_MEMBRESIA
    assert por_nombre["Beta Porvencer"]["dias_restantes"] == 3


def test_filtra_por_nombre_sin_importar_mayusculas(db, grupo):
    assert _nombres(selector.listar(db, "ALF", hoy=hoy_real())) == ["Alfa Vigente"]
    assert _nombres(selector.listar(db, "vencida", hoy=hoy_real())) == ["Omega Vencida", "Zeta Vencida"]


@pytest.mark.parametrize("texto", ["30000002", "30.000.002", "0002"])
def test_filtra_por_dni_completo_con_puntos_o_parcial(db, grupo, texto):
    assert _nombres(selector.listar(db, texto, hoy=hoy_real())) == ["Beta Porvencer"]


def test_sin_coincidencias_devuelve_lista_vacia(db, grupo):
    sel = selector.listar(db, "nadie", hoy=hoy_real())
    assert sel["socios"] == [] and sel["total"] == 0 and sel["hay_mas"] is False


def test_el_filtro_respeta_el_orden_elegido(db, grupo):
    sel = selector.listar(db, "vencida", orden="alfabetico", hoy=hoy_real())
    assert _nombres(sel) == ["Omega Vencida", "Zeta Vencida"]
    sel = selector.listar(db, "a", orden="prioridad", hoy=hoy_real())
    assert _nombres(sel)[:2] == ["Omega Vencida", "Zeta Vencida"]


def test_limite_de_50_por_vez_con_paginas(db, crear_socio):
    for i in range(120):
        crear_socio(nombre=f"Socio {i:03d}", dni=str(31000000 + i))
    uno = selector.listar(db, hoy=HOY)
    assert selector.LIMITE == 50 and len(uno["socios"]) == 50 and uno["total"] == 120
    assert uno["hay_mas"] is True and uno["mostrados"] == 50
    tres = selector.listar(db, pagina=3, hoy=HOY)
    assert len(tres["socios"]) == 20 and tres["hay_mas"] is False and tres["mostrados"] == 120
    assert _nombres(tres)[0] == "Socio 100"
    assert len(selector.listar(db, pagina=99, hoy=HOY)["socios"]) == 0       # una página inexistente no rompe


def test_las_paginas_no_repiten_ni_pierden_socios(db, crear_socio):
    for i in range(75):
        crear_socio(nombre=f"Socio {i:03d}", dni=str(31000000 + i))
    ids = [s["id"] for p in (1, 2) for s in selector.listar(db, pagina=p, hoy=HOY)["socios"]]
    assert len(ids) == 75 == len(set(ids))


# --------------------------------------------------------------------------- pantallas
def test_nuevo_pago_muestra_la_lista_sin_escribir_nada(nav, grupo):
    html = nav.get("/pagos/nuevo").get_data(as_text=True)
    assert "data-selector" in html and 'data-destino="pago"' in html and "Elegí un socio" in html
    for nombre in ("Alfa Vigente", "Beta Porvencer", "Zeta Vencida", "Omega Vencida", "Sergio Sinplan"):
        assert nombre in html
    assert f'href="/pagos/nuevo?socio_id={grupo["alfa"]}"' in html           # un clic y se abre el pago de ese socio


def test_cada_fila_muestra_dni_plan_y_estado_con_color(nav, grupo):
    html = nav.get("/pagos/nuevo").get_data(as_text=True)
    assert "DNI 30000001" in html and "Mensual" in html and "Sin plan" in html
    assert "estado-vencida" in html and "estado-por_vencer" in html and "estado-vigente" in html
    assert "text-bg-danger" in html and "text-bg-warning" in html and "text-bg-success" in html
    assert "Vencida" in html and "Por vencer" in html and "Vigente" in html


def test_la_foto_chica_aparece_solo_si_el_socio_tiene(nav, db, grupo):
    with db:
        db.execute("UPDATE socios SET foto = 'ana.jpg' WHERE id = ?", (grupo["alfa"],))
    html = nav.get("/pagos/nuevo?q=Alfa").get_data(as_text=True)
    assert 'class="foto-mini"' in html and "/fotos/ana.jpg" in html
    html = nav.get("/pagos/nuevo?q=Beta").get_data(as_text=True)
    assert "sin-foto-mini" in html and "foto-mini\"" not in html.replace("sin-foto-mini", "")


def test_nuevo_pago_orden_por_defecto_y_alfabetico_en_la_pantalla(nav, grupo):
    html = nav.get("/pagos/nuevo").get_data(as_text=True)
    assert _posiciones(html, "Omega Vencida", "Zeta Vencida", "Beta Porvencer", "Alfa Vigente", "Sergio Sinplan") == \
        sorted(_posiciones(html, "Omega Vencida", "Zeta Vencida", "Beta Porvencer", "Alfa Vigente", "Sergio Sinplan"))
    html = nav.get("/pagos/nuevo?orden=alfabetico").get_data(as_text=True)
    pos = _posiciones(html, "Alfa Vigente", "Beta Porvencer", "Omega Vencida", "Sergio Sinplan", "Zeta Vencida")
    assert pos == sorted(pos)


def test_nuevo_pago_el_buscador_filtra_la_misma_lista_por_nombre_y_por_dni(nav, grupo):
    html = nav.get("/pagos/nuevo?q=beta").get_data(as_text=True)
    assert "Beta Porvencer" in html and "Alfa Vigente" not in html and "Zeta Vencida" not in html
    html = nav.get("/pagos/nuevo?q=30000004").get_data(as_text=True)
    assert "Omega Vencida" in html and "Beta Porvencer" not in html
    html = nav.get("/pagos/nuevo?q=zzzz").get_data(as_text=True)
    assert "No encontramos ningún socio con «zzzz»" in html


def test_nuevo_pago_pagina_de_a_50(nav, db, crear_socio):
    for i in range(60):
        crear_socio(nombre=f"Socio {i:03d}", dni=str(31000000 + i))
    html = nav.get("/pagos/nuevo").get_data(as_text=True)
    assert html.count('class="selector-fila') == 50 and "Mostrando 50 de 60" in html and "Mostrar más" in html
    html = nav.get("/pagos/nuevo?pagina=2").get_data(as_text=True)
    assert html.count('class="selector-fila') == 10 and "Socio 059" in html and "Anteriores" in html


def test_asignar_o_renovar_plan_tiene_su_pantalla_con_la_lista(nav, grupo):
    html = nav.get("/membresias/nueva").get_data(as_text=True)
    assert "Asignar o renovar plan" in html and 'data-destino="membresia"' in html
    assert f'href="/socios/{grupo["omega"]}/membresia"' in html
    assert "Sergio Sinplan" in html
    assert "Beta Porvencer" not in nav.get("/membresias/nueva?q=omega").get_data(as_text=True)
    assert "/membresias/nueva" in nav.get("/socios").get_data(as_text=True)    # se llega desde la lista de socios


def test_asistencia_muestra_la_lista_y_un_clic_registra_el_ingreso(nav, db, grupo):
    html = nav.get("/asistencia/").get_data(as_text=True)
    assert 'data-destino="ingreso"' in html and "Alfa Vigente" in html and "Omega Vencida" in html
    assert f'name="socio_id" value="{grupo["alfa"]}"' in html and 'name="csrf_token"' in html

    payments.registrar_pago(db, grupo["alfa"], 2500000, hoy_real(), "efectivo")      # la regla de ingreso exige el pago inicial
    r = nav.post("/asistencia/ingreso", {"socio_id": grupo["alfa"]}, follow_redirects=True)      # lo que envía el clic

    assert "Ingreso registrado: Alfa Vigente" in r.get_data(as_text=True)
    assert db.execute("SELECT COUNT(*) FROM asistencias WHERE socio_id = ?", (grupo["alfa"],)).fetchone()[0] == 1


def test_asistencia_sigue_mostrando_la_lista_cuando_hay_varios_candidatos(nav, grupo):
    html = nav.post("/asistencia/ingreso", {"q": "vencida"}).get_data(as_text=True)      # coinciden dos socios
    assert "Encontramos varios socios" in html and 'data-destino="ingreso"' in html
    assert 'href="/asistencia/?' in html                                                  # los links de orden vuelven a la pantalla


def test_tienda_muestra_la_lista_para_elegir_al_socio(nav, app, grupo):
    app.config["MODULO_TIENDA"] = True
    html = nav.get("/tienda/").get_data(as_text=True)
    assert 'data-destino="venta"' in html and 'id="buscar_socio"' in html and 'id="socio_dni"' in html
    assert 'data-elegir-dni="30000001"' in html and 'data-nombre="Alfa Vigente"' in html


def test_la_venta_con_el_dni_elegido_sigue_funcionando(nav, db, app, grupo):
    from app.services import tienda
    app.config["MODULO_TIENDA"] = True
    d, _ = tienda.validar_producto(db, dict(nombre="Whey", marca="ENA", categoria="P", precio="45000", costo="30000",
                                            stock="10", stock_minimo="3"))
    pid = tienda.crear_producto(db, d, "admin")
    r = nav.post("/tienda/", {"metodo": "efectivo", "socio_dni": "30000001", f"cant_{pid}": "1"})
    assert r.status_code == 302
    assert db.execute("SELECT socio_id FROM ventas").fetchone()[0] == grupo["alfa"]


def test_el_boton_de_orden_y_el_estado_activo_se_ven_en_la_pantalla(nav, grupo):
    html = nav.get("/pagos/nuevo").get_data(as_text=True)
    assert 'data-orden="prioridad"' in html and 'data-orden="alfabetico"' in html and "Vencidos primero" in html
    assert 'btn btn-outline-secondary active" data-orden="prioridad"' in html
    html = nav.get("/pagos/nuevo?orden=alfabetico").get_data(as_text=True)
    assert 'btn btn-outline-secondary active" data-orden="alfabetico"' in html


# ---------------------------------------------------------------------- fragmento (JS)
def test_el_fragmento_devuelve_solo_la_lista_filtrada(nav, grupo):
    r = nav.get("/socios/selector?destino=pago&q=alf&orden=prioridad")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "<html" not in html and "<nav" not in html
    assert "Alfa Vigente" in html and "Beta Porvencer" not in html and "Mostrando 1 de 1" in html


def test_el_fragmento_respeta_el_orden_pedido(nav, grupo):
    html = nav.get("/socios/selector?destino=pago&orden=alfabetico").get_data(as_text=True)
    pos = _posiciones(html, "Alfa Vigente", "Beta Porvencer", "Omega Vencida", "Sergio Sinplan", "Zeta Vencida")
    assert pos == sorted(pos)


def test_el_fragmento_mas_trae_la_pagina_siguiente_sin_el_estado_vacio(nav, db, crear_socio):
    for i in range(60):
        crear_socio(nombre=f"Socio {i:03d}", dni=str(31000000 + i))
    html = nav.get("/socios/selector?destino=pago&pagina=2&mas=1&orden=alfabetico").get_data(as_text=True)
    assert html.count('class="selector-fila') == 10 and "Socio 050" in html and "Socio 049" not in html
    assert "Mostrando 60 de 60" in html and "Mostrar más" not in html


def test_el_fragmento_para_ingreso_trae_el_formulario_con_el_token(nav, grupo):
    html = nav.get("/socios/selector?destino=ingreso&q=alfa").get_data(as_text=True)
    assert 'action="/asistencia/ingreso"' in html and 'name="csrf_token"' in html


def test_el_fragmento_rechaza_un_destino_inventado(nav):
    assert nav.get("/socios/selector?destino=otro").status_code == 404
    assert nav.get("/socios/selector").status_code == 404


def test_los_textos_se_escapan_en_el_fragmento(nav, db, crear_socio):
    crear_socio(nombre='<script>alert(1)</script>', dni="32000001")
    html = nav.get("/socios/selector?destino=pago&q=script").get_data(as_text=True)
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


# ------------------------------------------------------------------------- privacidad
def test_recepcion_tambien_ve_la_lista(nav_recepcion, grupo):
    assert "Alfa Vigente" in nav_recepcion.get("/pagos/nuevo").get_data(as_text=True)
    assert nav_recepcion.get("/socios/selector?destino=pago").status_code == 200
    assert nav_recepcion.get("/membresias/nueva").status_code == 200


def test_sin_sesion_no_se_ve_la_lista(anonimo, grupo):
    for ruta in ("/socios/selector?destino=pago", "/membresias/nueva", "/pagos/nuevo", "/asistencia/"):
        r = anonimo.get(ruta)
        assert r.status_code == 302 and "/login" in r.headers["Location"]
        assert "Alfa Vigente" not in r.get_data(as_text=True)


def test_el_kiosco_no_puede_pedir_la_lista(kiosco_nav, grupo):
    for ruta in ("/socios/selector?destino=pago", "/socios/selector?destino=ingreso&q=alfa", "/membresias/nueva"):
        r = kiosco_nav.get(ruta)
        assert r.status_code == 302 and r.headers["Location"].endswith("/kiosco/")
        assert "Alfa Vigente" not in r.get_data(as_text=True)


def test_las_pantallas_del_kiosco_nunca_traen_la_lista(kiosco_nav, anonimo, grupo):
    paginas = [kiosco_nav.get("/kiosco/").get_data(as_text=True), anonimo.get("/kiosco/entrar").get_data(as_text=True)]
    resultado = kiosco_nav.post("/kiosco/ingreso", {"dni": "30000001"}, follow_redirects=True).get_data(as_text=True)
    for html in paginas + [resultado]:
        assert "data-selector" not in html and "selector.js" not in html and "Elegí un socio" not in html
        assert "Beta Porvencer" not in html and "Zeta Vencida" not in html


def test_un_texto_con_nombre_y_numero_busca_por_nombre_y_no_por_los_digitos(db, crear_socio):
    crear_socio(nombre="Socio 003", dni="31000003")
    crear_socio(nombre="Socio 030", dni="31000030")           # su DNI también contiene «003»
    assert _nombres(selector.listar(db, "Socio 003", hoy=HOY)) == ["Socio 003"]


def test_el_contenedor_no_usa_data_orden_para_no_confundirse_con_los_botones_de_orden(nav, grupo):
    # El JavaScript busca `[data-orden]` con closest() al hacer clic: si el contenedor lo tuviera, cada clic
    # en una fila se tomaría como un clic en el botón de orden y no abriría al socio.
    html = nav.get("/pagos/nuevo").get_data(as_text=True)
    assert html.count("data-orden=") == 2 and 'data-orden-inicial="prioridad"' in html
