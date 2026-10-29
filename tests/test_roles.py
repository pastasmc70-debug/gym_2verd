"""Administrador y recepción: qué puede hacer cada uno y quién queda registrado."""
import time
from datetime import timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import config as cfg_mod
from app import create_app, models
from app.services import memberships, payments
from conftest import CLAVE, CLAVE_REC, USUARIO, USUARIO_REC, hoy_real

PRECIO = 2500000


@pytest.fixture
def datos(db, plan, crear_socio):
    """Un socio con plan y un pago, para tener qué anular."""
    socio_id = crear_socio(nombre="Socio Uno", dni="39000001")
    m = memberships.asignar_plan(db, socio_id, plan, hoy_real())["membresia_id"]
    pago = payments.registrar_pago(db, socio_id, PRECIO, hoy_real(), "efectivo")["pago_id"]
    sin_pagos = crear_socio(nombre="Socio Dos", dni="39000002")
    m2 = memberships.asignar_plan(db, sin_pagos, plan, hoy_real())["membresia_id"]
    return dict(socio=socio_id, membresia_con_pago=m, pago=pago, plan=plan, membresia_libre=m2)


PERMITIDAS = ["/", "/socios", "/socios/nuevo", "/planes/", "/pagos/", "/pagos/nuevo", "/asistencia/", "/alertas/", "/caja/"]


@pytest.mark.parametrize("ruta", PERMITIDAS)
def test_recepcion_puede_entrar_a_lo_operativo(nav_recepcion, ruta):
    assert nav_recepcion.get(ruta).status_code == 200


def _prohibidas(d):
    return [
        ("GET", "/planes/nuevo"), ("GET", f"/planes/{d['plan']}/editar"),
        ("POST", f"/planes/{d['plan']}/desactivar"), ("POST", f"/planes/{d['plan']}/activar"),
        ("POST", f"/planes/{d['plan']}/eliminar"),
        ("GET", "/exportar/"), ("GET", "/exportar/socios.csv"), ("GET", "/exportar/pagos.csv"),
        ("GET", "/datos/importar/"), ("POST", "/datos/importar/confirmar"), ("POST", "/datos/respaldo/"),
        ("GET", f"/pagos/{d['pago']}/anular"), ("POST", f"/pagos/{d['pago']}/anular"),
        ("GET", f"/membresias/{d['membresia_libre']}/anular"), ("POST", f"/membresias/{d['membresia_libre']}/anular"),
    ]


def test_recepcion_no_puede_anular_exportar_ni_editar_planes(nav_recepcion, db, datos):
    for metodo, ruta in _prohibidas(datos):
        r = nav_recepcion.get(ruta) if metodo == "GET" else nav_recepcion.post(ruta, {"motivo": "x"})
        assert r.status_code == 403, f"{metodo} {ruta} debería estar prohibido para recepción"
    # y no cambió nada
    assert models.obtener_pago(db, datos["pago"])["anulado"] == 0
    assert models.obtener_membresia(db, datos["membresia_libre"])["anulada"] == 0
    assert models.obtener_plan(db, datos["plan"])["activo"] == 1


def test_el_administrador_si_puede_todo_eso(nav, datos):
    for metodo, ruta in _prohibidas(datos):
        if metodo == "GET":
            assert nav.get(ruta).status_code == 200, ruta


def test_la_pagina_de_sin_permiso_explica_que_pasa(nav_recepcion):
    html = nav_recepcion.get("/exportar/").get_data(as_text=True)
    assert "no tiene permiso" in html


def test_el_menu_y_los_botones_se_adaptan_al_rol(nav, nav_recepcion, datos):
    ficha = f"/socios/{datos['socio']}"
    admin, rec = nav.get(ficha).get_data(as_text=True), nav_recepcion.get(ficha).get_data(as_text=True)
    assert ">Datos<" in admin and "Anular" in admin and "Administrador" in admin
    assert ">Datos<" not in rec and "Anular" not in rec and "Recepción" in rec
    assert "Nuevo plan" in nav.get("/planes/").get_data(as_text=True)
    planes_rec = nav_recepcion.get("/planes/").get_data(as_text=True)
    assert "Nuevo plan" not in planes_rec and "Editar" not in planes_rec and "Mensual" in planes_rec


def test_recepcion_puede_cargar_socios_ingresos_y_pagos_y_queda_registrado(nav_recepcion, db, plan, crear_socio, app):
    app.config["ACCESO_SIN_PAGO"] = True
    r = nav_recepcion.post("/socios/nuevo", {"nombre": "Nuevo Socio", "dni": "40111222", "telefono": "11 5555-0000"},
                           follow_redirects=True)
    assert "Socio creado" in r.get_data(as_text=True)
    socio_id = models.obtener_socio_por_dni(db, "40111222")["id"]

    nav_recepcion.post(f"/socios/{socio_id}/membresia", {"plan_id": plan, "fecha_inicio": hoy_real().isoformat()})
    nav_recepcion.post(f"/pagos/nuevo?socio_id={socio_id}", {"socio_id": socio_id, "monto": "25000",
                                                             "fecha": hoy_real().isoformat(), "metodo": "efectivo"})
    nav_recepcion.post("/asistencia/ingreso", {"q": "40111222"})

    assert models.membresia_actual(db, socio_id)["id"]
    assert db.execute("SELECT cargada_por FROM membresias WHERE socio_id = ?", (socio_id,)).fetchone()[0] == USUARIO_REC
    assert db.execute("SELECT cargado_por FROM pagos WHERE socio_id = ?", (socio_id,)).fetchone()[0] == USUARIO_REC
    assert db.execute("SELECT registrado_por FROM asistencias WHERE socio_id = ?", (socio_id,)).fetchone()[0] == USUARIO_REC


def test_las_pantallas_muestran_quien_cargo_cada_cosa(nav_recepcion, nav, db, datos, app):
    app.config["ACCESO_SIN_PAGO"] = True
    nav_recepcion.post("/asistencia/ingreso", {"q": "39000001"})
    assert "recepcion" in nav.get("/asistencia/").get_data(as_text=True)
    pagos = nav.get("/pagos/").get_data(as_text=True)
    assert "<th>Cargó</th>" in pagos


def test_la_anulacion_guarda_quien_la_hizo(nav, db, datos):
    nav.post(f"/pagos/{datos['pago']}/anular", {"motivo": "Error"})
    assert models.obtener_pago(db, datos["pago"])["anulado_por"] == USUARIO
    nav.post(f"/membresias/{datos['membresia_libre']}/anular", {"motivo": "Error"})
    assert models.obtener_membresia(db, datos["membresia_libre"])["anulada_por"] == USUARIO


# --------------------------------------------------------------------------- sesiones
def test_cada_usuario_entra_solo_con_su_clave(anonimo):
    assert anonimo.iniciar_sesion(USUARIO, CLAVE_REC).status_code == 200      # vuelve al login con error
    assert anonimo.get("/").status_code == 302
    assert anonimo.iniciar_sesion(USUARIO_REC, CLAVE).status_code == 200
    assert anonimo.get("/").status_code == 302
    assert anonimo.iniciar_sesion(USUARIO_REC, CLAVE_REC).status_code == 302
    assert anonimo.get("/").status_code == 200


def test_sin_sesion_se_pide_login(anonimo):
    r = anonimo.get("/pagos/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_la_sesion_del_personal_vence(app, nav):
    assert nav.get("/").status_code == 200
    with nav.client.session_transaction() as s:
        s["inicio"] = time.time() - (app.config["SESION_PERSONAL_HORAS"] + 1) * 3600
    assert nav.get("/").status_code == 302


def test_cerrar_sesion_de_recepcion(nav_recepcion):
    nav_recepcion.post("/logout")
    assert nav_recepcion.get("/").status_code == 302


# ---------------------------------------------------------------------- configuración
def _config(**extra):
    base = dict(SECRET_KEY="x", ADMIN_USER="admin", ADMIN_PASSWORD_HASH="h", RECEPCION_USER=None,
                RECEPCION_PASSWORD_HASH=None, DIAS_ALERTA=7, KIOSCO_MAX_INTENTOS_POR_MINUTO=15)
    base.update(extra)
    return base


def test_recepcion_es_opcional():
    cfg_mod.validar_config(_config())


def test_recepcion_necesita_usuario_y_hash_juntos():
    with pytest.raises(cfg_mod.ErrorDeConfiguracion, match="las dos variables"):
        cfg_mod.validar_config(_config(RECEPCION_USER="recep"))
    with pytest.raises(cfg_mod.ErrorDeConfiguracion, match="las dos variables"):
        cfg_mod.validar_config(_config(RECEPCION_PASSWORD_HASH="h"))
    cfg_mod.validar_config(_config(RECEPCION_USER="recep", RECEPCION_PASSWORD_HASH="h"))


def test_recepcion_no_puede_llamarse_igual_que_el_administrador():
    with pytest.raises(cfg_mod.ErrorDeConfiguracion, match="distinto"):
        cfg_mod.validar_config(_config(RECEPCION_USER="admin", RECEPCION_PASSWORD_HASH="h"))


def test_sin_usuario_de_recepcion_configurado_nadie_entra_como_recepcion(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "x", "ADMIN_USER": "admin",
                      "ADMIN_PASSWORD_HASH": generate_password_hash("clave-larga-123", method="pbkdf2:sha256:1000"),
                      "RECEPCION_USER": None, "RECEPCION_PASSWORD_HASH": None,
                      "DATABASE": str(tmp_path / "a.db"), "UPLOAD_DIR": str(tmp_path / "f")})
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = "t"
    r = c.post("/login", data={"usuario": "recepcion", "clave": CLAVE_REC, "csrf_token": "t"})
    assert r.status_code == 200 and "incorrectos" in r.get_data(as_text=True)
