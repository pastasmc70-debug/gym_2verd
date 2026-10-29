"""Acceso del administrador y protección de formularios."""
import pytest


@pytest.mark.parametrize("ruta", ["/", "/socios", "/socios/nuevo", "/planes/", "/pagos/", "/asistencia/",
                                  "/alertas/", "/exportar/", "/exportar/socios.csv"])
def test_sin_sesion_todo_redirige_al_login(anonimo, ruta):
    r = anonimo.get(ruta)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_login_correcto(anonimo):
    r = anonimo.iniciar_sesion()
    assert r.status_code == 302
    assert anonimo.get("/").status_code == 200


def test_login_con_clave_incorrecta(anonimo):
    html = anonimo.iniciar_sesion(clave="otra-clave").get_data(as_text=True)
    assert "Usuario o clave incorrectos" in html
    assert anonimo.get("/socios").status_code == 302


def test_login_con_usuario_incorrecto(anonimo):
    assert "Usuario o clave incorrectos" in anonimo.iniciar_sesion(usuario="otro").get_data(as_text=True)


def test_la_clave_no_esta_en_texto_plano(app):
    from conftest import CLAVE
    assert CLAVE not in app.config["ADMIN_PASSWORD_HASH"]


def test_post_sin_token_csrf_es_rechazado(nav, db, plan):
    r = nav.client.post(f"/planes/{plan}/eliminar", data={})
    assert r.status_code == 400
    assert db.execute("SELECT COUNT(*) FROM planes").fetchone()[0] == 1


def test_redireccion_despues_del_login_no_sale_del_sitio(anonimo):
    with anonimo.client.session_transaction() as s:
        s["csrf"] = "t"
    r = anonimo.client.post("/login?next=https://malo.example", data={"usuario": "admin", "clave": "clave-de-prueba-123", "csrf_token": "t"})
    assert r.status_code == 302 and "malo.example" not in r.headers["Location"]


def test_vuelve_a_la_pagina_que_se_pidio(anonimo):
    assert "next=/socios" in anonimo.get("/socios").headers["Location"]
    with anonimo.client.session_transaction() as s:
        s["csrf"] = "t"
    r = anonimo.client.post("/login?next=/socios", data={"usuario": "admin", "clave": "clave-de-prueba-123", "csrf_token": "t"})
    assert r.headers["Location"].endswith("/socios")


def test_demasiados_intentos_fallidos_bloquean_el_login(anonimo):
    for _ in range(5):
        anonimo.iniciar_sesion(clave="mala")
    r = anonimo.iniciar_sesion()          # incluso con la clave correcta
    assert r.status_code == 429


def test_cerrar_sesion(nav):
    nav.post("/logout")
    assert nav.get("/socios").status_code == 302


def test_variables_de_entorno_obligatorias(tmp_path):
    from app import create_app
    from app.config import ErrorDeConfiguracion
    with pytest.raises(ErrorDeConfiguracion, match="GYM_ADMIN_PASSWORD_HASH"):
        create_app({"SECRET_KEY": "x", "ADMIN_USER": "admin", "ADMIN_PASSWORD_HASH": None,
                    "DATABASE": str(tmp_path / "x.db"), "UPLOAD_DIR": str(tmp_path / "f")})
