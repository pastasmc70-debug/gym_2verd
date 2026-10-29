"""Asistente de primera vez, clave secreta automática y pantalla Configuración."""
import re

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app, models
from app import db as dbm
from app.routes import auth as auth_routes
from app.services import configuracion
from app.services.errors import ErrorDeNegocio
from conftest import CLAVE, CLAVE_KIOSCO, USUARIO, Navegador, hoy_real

RAPIDO = "pbkdf2:sha256:1000"  # hash barato para que los tests no tarden
CLAVE_ADMIN = "una-clave-larga-1"


def _crear_app(tmp_path, **extra):
    auth_routes._INTENTOS.clear()
    cfg = {"TESTING": True, "DATABASE": str(tmp_path / "datos" / "g.db"), "UPLOAD_DIR": str(tmp_path / "fotos"),
           "IMPORT_DIR": str(tmp_path / "imp"), "HASH_METODO": RAPIDO}
    cfg.update(extra)
    return create_app(cfg)


@pytest.fixture
def app_nueva(tmp_path, monkeypatch):
    """Instalación recién hecha: sin administrador y sin variables de entorno."""
    for var in ("GYM_SECRET_KEY", "GYM_ADMIN_USER", "GYM_ADMIN_PASSWORD_HASH", "GYM_RECEPCION_USER",
                "GYM_RECEPCION_PASSWORD_HASH", "GYM_NOMBRE", "GYM_MODULO_TIENDA", "GYM_KIOSCO_CLAVE_HASH"):
        monkeypatch.delenv(var, raising=False)
    return _crear_app(tmp_path)


@pytest.fixture
def nuevo(app_nueva):
    return Navegador(app_nueva.test_client())


def _paso1(n, nombre="Gimnasio Don Juan"):
    return n.post("/asistente/1", {"nombre": nombre})


def _paso2(n, usuario="dueno", clave=CLAVE_ADMIN, confirmacion=None):
    return n.post("/asistente/2", {"usuario": usuario, "clave": clave,
                                   "confirmacion": clave if confirmacion is None else confirmacion})


def _paso3(n, **extra):
    datos = {"p1_nombre": "Mensual", "p1_precio": "25.000", "p1_duracion": "30"}
    datos.update(extra)
    return n.post("/asistente/3", datos)


def _paso4(n, tienda="0"):
    return n.post("/asistente/4", {"tienda": tienda} if tienda is not None else {})


def _completo(n, tienda="0"):
    for r in (_paso1(n), _paso2(n), _paso3(n)):
        assert r.status_code == 302
    return _paso4(n, tienda)


def _db(app):
    return dbm.connect(app.config["DATABASE"])


# ------------------------------------------------------------- aparece solo la primera vez
@pytest.mark.parametrize("ruta", ["/", "/login", "/socios", "/pagos/", "/kiosco/entrar", "/configuracion/"])
def test_sin_administrador_todo_lleva_al_asistente(nuevo, ruta):
    r = nuevo.get(ruta)
    assert r.status_code == 302 and "/asistente/" in r.headers["Location"]


def test_el_asistente_tiene_cuatro_pasos_y_empieza_por_el_nombre(nuevo):
    r = nuevo.get("/asistente/", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Paso 1 de 4" in html and "Nombre del gimnasio" in html


def test_no_se_pueden_saltear_pasos(nuevo):
    for destino in (2, 3, 4):
        r = nuevo.get(f"/asistente/{destino}")
        assert r.status_code == 302 and r.headers["Location"].endswith("/asistente/1")
    _paso1(nuevo)
    assert nuevo.get("/asistente/3").headers["Location"].endswith("/asistente/2")
    assert nuevo.post("/asistente/4", {"tienda": "1"}).headers["Location"].endswith("/asistente/2")


def test_el_paso_que_no_existe_da_404(nuevo):
    assert nuevo.get("/asistente/5").status_code == 404


# ------------------------------------------------------------------- recorrido completo
def test_el_asistente_completo_deja_el_sistema_listo(app_nueva, nuevo):
    r = _completo(nuevo, tienda="1")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    html = nuevo.get("/").get_data(as_text=True)            # queda con la sesión de administrador iniciada
    assert "Gimnasio Don Juan" in html and "dueno" in html and "Administrador" in html
    db = _db(app_nueva)
    planes = db.execute("SELECT nombre, precio_centavos, duracion_dias, clases_por_semana FROM planes").fetchall()
    assert [tuple(p) for p in planes] == [("Mensual", 2500000, 30, None)]
    guardado = configuracion.leer_todo(db)
    assert guardado["gym_nombre"] == "Gimnasio Don Juan" and guardado["modulo_tienda"] == "1"
    assert guardado["admin_usuario"] == "dueno"
    assert CLAVE_ADMIN not in guardado["admin_clave_hash"]                    # siempre con hash
    assert check_password_hash(guardado["admin_clave_hash"], CLAVE_ADMIN)
    assert app_nueva.config["MODULO_TIENDA"] is True
    assert nuevo.get("/tienda/").status_code == 200


def test_la_configuracion_del_asistente_persiste_al_reiniciar(app_nueva, nuevo, tmp_path):
    _completo(nuevo, tienda="1")
    reiniciada = _crear_app(tmp_path)                                         # otra "ejecución" con la misma carpeta de datos
    assert reiniciada.config["GYM_NOMBRE"] == "Gimnasio Don Juan" and reiniciada.config["MODULO_TIENDA"] is True
    otro = Navegador(reiniciada.test_client())
    assert otro.get("/").status_code == 302 and "/login" in otro.get("/").headers["Location"]
    assert otro.iniciar_sesion("dueno", CLAVE_ADMIN).status_code == 302
    assert otro.iniciar_sesion("dueno", "otra-clave-larga").status_code in (200, 302)  # no rompe
    assert "Gimnasio Don Juan" in otro.get("/").get_data(as_text=True)


def test_el_usuario_del_asistente_no_entra_con_otra_clave(nuevo, app_nueva):
    _completo(nuevo)
    otro = Navegador(app_nueva.test_client())
    assert "incorrectos" in otro.iniciar_sesion("dueno", "clave-equivocada-1").get_data(as_text=True)
    assert otro.get("/socios").status_code == 302


# ------------------------------------------------------------------ no se puede repetir
def test_el_asistente_no_se_puede_repetir_con_administrador(app_nueva, nuevo):
    _completo(nuevo)
    anonimo = Navegador(app_nueva.test_client())
    for ruta in ("/asistente/", "/asistente/1", "/asistente/4"):
        r = anonimo.get(ruta)
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    r = anonimo.post("/asistente/2", {"usuario": "intruso", "clave": "clave-intrusa-123", "confirmacion": "clave-intrusa-123"})
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert configuracion.leer_todo(_db(app_nueva))["admin_usuario"] == "dueno"      # nada cambió


def test_ni_siquiera_el_administrador_logueado_puede_reabrirlo(nuevo):
    _completo(nuevo)
    assert "/login" in nuevo.get("/asistente/1").headers["Location"]


def test_el_servicio_tampoco_deja_crear_otro_administrador(app_nueva, nuevo):
    _completo(nuevo)
    db = _db(app_nueva)
    with pytest.raises(ErrorDeNegocio, match="no se puede repetir"):
        configuracion.completar_asistente(db, {}, nombre="Otro", usuario="intruso", clave_hash="x", planes=[], tienda=True)
    assert configuracion.leer_todo(db)["gym_nombre"] == "Gimnasio Don Juan"


def test_con_administrador_por_variables_de_entorno_no_hay_asistente(app):
    anonimo = Navegador(app.test_client())
    r = anonimo.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert "/login" in anonimo.get("/asistente/").headers["Location"]
    assert anonimo.iniciar_sesion().status_code == 302                         # las variables siguen funcionando


# ------------------------------------------------------------------- validaciones
@pytest.mark.parametrize("clave", ["", "corta", "123456789"])
def test_las_claves_cortas_se_rechazan(app_nueva, nuevo, clave):
    _paso1(nuevo)
    r = _paso2(nuevo, clave=clave)
    assert r.status_code == 200 and "muy corta" in r.get_data(as_text=True)
    assert nuevo.get("/asistente/3").headers["Location"].endswith("/asistente/2")      # no avanzó
    assert "admin_usuario" not in configuracion.leer_todo(_db(app_nueva))


def test_diez_caracteres_justos_alcanzan(nuevo):
    _paso1(nuevo)
    assert _paso2(nuevo, clave="1234567890").status_code == 302


def test_la_confirmacion_tiene_que_coincidir(nuevo):
    _paso1(nuevo)
    r = _paso2(nuevo, confirmacion="otra-clave-larga")
    assert r.status_code == 200 and "no coinciden" in r.get_data(as_text=True)


def test_la_clave_no_vuelve_a_mostrarse_en_la_pantalla(nuevo):
    _paso1(nuevo)
    html = _paso2(nuevo, confirmacion="otra-clave-larga").get_data(as_text=True)
    assert CLAVE_ADMIN not in html and "otra-clave-larga" not in html


@pytest.mark.parametrize("usuario", ["", "ab", "con espacio", "x" * 31, "a/b"])
def test_el_usuario_tiene_que_ser_valido(nuevo, usuario):
    _paso1(nuevo)
    r = _paso2(nuevo, usuario=usuario)
    assert r.status_code == 200 and "El usuario debe tener" in r.get_data(as_text=True)


def test_el_nombre_es_obligatorio_y_tiene_largo_maximo(nuevo):
    assert "Ingresá el nombre" in _paso1(nuevo, nombre="   ").get_data(as_text=True)
    assert "demasiado largo" in _paso1(nuevo, nombre="x" * 61).get_data(as_text=True)


def test_hace_falta_al_menos_un_plan(nuevo):
    _paso1(nuevo), _paso2(nuevo)
    r = nuevo.post("/asistente/3", {})
    assert r.status_code == 200 and "al menos un plan" in r.get_data(as_text=True)


def test_los_planes_se_validan_y_las_filas_vacias_se_ignoran(app_nueva, nuevo):
    _paso1(nuevo), _paso2(nuevo)
    r = _paso3(nuevo, p2_nombre="Trimestral", p2_precio="gratis", p2_duracion="0")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "precio válido" in html and "entre 1 y 3650" in html
    assert "Mensual" in html                                                  # lo ya cargado no se pierde
    r = _paso3(nuevo, p2_nombre="mensual", p2_precio="1000", p2_duracion="30")
    assert "Ya cargaste un plan con ese nombre" in r.get_data(as_text=True)
    r = _paso3(nuevo, p2_nombre="Trimestral", p2_precio="65.000", p2_duracion="90")   # la fila 3 queda vacía
    assert r.status_code == 302
    _paso4(nuevo)
    nombres = [p["nombre"] for p in models.listar_planes(_db(app_nueva))]
    assert sorted(nombres) == ["Mensual", "Trimestral"]


def test_hay_que_elegir_si_se_activa_la_tienda(app_nueva, nuevo):
    for r in (_paso1(nuevo), _paso2(nuevo), _paso3(nuevo)):
        assert r.status_code == 302
    r = _paso4(nuevo, tienda=None)
    assert r.status_code == 200 and "Elegí si querés activar la tienda" in r.get_data(as_text=True)
    assert "admin_usuario" not in configuracion.leer_todo(_db(app_nueva))      # todo o nada: no se guardó nada


def test_sin_tienda_la_tienda_queda_apagada(app_nueva, nuevo):
    _completo(nuevo, tienda="0")
    assert app_nueva.config["MODULO_TIENDA"] is False
    assert nuevo.get("/tienda/").status_code == 404


def test_el_usuario_del_asistente_no_puede_chocar_con_recepcion(tmp_path, monkeypatch):
    monkeypatch.delenv("GYM_ADMIN_USER", raising=False)
    app = _crear_app(tmp_path, RECEPCION_USER="Recepcion", RECEPCION_PASSWORD_HASH=generate_password_hash("x" * 12, method=RAPIDO))
    n = Navegador(app.test_client())
    _paso1(n)
    assert "ya lo usa recepción" in _paso2(n, usuario="recepcion").get_data(as_text=True)


# -------------------------------------------------------------------- clave secreta
def test_la_clave_secreta_se_genera_sola_y_se_guarda_en_la_carpeta_de_datos(app_nueva, tmp_path):
    archivo = tmp_path / "datos" / "secret_key"
    clave = archivo.read_text()
    assert re.fullmatch(r"[0-9a-f]{64}", clave) and app_nueva.config["SECRET_KEY"] == clave


def test_la_clave_secreta_es_la_misma_al_reiniciar(app_nueva, tmp_path):
    assert _crear_app(tmp_path).config["SECRET_KEY"] == app_nueva.config["SECRET_KEY"]


def test_dos_instalaciones_tienen_claves_distintas(app_nueva, tmp_path_factory, monkeypatch):
    otra = _crear_app(tmp_path_factory.mktemp("otra"))
    assert otra.config["SECRET_KEY"] != app_nueva.config["SECRET_KEY"]


def test_si_el_archivo_de_la_clave_esta_danado_se_genera_uno_nuevo(tmp_path):
    carpeta = tmp_path / "d"
    carpeta.mkdir()
    (carpeta / "secret_key").write_text("basura")
    clave = configuracion.clave_secreta(carpeta)
    assert re.fullmatch(r"[0-9a-f]{64}", clave) and (carpeta / "secret_key").read_text() == clave


def test_con_variable_de_entorno_no_se_crea_el_archivo(tmp_path, monkeypatch):
    monkeypatch.delenv("GYM_ADMIN_USER", raising=False)
    monkeypatch.delenv("GYM_ADMIN_PASSWORD_HASH", raising=False)
    app = _crear_app(tmp_path, SECRET_KEY="la-mia-por-entorno")
    assert app.config["SECRET_KEY"] == "la-mia-por-entorno" and not (tmp_path / "datos" / "secret_key").exists()


def test_la_sesion_sigue_valida_despues_de_reiniciar(app_nueva, nuevo, tmp_path):
    _completo(nuevo)
    reiniciada = _crear_app(tmp_path)
    cliente = reiniciada.test_client()
    cliente.set_cookie("session", nuevo.client.get_cookie("session").value)
    assert cliente.get("/").status_code == 200


def test_un_administrador_a_medias_por_entorno_sigue_siendo_un_error(tmp_path, monkeypatch):
    from app.config import ErrorDeConfiguracion
    monkeypatch.delenv("GYM_ADMIN_USER", raising=False)
    with pytest.raises(ErrorDeConfiguracion, match="GYM_ADMIN_USER"):
        _crear_app(tmp_path, ADMIN_PASSWORD_HASH="hash")


# ------------------------------------------------------------------ pantalla Configuración
def _guardar(nav, **extra):
    datos = {"gym_nombre": "Gym Nuevo"}
    datos.update(extra)
    return nav.post("/configuracion/", datos, follow_redirects=True)


def test_el_administrador_ve_la_configuracion_con_los_valores_actuales(nav):
    html = nav.get("/configuracion/").get_data(as_text=True)
    assert "Mi Gimnasio" in html and "Reglas de ingreso" in html and "Modo kiosco" in html
    assert "Todavía no hay clave de kiosco" not in html                       # el fixture ya trae una


def test_recepcion_y_anonimos_no_entran_a_la_configuracion(nav_recepcion, anonimo):
    assert nav_recepcion.get("/configuracion/").status_code == 403
    assert nav_recepcion.post("/configuracion/", {"gym_nombre": "Hackeado"}).status_code == 403
    r = anonimo.get("/configuracion/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert "Configuración" not in nav_recepcion.get("/").get_data(as_text=True)


def test_guardar_la_configuracion_la_aplica_y_persiste(app, nav, tmp_path):
    html = _guardar(nav, modulo_tienda="1", acceso_sin_pago="1", permitir_reingreso="1",
                    kiosco_teclado="1").get_data(as_text=True)
    assert "Configuración guardada" in html and "Gym Nuevo" in html           # el nombre se ve en el menú sin reiniciar
    c = app.config
    assert (c["GYM_NOMBRE"], c["MODULO_TIENDA"], c["ACCESO_SIN_PAGO"], c["PERMITIR_REINGRESO"]) == ("Gym Nuevo", True, True, True)
    assert c["LIMITAR_CLASES_SEMANA"] is False and c["KIOSCO_SONIDO"] is False   # lo destildado queda apagado
    assert c["KIOSCO_TECLADO_PANTALLA"] is True
    reiniciada = _crear_app(tmp_path, DATABASE=app.config["DATABASE"], ADMIN_USER=USUARIO,
                            ADMIN_PASSWORD_HASH=app.config["ADMIN_PASSWORD_HASH"])
    assert (reiniciada.config["GYM_NOMBRE"], reiniciada.config["MODULO_TIENDA"]) == ("Gym Nuevo", True)
    assert reiniciada.config["PERMITIR_REINGRESO"] is True and reiniciada.config["LIMITAR_CLASES_SEMANA"] is False


def test_lo_guardado_pisa_a_la_variable_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("GYM_NOMBRE", "Nombre del entorno")
    monkeypatch.setenv("GYM_PERMITIR_REINGRESO", "1")
    monkeypatch.setenv("GYM_ADMIN_USER", USUARIO)
    monkeypatch.setenv("GYM_ADMIN_PASSWORD_HASH", generate_password_hash(CLAVE, method=RAPIDO))
    app = _crear_app(tmp_path)
    assert app.config["GYM_NOMBRE"] == "Nombre del entorno" and app.config["PERMITIR_REINGRESO"] is True   # alternativa
    n = Navegador(app.test_client())
    n.iniciar_sesion()
    _guardar(n, gym_nombre="Nombre de la pantalla")                           # permitir_reingreso destildado
    assert app.config["GYM_NOMBRE"] == "Nombre de la pantalla" and app.config["PERMITIR_REINGRESO"] is False


def test_un_cambio_vale_en_otro_proceso_sin_reiniciar(app, nav, tmp_path):
    _guardar(nav, gym_nombre="Cambiado")
    otra = _crear_app(tmp_path, DATABASE=app.config["DATABASE"], ADMIN_USER=USUARIO,
                      ADMIN_PASSWORD_HASH=app.config["ADMIN_PASSWORD_HASH"])
    otra.config["GYM_NOMBRE"] = "viejo"                                       # un proceso que quedó con el valor anterior
    n2 = Navegador(otra.test_client())
    n2.iniciar_sesion()
    assert "Cambiado" in n2.get("/").get_data(as_text=True)


def test_el_nombre_es_obligatorio_en_la_configuracion(app, nav):
    html = _guardar(nav, gym_nombre="  ").get_data(as_text=True)
    assert "Ingresá el nombre" in html and app.config["GYM_NOMBRE"] == "Mi Gimnasio"


def test_una_regla_de_ingreso_cambiada_desde_la_pantalla_se_aplica(app, nav, db, plan, crear_socio):
    from app.services import memberships
    socio = crear_socio(dni="38000001")
    memberships.asignar_plan(db, socio, plan, hoy_real())
    nav.post("/asistencia/ingreso", {"q": "38000001"})
    assert db.execute("SELECT COUNT(*) FROM asistencias").fetchone()[0] == 0   # sin pago no entra (regla por defecto)
    _guardar(nav, acceso_sin_pago="1", limitar_clases_semana="1")
    nav.post("/asistencia/ingreso", {"q": "38000001"})
    assert db.execute("SELECT COUNT(*) FROM asistencias").fetchone()[0] == 1   # ahora sí


def test_apagar_la_tienda_desde_la_pantalla_la_oculta(app, nav):
    _guardar(nav, modulo_tienda="1")
    assert nav.get("/tienda/").status_code == 200
    _guardar(nav)
    assert nav.get("/tienda/").status_code == 404


def test_la_clave_del_kiosco_se_guarda_con_hash_y_funciona(app, nav):
    html = _guardar(nav, kiosco_clave="kiosco-nueva-123", kiosco_clave_confirmacion="kiosco-nueva-123").get_data(as_text=True)
    assert "Configuración guardada" in html
    hash_guardado = configuracion.leer_todo(dbm.connect(app.config["DATABASE"]))["kiosco_clave_hash"]
    assert "kiosco-nueva-123" not in hash_guardado and check_password_hash(hash_guardado, "kiosco-nueva-123")
    puerta = Navegador(app.test_client())
    assert puerta.post("/kiosco/entrar", {"clave": CLAVE_KIOSCO}).status_code == 200        # la vieja ya no sirve
    assert puerta.post("/kiosco/entrar", {"clave": "kiosco-nueva-123"}).status_code == 302


def test_dejar_vacia_la_clave_del_kiosco_no_la_cambia(app, nav):
    _guardar(nav)
    assert check_password_hash(app.config["KIOSCO_CLAVE_HASH"], CLAVE_KIOSCO)


def test_la_clave_del_kiosco_se_valida(app, nav):
    html = _guardar(nav, kiosco_clave="corta", kiosco_clave_confirmacion="corta").get_data(as_text=True)
    assert "muy corta" in html and check_password_hash(app.config["KIOSCO_CLAVE_HASH"], CLAVE_KIOSCO)
    html = _guardar(nav, kiosco_clave="kiosco-nueva-123", kiosco_clave_confirmacion="otra").get_data(as_text=True)
    assert "no coinciden" in html and check_password_hash(app.config["KIOSCO_CLAVE_HASH"], CLAVE_KIOSCO)
    assert app.config["GYM_NOMBRE"] == "Mi Gimnasio"                                          # con errores no se guarda nada


def test_la_migracion_crea_la_tabla_en_una_base_existente(tmp_path):
    import sqlite3
    conn = sqlite3.connect(tmp_path / "v.db")
    conn.row_factory = sqlite3.Row
    from app import migraciones
    conn.executescript(dbm.SCHEMA.read_text(encoding="utf-8"))
    for numero, sql in migraciones.MIGRACIONES:
        if numero <= 3:
            conn.executescript(sql)
    conn.execute("INSERT INTO planes (nombre, precio_centavos, duracion_dias) VALUES ('X', 100, 30)")
    conn.commit()
    dbm.init_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == migraciones.VERSION_ACTUAL
    assert conn.execute("SELECT COUNT(*) FROM configuracion").fetchone()[0] == 0
    assert conn.execute("SELECT nombre FROM planes").fetchone()[0] == "X"
