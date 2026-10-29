import math
import sqlite3

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   send_from_directory, url_for)

from .. import models, timeutils
from ..db import get_db
from ..services import memberships, payments, selector
from ..services.errors import ErrorDeNegocio
from ..services.photos import borrar_foto, guardar_foto
from ..services.validation import validar_socio
from ..services.whatsapp import link_whatsapp

bp = Blueprint("socios", __name__)
POR_PAGINA = 20


@bp.get("/socios")
def lista():
    db, cfg = get_db(), current_app.config
    q = request.args.get("q", "").strip()
    estado = request.args.get("estado", "")
    if estado not in models.ESTADOS_SOCIO:
        estado = ""
    total = models.contar_socios(db, q, estado)
    paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(max(1, request.args.get("pagina", 1, type=int)), paginas)
    hoy = timeutils.hoy()
    socios = [memberships.enriquecer(f, hoy, cfg["DIAS_ALERTA"])
              for f in models.listar_socios(db, q, estado, POR_PAGINA, (pagina - 1) * POR_PAGINA)]
    return render_template("socios/lista.html", socios=socios, q=q, estado=estado,
                           pagina=pagina, paginas=paginas, total=total)


def contexto_selector(destino: str, q: str = "", base_url: str | None = None) -> dict:
    """Datos de la lista de socios para elegir (la usan las pantallas que piden un socio). Sirve sin JavaScript:
    el orden y la página vienen por la URL (`orden`, `pagina`)."""
    cfg = current_app.config
    datos = selector.listar(get_db(), q, request.args.get("orden"), request.args.get("pagina", 1, type=int),
                            timeutils.hoy(), cfg["DIAS_ALERTA"])
    datos["destino"] = destino
    datos["base_url"] = base_url or request.path   # a dónde apuntan los links de orden y de página (sin JavaScript)
    return datos


@bp.get("/socios/selector")
def selector_lista():
    """Fragmento HTML con la lista (lo pide el JavaScript al escribir en el buscador o al pedir más)."""
    destino = request.args.get("destino")
    if destino not in selector.DESTINOS:
        abort(404)
    datos = contexto_selector(destino, request.args.get("q", ""), request.args.get("base_url") or None)
    plantilla = "socios/_selector_mas.html" if request.args.get("mas") else "socios/_selector_lista.html"
    return render_template(plantilla, sel=datos)


@bp.route("/socios/nuevo", methods=["GET", "POST"])
def nuevo():
    db, cfg = get_db(), current_app.config
    errores = {}
    if request.method == "POST":
        datos, errores = validar_socio(db, request.form)
        if not errores:
            try:
                datos["foto"] = guardar_foto(request.files.get("foto"), cfg["UPLOAD_DIR"])
            except ErrorDeNegocio as e:
                errores["foto"] = str(e)
        if not errores:
            try:
                with db:
                    socio_id = models.crear_socio(db, datos)
            except sqlite3.IntegrityError:  # dos personas cargando el mismo DNI a la vez
                borrar_foto(datos.get("foto"), cfg["UPLOAD_DIR"])
                errores["dni"] = "Ya existe un socio con ese DNI."
            else:
                flash("Socio creado. Ahora podés asignarle un plan.", "success")
                return redirect(url_for("socios.detalle", socio_id=socio_id))
        flash("Revisá los campos marcados en rojo.", "danger")
        return render_template("socios/form.html", valores=request.form, errores=errores, socio=None)
    valores = {"fecha_alta": timeutils.hoy().isoformat(), "estado": "activo"}
    return render_template("socios/form.html", valores=valores, errores=errores, socio=None)


@bp.route("/socios/<int:socio_id>/editar", methods=["GET", "POST"])
def editar(socio_id):
    db, cfg = get_db(), current_app.config
    socio = models.obtener_socio(db, socio_id)
    if socio is None:
        abort(404)
    errores = {}
    if request.method == "POST":
        datos, errores = validar_socio(db, request.form, socio_id=socio_id)
        nueva_foto = None
        if not errores:
            try:
                nueva_foto = guardar_foto(request.files.get("foto"), cfg["UPLOAD_DIR"])
            except ErrorDeNegocio as e:
                errores["foto"] = str(e)
        if not errores:
            foto_anterior = socio["foto"]
            if nueva_foto:
                datos["foto"] = nueva_foto
            elif request.form.get("quitar_foto"):
                datos["foto"] = None
            else:
                datos["foto"] = foto_anterior
            try:
                with db:
                    models.actualizar_socio(db, socio_id, datos)
            except sqlite3.IntegrityError:
                borrar_foto(nueva_foto, cfg["UPLOAD_DIR"])
                errores["dni"] = "Ya existe un socio con ese DNI."
            else:
                if datos["foto"] != foto_anterior:
                    borrar_foto(foto_anterior, cfg["UPLOAD_DIR"])
                flash("Cambios guardados.", "success")
                return redirect(url_for("socios.detalle", socio_id=socio_id))
        flash("Revisá los campos marcados en rojo.", "danger")
        return render_template("socios/form.html", valores=request.form, errores=errores, socio=socio)
    return render_template("socios/form.html", valores=dict(socio), errores=errores, socio=socio)


@bp.get("/socios/<int:socio_id>")
def detalle(socio_id):
    db, cfg = get_db(), current_app.config
    fila = models.obtener_socio(db, socio_id)
    if fila is None:
        abort(404)
    socio = memberships.enriquecer(fila, timeutils.hoy(), cfg["DIAS_ALERTA"])
    whatsapp = None
    if socio["estado_membresia"] in (models.VENCIDA, models.POR_VENCER):
        whatsapp = link_whatsapp(socio, cfg["GYM_NOMBRE"])
    actual = models.membresia_actual(db, socio_id)
    estado = payments.reproducir(db, actual["id"]) if actual else None
    saldo = estado.saldo_pendiente_centavos if estado else 0
    saldo_a_favor = estado.saldo_a_favor_centavos if estado else 0
    resultado_pago = None  # tarjeta con el resultado del pago recién registrado (?pago=ID)
    pago_id = request.args.get("pago", type=int)
    if pago_id:
        resultado_pago = payments.resumen_de_pago(db, pago_id)
        if resultado_pago and resultado_pago["pago"]["socio_id"] != socio_id:
            resultado_pago = None
    return render_template(
        "socios/detalle.html", socio=socio, whatsapp=whatsapp, saldo=saldo, saldo_a_favor=saldo_a_favor,
        resultado_pago=resultado_pago,
        membresias=models.historial_membresias(db, socio_id),
        pagos=models.pagos_de_socio(db, socio_id),
        asistencias=models.ultimas_asistencias(db, socio_id),
    )


@bp.get("/fotos/<nombre>")
def foto(nombre):
    """Las fotos se sirven solo a quien inició sesión (el before_request ya lo exige)."""
    return send_from_directory(current_app.config["UPLOAD_DIR"], nombre)
