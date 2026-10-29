import csv
import io
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app, models, timeutils  # noqa: E402
from app import db as dbm  # noqa: E402
from app.routes import auth as auth_routes  # noqa: E402
from app.services import memberships  # noqa: E402

USUARIO = "admin"
CLAVE = "clave-de-prueba-123"
USUARIO_REC = "recepcion"
CLAVE_REC = "clave-recepcion-123"
CLAVE_KIOSCO = "clave-kiosco-123"
HOY = date(2026, 10, 25)  # fecha fija para los tests de lógica pura


@pytest.fixture
def app(tmp_path):
    auth_routes._INTENTOS.clear()
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "clave-de-test",
        "ADMIN_USER": USUARIO,
        "ADMIN_PASSWORD_HASH": generate_password_hash(CLAVE, method="pbkdf2:sha256:1000"),  # rápido para tests
        "RECEPCION_USER": USUARIO_REC,
        "RECEPCION_PASSWORD_HASH": generate_password_hash(CLAVE_REC, method="pbkdf2:sha256:1000"),
        "KIOSCO_CLAVE_HASH": generate_password_hash(CLAVE_KIOSCO, method="pbkdf2:sha256:1000"),
        "DATABASE": str(tmp_path / "test.db"),
        "UPLOAD_DIR": str(tmp_path / "fotos"),
        "IMPORT_DIR": str(tmp_path / "importaciones"),
    })


@pytest.fixture
def db(app):
    conn = dbm.connect(app.config["DATABASE"])
    yield conn
    conn.close()


class Navegador:
    """Cliente de Flask que se encarga del token CSRF en cada POST."""

    def __init__(self, client):
        self.client = client

    def get(self, ruta, **kw):
        return self.client.get(ruta, **kw)

    def post(self, ruta, datos=None, **kw):
        with self.client.session_transaction() as sesion:
            token = sesion.setdefault("csrf", "token-de-prueba")
        cuerpo = dict(datos or {})
        cuerpo["csrf_token"] = token
        return self.client.post(ruta, data=cuerpo, **kw)

    def iniciar_sesion(self, usuario=USUARIO, clave=CLAVE):
        return self.post("/login", {"usuario": usuario, "clave": clave})


@pytest.fixture
def anonimo(app):
    return Navegador(app.test_client())


@pytest.fixture
def nav(anonimo):
    """Navegador con sesión de administrador."""
    anonimo.iniciar_sesion()
    return anonimo


@pytest.fixture
def nav_recepcion(app):
    """Navegador con sesión de recepción (otra instancia: no comparte cookies con `nav`)."""
    n = Navegador(app.test_client())
    n.iniciar_sesion(USUARIO_REC, CLAVE_REC)
    return n


@pytest.fixture
def plan(db):
    """Plan mensual de 30 días a $ 25.000, clases ilimitadas."""
    with db:
        return models.crear_plan(db, dict(nombre="Mensual", precio_centavos=2500000,
                                          duracion_dias=30, clases_por_semana=None))


@pytest.fixture
def crear_socio(db):
    contador = {"n": 0}

    def _crear(nombre="Ana Paz", dni=None, estado="activo", telefono="11 5555-1234", email=None):
        contador["n"] += 1
        dni = dni or str(30000000 + contador["n"])
        with db:
            return models.crear_socio(db, dict(nombre=nombre, dni=dni, telefono=telefono, email=email,
                                               fecha_alta=HOY.isoformat(), estado=estado, foto=None, notas=None))
    return _crear


@pytest.fixture
def socio_con_plan(db, plan, crear_socio):
    """Devuelve una función que crea un socio con plan que vence en `dias_hasta_vencer` días respecto de `hoy`."""
    def _crear(dias_hasta_vencer, hoy=HOY, **kw):
        socio_id = crear_socio(**kw)
        inicio = hoy + timedelta(days=dias_hasta_vencer - 30)
        memberships.asignar_plan(db, socio_id, plan, inicio)
        return socio_id
    return _crear


def leer_csv(respuesta):
    texto = respuesta.get_data().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(texto), delimiter=";"))


def hoy_real():
    return timeutils.hoy()
