"""Modo kiosco: ingreso por DNI desde la recepción, con privacidad, clave aparte y límite de intentos."""
import json
import re
from datetime import timedelta

import pytest

import crear_hash
from app import models
from app.services import kiosco, memberships, payments
from app.services.attendance import ReglasIngreso
from conftest import CLAVE_KIOSCO, HOY, Navegador, hoy_real

PRECIO = 2500000
REGLAS = ReglasIngreso()
CLAVES_PERMITIDAS = {"ok", "mensaje", "nombre", "foto", "estado", "dias"}


def _socio_pago(db, plan, crear_socio, dias_hasta_vencer=20, hoy=HOY, pagar=True, **kw):
    socio_id = crear_socio(**kw)
    memberships.asignar_plan(db, socio_id, plan, hoy + timedelta(days=dias_hasta_vencer - 30))
    if pagar:
        payments.registrar_pago(db, socio_id, PRECIO, hoy, "efectivo")
    return socio_id


# --------------------------------------------------------------------------- servicio
def test_ingreso_aceptado_muestra_nombre_estado_y_dias(db, plan, crear_socio):
    _socio_pago(db, plan, crear_socio, 20, nombre="Lucía Gómez", dni="30111222")
    r = kiosco.resolver_ingreso(db, "30111222", REGLAS, hoy=HOY)
    assert r["ok"] is True and r["nombre"] == "Lucía Gómez"
    assert r["estado"] == "Vigente" and r["dias"] == "Te quedan 20 días"
    assert db.execute("SELECT registrado_por FROM asistencias").fetchone()[0] == "kiosco"


@pytest.mark.parametrize("dias,estado,texto", [(3, "Por vencer", "Te quedan 3 días"), (1, "Por vencer", "Te queda 1 día"),
                                               (0, "Por vencer", "Tu cuota vence hoy")])
def test_por_vencer(db, plan, crear_socio, dias, estado, texto):
    _socio_pago(db, plan, crear_socio, dias, dni="30111222")
    r = kiosco.resolver_ingreso(db, "30111222", REGLAS, hoy=HOY)
    assert r["ok"] and r["estado"] == estado and r["dias"] == texto


def test_cuota_vencida_se_rechaza_en_rojo(db, plan, crear_socio):
    _socio_pago(db, plan, crear_socio, -5, pagar=False, nombre="Pablo Vencido", dni="30111222")
    r = kiosco.resolver_ingreso(db, "30111222", REGLAS, hoy=HOY)
    assert r["ok"] is False and r["nombre"] == "Pablo Vencido"
    assert r["estado"] == "Vencida" and r["dias"] == "Venció hace 5 días" and "vencida" in r["mensaje"]
    assert db.execute("SELECT COUNT(*) FROM asistencias").fetchone()[0] == 0


def test_dni_inexistente_o_invalido_no_revela_nada(db):
    for texto in ("30111222", "123", "123456789", "abc", "", "3011 1222"):
        r = kiosco.resolver_ingreso(db, texto, REGLAS, hoy=HOY)
        assert r["ok"] is False and r["nombre"] == "" and r["foto"] is None


def test_el_rechazo_por_falta_de_pago_no_menciona_pagos(db, plan, crear_socio):
    _socio_pago(db, plan, crear_socio, 20, pagar=False, dni="30111222")
    r = kiosco.resolver_ingreso(db, "30111222", REGLAS, hoy=HOY)
    assert r["ok"] is False
    assert not re.search(r"pag|deud|saldo|cuota registrada", r["mensaje"] + r["estado"] + r["dias"], re.I)


@pytest.mark.parametrize("estado,etiqueta", [("pausado", "Pausado"), ("baja", "De baja")])
def test_pausado_y_baja(db, plan, crear_socio, estado, etiqueta):
    socio_id = _socio_pago(db, plan, crear_socio, 20, dni="30111222")
    with db:
        db.execute("UPDATE socios SET estado = ? WHERE id = ?", (estado, socio_id))
    r = kiosco.resolver_ingreso(db, "30111222", REGLAS, hoy=HOY)
    assert r["ok"] is False and r["estado"] == etiqueta and r["dias"] == ""


def test_segundo_ingreso_del_dia_y_limite_de_clases(db, crear_socio):
    with db:
        uno = models.crear_plan(db, dict(nombre="Una", precio_centavos=PRECIO, duracion_dias=30, clases_por_semana=1))
    socio_id = crear_socio(dni="30111222")
    memberships.asignar_plan(db, socio_id, uno, HOY - timedelta(days=10))
    payments.registrar_pago(db, socio_id, PRECIO, HOY, "efectivo")
    assert kiosco.resolver_ingreso(db, "30111222", REGLAS, hoy=HOY)["ok"] is True
    assert "Ya registraste tu ingreso hoy" in kiosco.resolver_ingreso(db, "30111222", REGLAS, hoy=HOY)["mensaje"]
    assert "clases de esta semana" in kiosco.resolver_ingreso(db, "30111222", REGLAS, hoy=HOY - timedelta(days=1))["mensaje"]   # sábado: misma semana (lun-dom)


def test_la_respuesta_tiene_solo_los_campos_permitidos(db, plan, crear_socio):
    _socio_pago(db, plan, crear_socio, 20, dni="30111222", telefono="11 5555-1234", email="x@y.com")
    for texto in ("30111222", "30111222", "99999999"):
        assert set(kiosco.resolver_ingreso(db, texto, REGLAS, hoy=HOY)) == CLAVES_PERMITIDAS


# -------------------------------------------------------------------------- limitador
def test_el_limitador_corta_despues_del_maximo_y_se_libera_con_el_tiempo():
    reloj = {"t": 0.0}
    lim = kiosco.Limitador(3, 60, reloj=lambda: reloj["t"])
    assert [lim.intentar("a") for _ in range(4)] == [True, True, True, False]
    assert lim.intentar("otra-ip") is True                 # cada IP tiene su propio contador
    reloj["t"] = 59.0
    assert lim.intentar("a") is False
    reloj["t"] = 61.0
    assert lim.intentar("a") is True


# ---------------------------------------------------------------------------- acceso
@pytest.fixture
def kiosco_nav(app):
    n = Navegador(app.test_client())
    r = n.client.get("/kiosco/entrar")
    assert r.status_code == 200
    r = n.post("/kiosco/entrar", {"clave": CLAVE_KIOSCO})
    assert r.status_code == 302 and r.headers["Location"].endswith("/kiosco/")
    return n


def test_sin_clave_configurada_el_kiosco_avisa(app):
    app.config["KIOSCO_CLAVE_HASH"] = None
    r = app.test_client().get("/kiosco/entrar")
    assert r.status_code == 503 and "GYM_KIOSCO_CLAVE_HASH" in r.get_data(as_text=True)


def test_clave_incorrecta(anonimo):
    r = anonimo.post("/kiosco/entrar", {"clave": "mala"})
    assert r.status_code == 200 and "no es correcta" in r.get_data(as_text=True)
    assert anonimo.get("/kiosco/").status_code == 302


def test_la_clave_del_kiosco_es_distinta_de_la_del_administrador(anonimo):
    from conftest import CLAVE
    assert "no es correcta" in anonimo.post("/kiosco/entrar", {"clave": CLAVE}).get_data(as_text=True)


def test_demasiados_intentos_de_clave_se_bloquean(anonimo):
    from app.routes import kiosco as ruta
    ruta._FALLOS_CLAVE.clear()
    for _ in range(5):
        anonimo.post("/kiosco/entrar", {"clave": "mala"})
    r = anonimo.post("/kiosco/entrar", {"clave": CLAVE_KIOSCO})        # ni con la clave buena
    assert r.status_code == 429
    ruta._FALLOS_CLAVE.clear()


def test_sin_sesion_la_pantalla_pide_la_clave(anonimo):
    r = anonimo.get("/kiosco/")
    assert r.status_code == 302 and "/kiosco/entrar" in r.headers["Location"]


@pytest.mark.parametrize("ruta", ["/", "/socios", "/socios/1", "/pagos/", "/pagos/nuevo", "/asistencia/", "/alertas/",
                                  "/caja/", "/planes/", "/exportar/", "/exportar/socios.csv", "/datos/importar/",
                                  "/fotos/abc.jpg"])
def test_el_kiosco_no_accede_a_nada_mas(kiosco_nav, ruta):
    r = kiosco_nav.get(ruta)
    assert r.status_code == 302 and r.headers["Location"].endswith("/kiosco/")


def test_el_kiosco_no_puede_hacer_acciones_del_sistema(kiosco_nav, db, plan, crear_socio):
    socio_id = crear_socio()
    r = kiosco_nav.post("/socios/nuevo", {"nombre": "x", "dni": "40111222", "telefono": "11 5555-0000"})
    assert r.status_code == 302 and db.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 1
    assert kiosco_nav.post("/datos/respaldo/").status_code == 302
    assert kiosco_nav.post("/logout").status_code == 302


def test_el_personal_logueado_tampoco_usa_el_kiosco_sin_la_clave(nav):
    r = nav.get("/kiosco/")
    assert r.status_code == 302 and "/kiosco/entrar" in r.headers["Location"]
    assert nav.post("/kiosco/ingreso", {"dni": "30111222"}).status_code == 302


def test_la_sesion_del_kiosco_vence(app, kiosco_nav):
    import time
    with kiosco_nav.client.session_transaction() as s:
        s["inicio"] = time.time() - (app.config["KIOSCO_SESION_DIAS"] + 1) * 86400
    assert kiosco_nav.get("/kiosco/").status_code == 302


def test_salir_del_kiosco(kiosco_nav):
    kiosco_nav.post("/kiosco/salir")
    assert "/kiosco/entrar" in kiosco_nav.get("/kiosco/").headers["Location"]


# ------------------------------------------------------------------------- pantallas
def test_la_pantalla_tiene_el_campo_con_foco_solo_numeros_y_lo_necesario(kiosco_nav, app):
    html = kiosco_nav.get("/kiosco/").get_data(as_text=True)
    assert 'id="dni"' in html and "autofocus" in html
    assert 'inputmode="numeric"' in html and 'pattern="[0-9]*"' in html and 'maxlength="8"' in html
    assert 'data-sonido="1"' in html
    assert "data-tecla" not in html                                      # teclado en pantalla apagado por defecto
    assert "cdn.jsdelivr" not in html                                    # anda sin internet


def test_el_sonido_y_el_teclado_en_pantalla_se_activan_por_configuracion(kiosco_nav, app):
    app.config["KIOSCO_SONIDO"] = False
    app.config["KIOSCO_TECLADO_PANTALLA"] = True
    html = kiosco_nav.get("/kiosco/").get_data(as_text=True)
    assert 'data-sonido="0"' in html
    assert html.count("data-tecla=") == 12                               # 0-9, borrar y enter


def test_el_javascript_recupera_el_foco_filtra_numeros_y_vuelve_a_los_5_segundos(client_estatico):
    js = client_estatico.get("/static/js/kiosco.js").get_data(as_text=True)
    assert 'addEventListener("blur"' in js and "setInterval(enfocar" in js          # recupera el foco
    assert r"replace(/\D/g" in js                                                    # solo números
    assert "5000" in js and 'campo.value = ""' in js                                 # 5 segundos y campo vacío
    assert "requestFullscreen" in js and "frequency" in js                           # pantalla completa y sonido


@pytest.fixture
def client_estatico(app):
    return app.test_client()


def _post_json(n, dni):
    return n.post("/kiosco/ingreso", {"dni": dni}, headers={"X-Requested-With": "kiosco", "Accept": "application/json"})


def test_ingreso_por_json(kiosco_nav, db, plan, crear_socio):
    _socio_pago(db, plan, crear_socio, 20, hoy=hoy_real(), nombre="Lucía Gómez", dni="30111222")
    r = _post_json(kiosco_nav, "30111222")
    data = r.get_json()
    assert r.status_code == 200 and data["ok"] is True and data["nombre"] == "Lucía Gómez"
    assert data["estado"] == "Vigente" and data["dias"] == "Te quedan 20 días"
    again = _post_json(kiosco_nav, "30111222").get_json()
    assert again["ok"] is False and "Ya registraste" in again["mensaje"]


def test_ingreso_sin_javascript_devuelve_la_pantalla_verde_o_roja_que_vuelve_sola(kiosco_nav, db, plan, crear_socio):
    _socio_pago(db, plan, crear_socio, 20, hoy=hoy_real(), nombre="Lucía Gómez", dni="30111222")
    verde = kiosco_nav.post("/kiosco/ingreso", {"dni": "30111222"}).get_data(as_text=True)
    assert 'class="resultado ok"' in verde and "Lucía Gómez" in verde and 'http-equiv="refresh" content="5;' in verde
    rojo = kiosco_nav.post("/kiosco/ingreso", {"dni": "99999999"}).get_data(as_text=True)
    assert 'class="resultado no"' in rojo and "No encontramos ese DNI" in rojo


def test_privacidad_la_respuesta_no_trae_datos_personales_ni_de_pagos(kiosco_nav, db, plan, crear_socio):
    socio_id = _socio_pago(db, plan, crear_socio, 20, hoy=hoy_real(), nombre="Lucía Gómez", dni="30111222",
                           telefono="11 5555-1234", email="lucia.secreta@ejemplo.com")
    with db:
        db.execute("UPDATE socios SET notas = 'Nota privada de salud' WHERE id = ?", (socio_id,))
    prohibido = ["5555-1234", "lucia.secreta", "Nota privada", "25.000", "25000", "Mensual", "30111222", "efectivo", "saldo", "deuda"]
    for cuerpo in (_post_json(kiosco_nav, "30111222").get_data(as_text=True),
                   kiosco_nav.post("/kiosco/ingreso", {"dni": "30111222"}).get_data(as_text=True),   # rechazo (reingreso)
                   kiosco_nav.get("/kiosco/").get_data(as_text=True)):
        for dato in prohibido:
            assert dato not in cuerpo, f"el kiosco no debe mostrar «{dato}»"


def test_privacidad_tambien_en_el_rechazo_por_deuda_o_vencida(kiosco_nav, db, plan, crear_socio):
    _socio_pago(db, plan, crear_socio, -10, hoy=hoy_real(), pagar=False, nombre="Pablo", dni="30111222",
                telefono="11 5555-1234", email="pablo.secreto@ejemplo.com")
    cuerpo = _post_json(kiosco_nav, "30111222").get_data(as_text=True)
    assert "Pablo" in cuerpo
    for dato in ("5555-1234", "pablo.secreto", "25.000", "Mensual"):
        assert dato not in cuerpo
    assert set(json.loads(cuerpo)) == CLAVES_PERMITIDAS | {"foto_url"}


def test_limite_de_intentos_por_minuto_aunque_el_dni_sea_valido(app, kiosco_nav, db, plan, crear_socio):
    app.config["KIOSCO_MAX_INTENTOS_POR_MINUTO"] = 3
    app.extensions.pop("kiosco_limitador", None)
    _socio_pago(db, plan, crear_socio, 20, hoy=hoy_real(), dni="30111222")
    respuestas = [_post_json(kiosco_nav, d) for d in ("1", "2", "3")]
    assert all(r.status_code == 200 for r in respuestas)
    r = _post_json(kiosco_nav, "30111222")                                # DNI real, pero ya se pasó del límite
    assert r.status_code == 429 and "Demasiados intentos" in r.get_json()["mensaje"]
    assert r.get_json()["nombre"] == "" and db.execute("SELECT COUNT(*) FROM asistencias").fetchone()[0] == 0


def test_ingreso_sin_token_csrf_se_rechaza(kiosco_nav):
    assert kiosco_nav.client.post("/kiosco/ingreso", data={"dni": "30111222"}).status_code == 400


def test_la_foto_se_ve_en_la_respuesta_y_solo_se_sirven_fotos_de_socios(kiosco_nav, db, app, plan, crear_socio):
    from pathlib import Path
    socio_id = _socio_pago(db, plan, crear_socio, 20, hoy=hoy_real(), nombre="Con Foto", dni="30111222")
    carpeta = Path(app.config["UPLOAD_DIR"]); carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "abc123.jpg").write_bytes(b"\xff\xd8\xff-foto")
    (carpeta / "suelto.jpg").write_bytes(b"\xff\xd8\xff-otra")
    with db:
        db.execute("UPDATE socios SET foto = 'abc123.jpg' WHERE id = ?", (socio_id,))

    data = _post_json(kiosco_nav, "30111222").get_json()
    assert data["foto_url"] == "/kiosco/foto/abc123.jpg"
    assert kiosco_nav.get(data["foto_url"]).get_data() == b"\xff\xd8\xff-foto"
    assert kiosco_nav.get("/kiosco/foto/suelto.jpg").status_code == 404        # no es la foto de ningún socio
    assert kiosco_nav.get("/kiosco/foto/..%2Ffotos%2Fsuelto.jpg").status_code == 404


def test_la_foto_no_se_sirve_sin_sesion(anonimo):
    assert anonimo.get("/kiosco/foto/abc123.jpg").status_code == 302


# ---------------------------------------------------------------------- crear_hash.py
@pytest.mark.parametrize("quien,variable", [("admin", "GYM_ADMIN_PASSWORD_HASH"), ("recepcion", "GYM_RECEPCION_PASSWORD_HASH"),
                                            ("kiosco", "GYM_KIOSCO_CLAVE_HASH")])
def test_crear_hash_imprime_la_variable_correcta(monkeypatch, capsys, quien, variable):
    monkeypatch.setattr("getpass.getpass", lambda _="": "una-clave-larga-123")
    assert crear_hash.main([quien]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith(f"{variable}='")


def test_crear_hash_rechaza_argumentos_raros(capsys):
    assert crear_hash.main(["otro"]) == 1 and "Uso:" in capsys.readouterr().err
