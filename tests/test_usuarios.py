"""Cuentas de recepción en la base: alta, desactivación, cambio de clave, permisos, compatibilidad y registro de quién."""
import io
import re

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app, models
from app.services import tienda, usuarios
from app.services.errors import ErrorDeNegocio
from conftest import CLAVE, CLAVE_REC, USUARIO, USUARIO_REC, Navegador, hoy_real

CLAVE_NUEVA = "clave-de-ana-12345"


def _alta(nav, usuario="ana.perez", clave=CLAVE_NUEVA, clave2=None):
    return nav.post("/usuarios/nuevo", {"usuario": usuario, "clave": clave, "clave2": clave if clave2 is None else clave2})


def _id(db, usuario):
    return usuarios.obtener_por_nombre(db, usuario)["id"]


# ------------------------------------------------------------------ servicio
def test_usuario_valido_se_normaliza_a_minusculas(db):
    d, errores = usuarios.validar_nuevo(db, {"usuario": "  Ana.Perez ", "clave": CLAVE_NUEVA, "clave2": CLAVE_NUEVA}, USUARIO)
    assert not errores and d["usuario"] == "ana.perez"


@pytest.mark.parametrize("nombre", ["", "ab", "a" * 31, "ana perez", "ana@gym", "ánita", "ana/perez"])
def test_nombres_de_usuario_invalidos(db, nombre):
    _, errores = usuarios.validar_nuevo(db, {"usuario": nombre, "clave": CLAVE_NUEVA, "clave2": CLAVE_NUEVA}, USUARIO)
    assert "usuario" in errores


def test_no_se_repite_el_nombre_ni_el_del_administrador(db):
    usuarios.crear(db, "ana", CLAVE_NUEVA)
    for repetido in ("ana", "ANA", USUARIO, USUARIO.upper()):
        _, errores = usuarios.validar_nuevo(db, {"usuario": repetido, "clave": CLAVE_NUEVA, "clave2": CLAVE_NUEVA}, USUARIO)
        assert "ya está en uso" in errores["usuario"], repetido


@pytest.mark.parametrize("clave,clave2,texto", [("corta123", "corta123", "al menos 10"), ("", "", "al menos 10"),
                                                (CLAVE_NUEVA, CLAVE_NUEVA + "x", "no coinciden")])
def test_validacion_de_clave(db, clave, clave2, texto):
    _, errores = usuarios.validar_nuevo(db, {"usuario": "ana", "clave": clave, "clave2": clave2}, USUARIO)
    assert texto in errores["clave"]


def test_la_clave_de_diez_caracteres_justos_se_acepta(db):
    _, errores = usuarios.validar_nuevo(db, {"usuario": "ana", "clave": "1234567890", "clave2": "1234567890"}, USUARIO)
    assert not errores


def test_la_clave_se_guarda_con_hash_nunca_en_texto(db):
    uid = usuarios.crear(db, "ana", CLAVE_NUEVA)
    guardada = usuarios.obtener(db, uid)["clave_hash"]
    assert CLAVE_NUEVA not in guardada and check_password_hash(guardada, CLAVE_NUEVA)


def test_autenticar(db):
    uid = usuarios.crear(db, "ana", CLAVE_NUEVA)
    assert usuarios.autenticar(db, "ana", CLAVE_NUEVA)["id"] == uid
    assert usuarios.autenticar(db, " ANA ", CLAVE_NUEVA)["id"] == uid          # no distingue mayúsculas
    assert usuarios.autenticar(db, "ana", "otra-clave-larga") is None
    assert usuarios.autenticar(db, "nadie", CLAVE_NUEVA) is None
    assert usuarios.autenticar(db, "ana", "") is None and usuarios.autenticar(db, "ana", None) is None


def test_una_cuenta_desactivada_no_autentica_y_al_reactivarla_si(db):
    uid = usuarios.crear(db, "ana", CLAVE_NUEVA)
    usuarios.cambiar_activo(db, uid, False)
    assert usuarios.autenticar(db, "ana", CLAVE_NUEVA) is None
    assert usuarios.obtener(db, uid)["desactivado_en"]
    usuarios.cambiar_activo(db, uid, True)
    assert usuarios.autenticar(db, "ana", CLAVE_NUEVA) is not None and usuarios.obtener(db, uid)["desactivado_en"] is None


def test_cambiar_clave(db):
    uid = usuarios.crear(db, "ana", CLAVE_NUEVA)
    usuarios.cambiar_clave(db, uid, "otra-clave-nueva-1", "otra-clave-nueva-1")
    assert usuarios.autenticar(db, "ana", CLAVE_NUEVA) is None and usuarios.autenticar(db, "ana", "otra-clave-nueva-1")
    with pytest.raises(ErrorDeNegocio, match="al menos 10"):
        usuarios.cambiar_clave(db, uid, "corta", "corta")
    with pytest.raises(ErrorDeNegocio, match="no coinciden"):
        usuarios.cambiar_clave(db, uid, "otra-clave-nueva-2", "distinta-clave-99")
    with pytest.raises(ErrorDeNegocio, match="No encontramos"):
        usuarios.cambiar_clave(db, 999, "otra-clave-nueva-1", "otra-clave-nueva-1")
    assert usuarios.autenticar(db, "ana", "otra-clave-nueva-1")                # los rechazos no la cambiaron


def test_los_usuarios_no_se_borran_se_listan_activos_primero(db):
    a = usuarios.crear(db, "zeta", CLAVE_NUEVA); usuarios.crear(db, "beto", CLAVE_NUEVA)
    usuarios.cambiar_activo(db, a, False)
    assert [u["usuario"] for u in usuarios.listar(db)] == ["beto", USUARIO_REC, "zeta"]     # `recep` viene del entorno


# ---------------------------------------------------- compatibilidad con variables de entorno
def test_las_variables_de_recepcion_se_importan_como_primer_usuario(db):
    fila = usuarios.obtener_por_nombre(db, USUARIO_REC)         # la fixture `app` trae las variables de entorno
    assert fila["activo"] == 1 and fila["rol"] == "recepcion" and fila["creado_por"] == "variables de entorno"
    assert check_password_hash(fila["clave_hash"], CLAVE_REC)


def test_importar_de_entorno_no_duplica_ni_resucita(db, app):
    cfg = app.config
    assert usuarios.importar_de_entorno(db, cfg["RECEPCION_USER"], cfg["RECEPCION_PASSWORD_HASH"]) is False
    usuarios.cambiar_activo(db, _id(db, USUARIO_REC), False)
    app2 = create_app({k: cfg[k] for k in ("TESTING", "SECRET_KEY", "ADMIN_USER", "ADMIN_PASSWORD_HASH", "RECEPCION_USER",
                                           "RECEPCION_PASSWORD_HASH", "DATABASE", "UPLOAD_DIR", "IMPORT_DIR")})
    assert app2 is not app
    assert db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 1
    assert usuarios.obtener_por_nombre(db, USUARIO_REC)["activo"] == 0          # sigue desactivada tras reiniciar


def test_sin_variables_no_se_crea_nada(db):
    assert usuarios.importar_de_entorno(db, None, None) is False
    assert usuarios.importar_de_entorno(db, "x", None) is False


def test_la_clave_de_las_variables_sigue_sirviendo_para_entrar(anonimo):
    r = anonimo.iniciar_sesion(USUARIO_REC, CLAVE_REC)
    assert r.status_code == 302 and "Recepción" in anonimo.get("/").get_data(as_text=True)


# ------------------------------------------------------------------ pantallas
def test_el_administrador_crea_una_cuenta_y_esa_persona_entra(nav, app, db):
    r = _alta(nav, "Ana.Perez")
    assert r.status_code == 302
    assert "ana.perez" in nav.get("/usuarios/").get_data(as_text=True)
    ana = Navegador(app.test_client())
    assert ana.iniciar_sesion("ana.perez", CLAVE_NUEVA).status_code == 302
    html = ana.get("/").get_data(as_text=True)
    assert "ana.perez · Recepción" in html


def test_la_lista_no_muestra_nunca_las_claves(nav, db):
    _alta(nav)
    html = nav.get("/usuarios/").get_data(as_text=True)
    assert CLAVE_NUEVA not in html and "pbkdf2" not in html and "scrypt" not in html


def test_formulario_con_errores_no_crea_y_no_devuelve_la_clave(nav, db):
    r = _alta(nav, "ab", "corta", "corta")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Revisá los campos" in html and "entre 3 y 30" in html and "al menos 10" in html
    assert 'value="corta"' not in html
    assert usuarios.obtener_por_nombre(db, "ab") is None
    assert "no coinciden" in _alta(nav, "ana", CLAVE_NUEVA, "otra-distinta-123").get_data(as_text=True)
    assert "ya está en uso" in _alta(nav, USUARIO).get_data(as_text=True)


def test_sin_token_csrf_no_se_crea(anonimo, nav, db):
    r = nav.client.post("/usuarios/nuevo", data={"usuario": "ana", "clave": CLAVE_NUEVA, "clave2": CLAVE_NUEVA})
    assert r.status_code == 400 and usuarios.obtener_por_nombre(db, "ana") is None


def test_recepcion_no_puede_ver_ni_crear_ni_tocar_usuarios(nav_recepcion, nav, db):
    _alta(nav)
    uid = _id(db, "ana.perez")
    for ruta in ("/usuarios/", "/usuarios/nuevo", f"/usuarios/{uid}/clave"):
        assert nav_recepcion.get(ruta).status_code == 403, ruta
    assert _alta(nav_recepcion, "intrusa").status_code == 403
    assert nav_recepcion.post(f"/usuarios/{uid}/clave", {"clave": "otra-clave-nueva-1", "clave2": "otra-clave-nueva-1"}).status_code == 403
    assert nav_recepcion.post(f"/usuarios/{uid}/desactivar").status_code == 403
    assert usuarios.obtener_por_nombre(db, "intrusa") is None
    assert usuarios.obtener(db, uid)["activo"] == 1 and usuarios.autenticar(db, "ana.perez", CLAVE_NUEVA)


def test_el_menu_usuarios_es_solo_del_administrador(nav, nav_recepcion):
    assert ">Usuarios<" in nav.get("/").get_data(as_text=True)
    assert ">Usuarios<" not in nav_recepcion.get("/").get_data(as_text=True)


def test_desactivar_impide_entrar_y_cierra_la_sesion_abierta(nav, app, db):
    _alta(nav)
    ana = Navegador(app.test_client())
    ana.iniciar_sesion("ana.perez", CLAVE_NUEVA)
    assert ana.get("/asistencia/").status_code == 200

    nav.post(f"/usuarios/{_id(db, 'ana.perez')}/desactivar")

    r = ana.get("/asistencia/")                                                  # sesión que ya tenía abierta
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert ana.get("/asistencia/").status_code == 302
    r = ana.iniciar_sesion("ana.perez", CLAVE_NUEVA)
    assert r.status_code == 200 and "incorrectos" in r.get_data(as_text=True)    # y tampoco puede volver a entrar

    nav.post(f"/usuarios/{_id(db, 'ana.perez')}/activar")
    assert ana.iniciar_sesion("ana.perez", CLAVE_NUEVA).status_code == 302


def test_cambiar_la_clave_desde_la_pantalla_cierra_la_sesion_vieja(nav, app, db):
    _alta(nav)
    ana = Navegador(app.test_client())
    ana.iniciar_sesion("ana.perez", CLAVE_NUEVA)
    uid = _id(db, "ana.perez")

    corta = nav.post(f"/usuarios/{uid}/clave", {"clave": "corta", "clave2": "corta"})
    assert corta.status_code == 200 and "al menos 10" in corta.get_data(as_text=True)
    assert ana.get("/asistencia/").status_code == 200                            # no cambió nada

    r = nav.post(f"/usuarios/{uid}/clave", {"clave": "clave-renovada-99", "clave2": "clave-renovada-99"})
    assert r.status_code == 302
    assert ana.get("/asistencia/").status_code == 302                            # la sesión con la clave vieja se cerró
    assert "incorrectos" in ana.iniciar_sesion("ana.perez", CLAVE_NUEVA).get_data(as_text=True)
    assert ana.iniciar_sesion("ana.perez", "clave-renovada-99").status_code == 302


def test_acciones_con_cuentas_inexistentes(nav):
    assert nav.get("/usuarios/999/clave").status_code == 404
    assert nav.post("/usuarios/999/desactivar").status_code == 404
    assert nav.post("/usuarios/999/borrar").status_code == 404                   # no existe la acción «borrar»


def test_el_administrador_no_aparece_como_cuenta_de_la_base(nav, db):
    assert usuarios.obtener_por_nombre(db, USUARIO) is None
    assert "Usuarios de recepción" in nav.get("/usuarios/").get_data(as_text=True)


# ------------------------------------------ cada acción queda con el nombre de quien la hizo
def test_cada_accion_queda_a_nombre_de_la_persona_que_la_hizo(nav, db, plan, crear_socio, app):
    app.config["ACCESO_SIN_PAGO"] = True
    app.config["MODULO_TIENDA"] = True
    _alta(nav, "ana.perez")
    ana = Navegador(app.test_client())
    ana.iniciar_sesion("ana.perez", CLAVE_NUEVA)

    ana.post("/socios/nuevo", {"nombre": "Nuevo Socio", "dni": "40111222", "telefono": "11 5555-0000"})
    socio_id = models.obtener_socio_por_dni(db, "40111222")["id"]
    ana.post(f"/socios/{socio_id}/membresia", {"plan_id": plan, "fecha_inicio": hoy_real().isoformat()})
    ana.post(f"/pagos/nuevo?socio_id={socio_id}", {"socio_id": socio_id, "monto": "25000", "fecha": hoy_real().isoformat(), "metodo": "efectivo"})
    ana.post("/asistencia/ingreso", {"q": "40111222"})
    d, _ = tienda.validar_producto(db, dict(nombre="Whey", marca="", categoria="", precio="1000", costo="", stock="5", stock_minimo="1"))
    pid = tienda.crear_producto(db, d, "admin")
    ana.post("/tienda/", {f"cant_{pid}": "1", "metodo": "efectivo"})

    uno = lambda sql: db.execute(sql, (socio_id,)).fetchone()[0]
    assert uno("SELECT cargada_por FROM membresias WHERE socio_id = ?") == "ana.perez"
    assert uno("SELECT cargado_por FROM pagos WHERE socio_id = ?") == "ana.perez"
    assert uno("SELECT registrado_por FROM asistencias WHERE socio_id = ?") == "ana.perez"
    assert db.execute("SELECT cargada_por FROM ventas").fetchone()[0] == "ana.perez"

    # y se ve en las pantallas donde hoy figura «quién»
    for ruta in ("/pagos/", "/asistencia/", "/tienda/ventas", "/caja/"):
        assert "ana.perez" in nav.get(ruta).get_data(as_text=True), ruta
    pago_id = db.execute("SELECT id FROM pagos WHERE socio_id = ?", (socio_id,)).fetchone()[0]
    nav.post(f"/pagos/{pago_id}/anular", {"motivo": "Error de carga"})
    assert models.obtener_pago(db, pago_id)["anulado_por"] == USUARIO
    assert USUARIO in nav.get(f"/socios/{socio_id}").get_data(as_text=True)


def test_una_cuenta_desactivada_conserva_su_nombre_en_el_historial(nav, db, app, plan):
    app.config["ACCESO_SIN_PAGO"] = True
    _alta(nav, "ana.perez")
    ana = Navegador(app.test_client()); ana.iniciar_sesion("ana.perez", CLAVE_NUEVA)
    ana.post("/socios/nuevo", {"nombre": "Nuevo Socio", "dni": "40111222", "telefono": "11 5555-0000"})
    socio_id = models.obtener_socio_por_dni(db, "40111222")["id"]
    ana.post(f"/socios/{socio_id}/membresia", {"plan_id": plan, "fecha_inicio": hoy_real().isoformat()})
    ana.post("/asistencia/ingreso", {"q": "40111222"})
    assert db.execute("SELECT registrado_por FROM asistencias").fetchone()[0] == "ana.perez"
    nav.post(f"/usuarios/{_id(db, 'ana.perez')}/desactivar")
    assert "ana.perez" in nav.get("/asistencia/").get_data(as_text=True)
    assert "Nuevo Socio" in nav.get("/asistencia/").get_data(as_text=True)
    assert "ya está en uso" in _alta(nav, "ana.perez").get_data(as_text=True)    # el nombre no se reutiliza


# ------------------------------------------------------------------ importación
def _csv_socios(*filas):
    return ("nombre;dni;telefono;email;fecha_alta;estado;notas\n" + "\n".join(filas) + "\n").encode()


def test_la_importacion_queda_registrada_con_quien_la_hizo(nav, db):
    r = nav.post("/datos/importar/", {"archivo": (io.BytesIO(_csv_socios("Ana Paz;30111222;11 5555-1234;;;;", "Mal;1;1;;;;")), "s.csv")})
    token = re.search(r'name="token" value="([0-9a-f]{32})"', r.get_data(as_text=True)).group(1)
    assert db.execute("SELECT COUNT(*) FROM importaciones").fetchone()[0] == 0     # la vista previa no registra nada
    nav.post("/datos/importar/confirmar", {"token": token})
    fila = db.execute("SELECT * FROM importaciones").fetchone()
    assert (fila["usuario"], fila["importadas"], fila["omitidas"]) == (USUARIO, 1, 1) and fila["creada_en"]
    html = nav.get("/datos/importar/").get_data(as_text=True)
    assert "Últimas importaciones" in html and USUARIO in html


def test_sin_importaciones_la_pantalla_lo_dice(nav):
    assert "Todavía no se importó nada" in nav.get("/datos/importar/").get_data(as_text=True)


# ------------------------------------------- junto con el asistente de primera vez (instalación nueva)
def test_instalacion_nueva_administrador_del_asistente_crea_cuentas_de_recepcion(tmp_path, monkeypatch):
    from test_asistente_configuracion import CLAVE_ADMIN, _completo, _crear_app
    for var in ("GYM_SECRET_KEY", "GYM_ADMIN_USER", "GYM_ADMIN_PASSWORD_HASH", "GYM_RECEPCION_USER",
                "GYM_RECEPCION_PASSWORD_HASH", "GYM_NOMBRE", "GYM_MODULO_TIENDA", "GYM_KIOSCO_CLAVE_HASH"):
        monkeypatch.delenv(var, raising=False)
    app = _crear_app(tmp_path)
    dueno = Navegador(app.test_client())
    _completo(dueno)                                                  # el asistente deja al dueño con la sesión abierta

    assert dueno.get("/usuarios/").status_code == 200
    assert _alta(dueno, "ana.perez").status_code == 302
    ana = Navegador(app.test_client())
    assert ana.iniciar_sesion("ana.perez", CLAVE_NUEVA).status_code == 302
    assert ana.get("/asistencia/").status_code == 200
    for ruta in ("/usuarios/", "/usuarios/nuevo", "/configuracion/"):
        assert ana.get(ruta).status_code == 403, ruta
    assert "dueno" in _alta(dueno, "dueno").get_data(as_text=True) and "ya está en uso" in _alta(dueno, "dueno").get_data(as_text=True)
