"""ABM de socios y planes: validaciones."""
import io

from app import models
from app.services.validation import validar_plan, validar_socio

FORM_OK = {"nombre": "Lucía Gómez", "dni": "30.123.456", "telefono": "11 5555-1234", "estado": "activo"}


def test_dni_duplicado_rechazado(db, crear_socio):
    crear_socio(nombre="Ana Paz", dni="30123456")
    _, errores = validar_socio(db, FORM_OK)
    assert "ya existe un socio con ese dni" in errores["dni"].lower()
    assert "Ana Paz" in errores["dni"]


def test_dni_duplicado_se_detecta_aunque_cambie_el_formato(db, crear_socio):
    crear_socio(dni="30123456")
    _, errores = validar_socio(db, dict(FORM_OK, dni="30 123 456"))
    assert "dni" in errores


def test_un_socio_puede_guardar_su_propio_dni_al_editarse(db, crear_socio):
    socio_id = crear_socio(dni="30123456")
    _, errores = validar_socio(db, FORM_OK, socio_id=socio_id)
    assert errores == {}


def test_la_base_tambien_impide_dni_duplicado(db, crear_socio):
    import sqlite3
    import pytest
    crear_socio(dni="30123456")
    with pytest.raises(sqlite3.IntegrityError):
        crear_socio(dni="30123456")


def test_dni_se_guarda_solo_con_numeros(db):
    datos, errores = validar_socio(db, FORM_OK)
    assert errores == {} and datos["dni"] == "30123456"


def test_campos_obligatorios(db):
    _, errores = validar_socio(db, {})
    assert {"nombre", "dni", "telefono"} <= set(errores)


def test_dni_con_largo_invalido(db):
    assert "dni" in validar_socio(db, dict(FORM_OK, dni="123"))[1]
    assert "dni" in validar_socio(db, dict(FORM_OK, dni="123456789"))[1]


def test_email_y_telefono_invalidos(db):
    _, errores = validar_socio(db, dict(FORM_OK, email="no-es-un-mail", telefono="abc"))
    assert "email" in errores and "telefono" in errores


def test_estado_invalido(db):
    assert "estado" in validar_socio(db, dict(FORM_OK, estado="congelado"))[1]


def test_pantalla_rechaza_dni_duplicado_y_no_crea_el_socio(nav, db, crear_socio):
    crear_socio(nombre="Ana Paz", dni="30123456")

    html = nav.post("/socios/nuevo", FORM_OK).get_data(as_text=True)

    assert "Ya existe un socio con ese DNI" in html
    assert db.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 1


def test_pantalla_crea_el_socio(nav, db):
    r = nav.post("/socios/nuevo", FORM_OK)
    assert r.status_code == 302
    socio = models.obtener_socio_por_dni(db, "30123456")
    assert socio["nombre"] == "Lucía Gómez" and socio["estado"] == "activo"


def test_pantalla_no_deja_editar_un_socio_con_el_dni_de_otro(nav, db, crear_socio):
    crear_socio(dni="30123456")
    otro = crear_socio(nombre="Otro Socio", dni="40999888")
    html = nav.post(f"/socios/{otro}/editar", dict(FORM_OK, nombre="Otro Socio")).get_data(as_text=True)
    assert "Ya existe un socio con ese DNI" in html
    assert models.obtener_socio(db, otro)["dni"] == "40999888"


def test_foto_que_no_es_imagen_se_rechaza(nav, db):
    datos = dict(FORM_OK, foto=(io.BytesIO(b"esto no es una imagen"), "foto.jpg"))
    with nav.client.session_transaction() as s:
        datos["csrf_token"] = s.setdefault("csrf", "token-de-prueba")
    html = nav.client.post("/socios/nuevo", data=datos, content_type="multipart/form-data").get_data(as_text=True)
    assert "JPG, PNG o WEBP" in html
    assert db.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 0


def test_foto_valida_se_guarda_y_solo_se_sirve_con_sesion(nav, app, db):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    datos = dict(FORM_OK, foto=(io.BytesIO(png), "yo.png"))
    with nav.client.session_transaction() as s:
        datos["csrf_token"] = s.setdefault("csrf", "token-de-prueba")
    nav.client.post("/socios/nuevo", data=datos, content_type="multipart/form-data")
    nombre = models.obtener_socio_por_dni(db, "30123456")["foto"]
    assert nombre and nombre.endswith(".png")
    assert nav.get(f"/fotos/{nombre}").status_code == 200
    assert app.test_client().get(f"/fotos/{nombre}").status_code == 302   # sin sesión: redirige al login


# ---- planes ------------------------------------------------------------------
PLAN_OK = {"nombre": "Libre", "precio": "28.000", "duracion_dias": "30", "ilimitado": "1"}


def test_plan_valido(db):
    datos, errores = validar_plan(db, PLAN_OK)
    assert errores == {}
    assert datos["precio_centavos"] == 2800000 and datos["clases_por_semana"] is None


def test_plan_con_clases_por_semana(db):
    datos, errores = validar_plan(db, {"nombre": "3x", "precio": "20000", "duracion_dias": "30", "clases_por_semana": "3"})
    assert errores == {} and datos["clases_por_semana"] == 3


def test_plan_rechaza_precio_cero_duracion_invalida_y_sin_clases(db):
    _, errores = validar_plan(db, {"nombre": "X", "precio": "0", "duracion_dias": "0"})
    assert {"precio", "duracion_dias", "clases_por_semana"} <= set(errores)


def test_plan_con_nombre_repetido(db, plan):
    _, errores = validar_plan(db, dict(PLAN_OK, nombre="mensual"))   # sin distinguir mayúsculas
    assert "nombre" in errores


def test_no_se_elimina_un_plan_en_uso(nav, db, plan, crear_socio):
    from datetime import date
    from app.services import memberships
    memberships.asignar_plan(db, crear_socio(), plan, date(2026, 10, 1))
    html = nav.post(f"/planes/{plan}/eliminar", follow_redirects=True).get_data(as_text=True)
    assert "No se puede eliminar" in html
    assert models.obtener_plan(db, plan) is not None


def test_se_elimina_un_plan_sin_uso(nav, db, plan):
    nav.post(f"/planes/{plan}/eliminar")
    assert models.obtener_plan(db, plan) is None
