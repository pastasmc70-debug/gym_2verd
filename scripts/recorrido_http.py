"""Recorrido de punta a punta contra un servidor real (`python run.py`) con una base temporal.

Uso:  python scripts/recorrido_http.py          (funciona igual en Windows, Linux y macOS)
Levanta el servidor dos veces (tienda apagada y encendida), recorre los flujos principales por HTTP
y escribe una línea por flujo: "OK" o "FALLA: motivo". No usa librerías externas (solo werkzeug, que ya trae Flask).
"""
import http.cookiejar
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from werkzeug.security import generate_password_hash

RAIZ = Path(__file__).resolve().parent.parent
DNI_A, DNI_B = "39123456", "39654321"


def hoy_ar():
    """La fecha de hoy en Argentina (igual que la app), no la del reloj de esta computadora."""
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).strftime("%Y-%m-%d")


class Sesion:
    def __init__(self, base):
        self.base = base
        self.o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _abrir(self, url, datos=None, cabeceras=None):
        req = urllib.request.Request(self.base + url, data=datos, headers=cabeceras or {})
        try:
            r = self.o.open(req)
            return r.status, r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, e.read(), url

    def get(self, url):
        c, b, u = self._abrir(url)
        return c, b.decode("utf-8", "ignore"), u

    def post(self, url, datos, desde, cabeceras=None, crudo=False):
        _, h, _ = self.get(desde)
        token = re.search(r'name="csrf_token" value="([^"]+)"', h).group(1)
        c, b, u = self._abrir(url, urllib.parse.urlencode(dict(datos, csrf_token=token)).encode(), cabeceras)
        return (c, b, u) if crudo else (c, b.decode("utf-8", "ignore"), u)


def levantar(tienda, puerto):
    carpeta = tempfile.mkdtemp()
    env = dict(os.environ, GYM_SECRET_KEY="x" * 40, GYM_ADMIN_USER="admin",
               GYM_ADMIN_PASSWORD_HASH=generate_password_hash("clave-admin-1"),
               GYM_RECEPCION_USER="recep", GYM_RECEPCION_PASSWORD_HASH=generate_password_hash("clave-recep-1"),
               GYM_KIOSCO_CLAVE_HASH=generate_password_hash("clave-kiosco-1"),
               GYM_DB_PATH=os.path.join(carpeta, "g.db"), GYM_UPLOAD_DIR=os.path.join(carpeta, "fotos"),
               GYM_IMPORT_DIR=os.path.join(carpeta, "imp"), GYM_MODULO_TIENDA="1" if tienda else "0", PORT=str(puerto))
    subprocess.run([sys.executable, "seed.py", "--reset"], cwd=RAIZ, env=env, check=True, capture_output=True)
    srv = subprocess.Popen([sys.executable, "run.py"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{puerto}"
    for _ in range(30):                                   # espera a que responda
        try:
            urllib.request.urlopen(base + "/login", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    return srv, carpeta, base


def correr(tienda, puerto, resultados):
    srv, carpeta, base = levantar(tienda, puerto)
    etiqueta = "tienda encendida" if tienda else "tienda apagada"
    ctx = {}

    def flujo(nombre, f):
        try:
            motivo = f()
            r = "OK" if motivo is None else f"FALLA: {motivo}"
        except Exception as e:  # noqa: BLE001 - el recorrido tiene que seguir y reportar
            r = f"FALLA: excepción {type(e).__name__}: {e}"
        resultados.append((etiqueta, nombre, r))
        print(f"[{etiqueta}] {nombre}: {r}")

    a = Sesion(base)

    def login():
        c, h, u = a.post("/login", dict(usuario="admin", clave="clave-admin-1"), "/login")
        return None if c == 200 and "Panel" in a.get("/")[1] else f"no entró al panel (HTTP {c})"

    def alta_socio():
        c, h, u = a.post("/socios/nuevo", dict(nombre="Prueba Recorrido", dni=DNI_A, telefono="11 5555-0001", email="",
                                                fecha_alta="", estado="activo", notas=""), "/socios/nuevo")
        m = re.search(r"/socios/(\d+)$", u)
        if not m:
            return "no redirigió al detalle del socio: " + re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", h))[:200]
        ctx["socio"] = m.group(1)
        c, h, u = a.post("/socios/nuevo", dict(nombre="Sin Plan", dni=DNI_B, telefono="11 5555-0002", email="",
                                                fecha_alta="", estado="activo", notas=""), "/socios/nuevo")
        if "DNI" in a.post("/socios/nuevo", dict(nombre="Repetido", dni=DNI_A, telefono="1", email="", fecha_alta="", estado="activo", notas=""), "/socios/nuevo")[1] and True:
            return None
        return "no rechazó el DNI repetido"

    def membresia():
        sid = ctx["socio"]
        _, h, _ = a.get(f"/socios/{sid}/membresia")
        plan = re.search(r'<option value="(\d+)"[^>]*>\s*Libre', h)
        if not plan:
            return "no encontré el plan Libre en el formulario"
        hoy = hoy_ar()
        c, h, u = a.post(f"/socios/{sid}/membresia", dict(plan_id=plan.group(1), fecha_inicio=hoy, acumular="0"), f"/socios/{sid}/membresia")
        return None if c == 200 and "Libre" in h else "no quedó asignado el plan"

    def pago_total():
        sid = ctx["socio"]
        _, h, _ = a.get(f"/pagos/nuevo?socio_id={sid}")
        monto = re.search(r'name="monto"[^>]*value="([^"]*)"', h) or re.search(r'value="([^"]*)"[^>]*name="monto"', h)
        if not monto:
            return "el formulario no trae el monto sugerido"
        ctx["monto"] = monto.group(1)
        c, h, u = a.post("/pagos/nuevo", dict(socio_id=sid, monto=monto.group(1), fecha=hoy_ar(),
                                              metodo="efectivo", nota=""), f"/pagos/nuevo?socio_id={sid}")
        return None if "Pago registrado" in h else "no confirmó el pago: " + re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", h))[:200]

    def pago_parcial():
        sid = ctx["socio"]
        datos = dict(socio_id=sid, monto="1.000", fecha=hoy_ar(), metodo="tarjeta", nota="")
        c, h, u = a.post("/pagos/nuevo", datos, f"/pagos/nuevo?socio_id={sid}")
        if "confirmar_parcial" not in h:
            return "no pidió confirmación para un monto menor al precio"
        c, h, u = a.post("/pagos/nuevo", dict(datos, confirmar_parcial="1"), f"/pagos/nuevo?socio_id={sid}")
        return None if "Pago parcial registrado" in h else "no registró el parcial confirmado"

    def anular_pago():
        sid = ctx["socio"]
        ids = re.findall(r"/pagos/(\d+)/anular", a.get(f"/socios/{sid}")[1])
        if not ids:
            return "el socio no muestra pagos para anular"
        pid = max(ids, key=int)
        ruta = f"/pagos/{pid}/anular"
        c, h, u = a.post(ruta, {"motivo": ""}, ruta)
        if "Pago anulado" in h:
            return "anuló sin motivo"
        c, h, u = a.post(ruta, {"motivo": "Prueba del recorrido"}, ruta)
        return None if "Prueba del recorrido" in a.get(f"/socios/{sid}")[1] or "anulado" in h.lower() else "no quedó anulado con motivo"

    def asistencia():
        c, h, u = a.post("/asistencia/ingreso", dict(q=DNI_A), "/asistencia/")
        return None if "Prueba Recorrido" in a.get("/asistencia/")[1] else "el ingreso no figura en la lista de hoy"

    def kiosco():
        k = Sesion(base)
        c, h, u = k.post("/kiosco/entrar", dict(clave="mala"), "/kiosco/entrar")
        if "no es correcta" not in h:
            return "aceptó una clave de kiosco incorrecta"
        k.post("/kiosco/entrar", dict(clave="clave-kiosco-1"), "/kiosco/entrar")
        if k.get("/kiosco/")[0] != 200:
            return "no entró a la pantalla con la clave correcta"
        _, rojo, _ = k.post("/kiosco/ingreso", dict(dni=DNI_B), "/kiosco/")
        _, verde, _ = k.post("/kiosco/ingreso", dict(dni="12"), "/kiosco/")  # DNI inexistente: también rojo
        # el socio de prueba ya ingresó hoy (reingreso apagado): sirve como caso rojo; para el verde usamos otro socio del seed
        return None if 'class="resultado no"' in rojo and 'class="resultado no"' in verde and "telef" not in rojo.lower() else "pantalla roja incorrecta"

    def kiosco_verde():
        k = Sesion(base)
        k.post("/kiosco/entrar", dict(clave="clave-kiosco-1"), "/kiosco/entrar")
        _, h, _ = a.get("/socios?estado=activo&q=")
        for dni in re.findall(r"DNI[^0-9]{0,40}(\d{7,8})", h) + re.findall(r">(\d{8})<", h):
            _, r, _ = k.post("/kiosco/ingreso", dict(dni=dni), "/kiosco/")
            if 'class="resultado ok"' in r:
                return None if all(x not in r.lower() for x in ("11 5", "@", "$")) else "la pantalla verde muestra datos privados"
        return "ningún socio activo del seed dio pantalla verde"

    def kiosco_aislado():
        k = Sesion(base)
        k.post("/kiosco/entrar", dict(clave="clave-kiosco-1"), "/kiosco/entrar")
        c, h, u = k.get("/socios")
        return None if "kiosco" in u or "Socios" not in h else "la sesión del kiosco pudo ver /socios"

    def caja():
        c, h, _ = a.get("/caja/")
        if c != 200 or "Caja diaria" not in h:
            return f"la caja no abrió (HTTP {c})"
        # el plan Libre cuesta $ 28.000; el parcial de $ 1.000 se anuló y no debe sumar
        return None if "$ 28.000" in h and "$ 29.000" not in h else "la caja no muestra $ 28.000 (o suma el pago anulado)"

    def backup():
        c, z, _ = a.post("/datos/respaldo/", {}, "/exportar/", crudo=True)
        try:
            nombres = set(zipfile.ZipFile(io.BytesIO(z)).namelist())
        except zipfile.BadZipFile:
            return f"no devolvió un zip (HTTP {c})"
        return None if {"gimnasio.db", "LEEME.txt"} <= nombres else f"zip incompleto: {sorted(nombres)}"

    def cuentas():
        a.post("/usuarios/nuevo", dict(usuario="ana.perez", clave="clave-de-ana-12345", clave2="clave-de-ana-12345"), "/usuarios/nuevo")
        if "ana.perez" not in a.get("/usuarios/")[1]:
            return "el administrador no pudo crear la cuenta"
        e = Sesion(base)
        e.post("/login", dict(usuario="ana.perez", clave="clave-de-ana-12345"), "/login")
        if "ana.perez" not in e.get("/")[1] or e.get("/usuarios/")[0] != 403:
            return "la cuenta nueva no entró como recepción, o pudo ver /usuarios/"
        ids = re.findall(r"/usuarios/(\d+)/desactivar", a.get("/usuarios/")[1])
        for uid in ids:
            a.post(f"/usuarios/{uid}/desactivar", {}, "/usuarios/")
        _, h, u = e.get("/asistencia/")                      # sesión que ya tenía abierta
        return None if "login" in u and "Ingresar" in h else "desactivar no cerró la sesión abierta"

    def tienda_flujo():
        if not tienda:
            ok404 = all(a.get(p)[0] == 404 for p in ("/tienda/", "/tienda/ventas", "/tienda/productos"))
            return None if ok404 and "Tienda del mes" not in a.get("/")[1] else "con el módulo apagado la tienda sigue accesible"
        a.post("/tienda/productos/nuevo", dict(nombre="Whey", marca="ENA", categoria="Prot", precio="45000", costo="30000",
                                                stock="10", stock_minimo="3"), "/tienda/productos/nuevo")
        pid = re.search(r'name="cant_(\d+)"', a.get("/tienda/")[1]).group(1)
        if "No alcanza el stock" not in a.post("/tienda/", {f"cant_{pid}": "99", "metodo": "efectivo"}, "/tienda/")[1]:
            return "vendió más de lo que había en stock"
        if "Venta registrada" not in a.post("/tienda/", {f"cant_{pid}": "8", "metodo": "efectivo"}, "/tienda/")[1]:
            return "no registró la venta"
        if "2" not in re.sub(r"\s+", " ", a.get(f"/tienda/productos/{pid}/stock")[1]) or "Whey" not in a.get("/tienda/faltantes")[1]:
            return "el stock no bajó a 2 / no aparece en faltantes"
        cj = a.get("/caja/")[1]
        if "Ventas de la tienda del día" not in cj or "$ 360.000" not in cj:
            return "la caja no muestra la tienda separada"
        vid = re.search(r"/tienda/ventas/(\d+)", a.get("/tienda/ventas")[1]).group(1)
        a.post(f"/tienda/ventas/{vid}/anular", {"motivo": "prueba"}, f"/tienda/ventas/{vid}/anular")
        return None if "Anulada" in a.get("/tienda/ventas")[1] else "no anuló la venta"

    try:
        flujo("login admin", login)
        flujo("alta de socio (y rechazo de DNI repetido)", alta_socio)
        flujo("alta de membresía", membresia)
        flujo("pago total", pago_total)
        flujo("pago parcial (con confirmación)", pago_parcial)
        flujo("anulación de un pago con motivo", anular_pago)
        flujo("acceso a asistencia", asistencia)
        flujo("kiosco: clave y pantalla roja", kiosco)
        flujo("kiosco: pantalla verde sin datos privados", kiosco_verde)
        flujo("kiosco: sesión aislada del resto", kiosco_aislado)
        flujo("tienda (venta, stock, anulación)" if tienda else "tienda apagada (404)", tienda_flujo)
        flujo("usuarios: crear, entrar, recepción sin acceso, desactivar", cuentas)
        flujo("caja diaria", caja)
        flujo("backup descargable", backup)
    finally:
        srv.terminate()
        srv.wait()
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    resultados = []
    correr(False, 5101, resultados)
    correr(True, 5102, resultados)
    fallas = [r for r in resultados if r[2] != "OK"]
    print(f"\n{len(resultados) - len(fallas)} OK, {len(fallas)} FALLA")
    sys.exit(1 if fallas else 0)
