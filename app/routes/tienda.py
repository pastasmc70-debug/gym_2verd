import sqlite3

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from .. import models, permisos, timeutils
from ..db import get_db
from ..formatting import monto_form
from ..services import tienda
from ..services.errors import ErrorDeNegocio
from . import socios as socios_routes

bp = Blueprint("tienda", __name__, url_prefix="/tienda")


@bp.before_request
def modulo_encendido():
    """Con GYM_MODULO_TIENDA apagado la tienda no existe: ni menú ni pantallas."""
    if not current_app.config["MODULO_TIENDA"]:
        abort(404)


# ------------------------------------------------------------------ ventas
@bp.route("/", methods=["GET", "POST"])
def nueva_venta():
    db = get_db()
    productos = tienda.listar_productos(db, solo_activos=True)
    error, cantidades = None, {}
    metodo, dni = request.form.get("metodo", "efectivo"), request.form.get("socio_dni", "").strip()
    if request.method == "POST":
        items = []
        for p in productos:
            texto = request.form.get(f"cant_{p['id']}", "").strip()
            if texto in ("", "0"):
                continue
            cantidades[p["id"]] = texto
            try:
                items.append((p["id"], int(texto)))
            except ValueError:
                items.append((p["id"], texto))        # el servicio lo rechaza con un mensaje claro
        socio_id = None
        try:
            if dni:
                socio = models.obtener_socio_por_dni(db, dni)
                if socio is None:
                    raise ErrorDeNegocio(f"No encontramos ningún socio con el DNI {dni}. Dejá el campo vacío para una venta de mostrador.", "socio")
                socio_id = socio["id"]
            r = tienda.registrar_venta(db, items, metodo, socio_id=socio_id, usuario=permisos.usuario_actual())
        except ErrorDeNegocio as e:
            error = str(e)
        else:
            flash(f"Venta registrada por {_pesos(r['total_centavos'])}.", "success")
            return redirect(url_for("tienda.nueva_venta"))
    return render_template("tienda/nueva_venta.html", productos=productos, error=error, cantidades=cantidades,
                           metodo=metodo, dni=dni,
                           sel=socios_routes.contexto_selector("venta", "", url_for("tienda.nueva_venta")))


def _pesos(centavos):
    return current_app.jinja_env.filters["pesos"](centavos)


@bp.get("/ventas")
def ventas():
    hoy = timeutils.hoy()
    fecha = timeutils.parse_fecha(request.args.get("fecha")) or hoy
    if fecha > hoy:
        fecha = hoy
    return render_template("tienda/ventas.html", fecha=fecha, hoy=hoy, caja=tienda.caja_del_dia(get_db(), fecha))


@bp.get("/ventas/<int:venta_id>")
def detalle_venta(venta_id):
    db = get_db()
    venta = tienda.obtener_venta(db, venta_id)
    if venta is None:
        abort(404)
    return render_template("tienda/detalle_venta.html", venta=venta, items=tienda.items_de_venta(db, venta_id))


@bp.route("/ventas/<int:venta_id>/anular", methods=["GET", "POST"])
def anular_venta(venta_id):
    db = get_db()
    venta = tienda.obtener_venta(db, venta_id)
    if venta is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            tienda.anular_venta(db, venta_id, request.form.get("motivo"), permisos.usuario_actual())
        except ErrorDeNegocio as e:
            error = str(e)
        else:
            flash("Venta anulada. El stock volvió al inventario.", "success")
            return redirect(url_for("tienda.detalle_venta", venta_id=venta_id))
    return render_template("tienda/anular_venta.html", venta=venta, items=tienda.items_de_venta(db, venta_id),
                           error=error, motivo=request.form.get("motivo", ""))


# --------------------------------------------------------------- productos
@bp.get("/productos")
def productos():
    q = request.args.get("q", "").strip()
    return render_template("tienda/productos.html", productos=tienda.listar_productos(get_db(), q=q), q=q)


def _valores(p):
    return {"nombre": p["nombre"], "marca": p["marca"] or "", "categoria": p["categoria"] or "",
            "precio": monto_form(p["precio_centavos"]),
            "costo": monto_form(p["costo_centavos"]) if p["costo_centavos"] is not None else "",
            "stock_minimo": p["stock_minimo"]}


@bp.route("/productos/nuevo", methods=["GET", "POST"])
def producto_nuevo():
    db = get_db()
    errores = {}
    if request.method == "POST":
        datos, errores = tienda.validar_producto(db, request.form)
        if not errores:
            try:
                with db:
                    tienda.crear_producto(db, datos, permisos.usuario_actual())
            except sqlite3.IntegrityError:
                errores["nombre"] = "Ya existe un producto con ese nombre y marca."
            else:
                flash(f"Producto «{datos['nombre']}» creado.", "success")
                return redirect(url_for("tienda.productos"))
        flash("Revisá los campos marcados en rojo.", "danger")
        return render_template("tienda/producto_form.html", valores=request.form, errores=errores, producto=None,
                               categorias=tienda.categorias(db))
    return render_template("tienda/producto_form.html", valores={}, errores=errores, producto=None,
                           categorias=tienda.categorias(db))


@bp.route("/productos/<int:producto_id>/editar", methods=["GET", "POST"])
def producto_editar(producto_id):
    db = get_db()
    producto = tienda.obtener_producto(db, producto_id)
    if producto is None:
        abort(404)
    errores = {}
    if request.method == "POST":
        datos, errores = tienda.validar_producto(db, request.form, producto_id=producto_id)
        if not errores:
            try:
                with db:
                    tienda.actualizar_producto(db, producto_id, datos)
            except sqlite3.IntegrityError:
                errores["nombre"] = "Ya existe un producto con ese nombre y marca."
            else:
                flash("Producto actualizado. Las ventas ya hechas conservan el precio que tenían.", "success")
                return redirect(url_for("tienda.productos"))
        flash("Revisá los campos marcados en rojo.", "danger")
        return render_template("tienda/producto_form.html", valores=request.form, errores=errores, producto=producto,
                               categorias=tienda.categorias(db))
    return render_template("tienda/producto_form.html", valores=_valores(producto), errores=errores, producto=producto,
                           categorias=tienda.categorias(db))


@bp.post("/productos/<int:producto_id>/<accion>")
def producto_activar(producto_id, accion):
    if accion not in ("activar", "desactivar"):
        abort(404)
    db = get_db()
    if tienda.obtener_producto(db, producto_id) is None:
        abort(404)
    with db:
        tienda.cambiar_activo(db, producto_id, accion == "activar")
    flash("Producto activado." if accion == "activar" else "Producto desactivado: ya no aparece para vender.", "success")
    return redirect(url_for("tienda.productos"))


# ------------------------------------------------------------------- stock
@bp.get("/productos/<int:producto_id>/stock")
def stock(producto_id):
    db = get_db()
    producto = tienda.obtener_producto(db, producto_id)
    if producto is None:
        abort(404)
    return render_template("tienda/stock.html", producto=producto, movimientos=tienda.movimientos(db, producto_id, 30),
                           errores={}, form={})


@bp.post("/productos/<int:producto_id>/stock/<operacion>")
def stock_operar(producto_id, operacion):
    if operacion not in ("entrada", "ajuste"):
        abort(404)
    db = get_db()
    producto = tienda.obtener_producto(db, producto_id)
    if producto is None:
        abort(404)
    usuario = permisos.usuario_actual()
    try:
        if operacion == "entrada":
            nuevo = tienda.entrada_mercaderia(db, producto_id, request.form.get("cantidad"), request.form.get("motivo"), usuario)
            flash(f"Entrada registrada. Stock actual: {nuevo}.", "success")
        else:
            variacion = tienda.ajustar_stock(db, producto_id, request.form.get("stock_real"), request.form.get("motivo"), usuario)
            flash(f"Stock ajustado ({variacion:+d}).", "success")
    except ErrorDeNegocio as e:
        return render_template("tienda/stock.html", producto=producto, movimientos=tienda.movimientos(db, producto_id, 30),
                               errores={operacion: str(e)}, form=request.form), 400
    return redirect(url_for("tienda.stock", producto_id=producto_id))


# ---------------------------------------------------------------- reportes
@bp.get("/faltantes")
def faltantes():
    return render_template("tienda/faltantes.html", productos=tienda.faltantes(get_db()))


@bp.get("/mas-vendidos")
def mas_vendidos():
    hoy = timeutils.hoy()
    desde0, hasta0 = tienda.periodo_por_defecto(hoy)
    desde = timeutils.parse_fecha(request.args.get("desde")) or desde0
    hasta = min(timeutils.parse_fecha(request.args.get("hasta")) or hasta0, hoy)
    error = None
    if desde > hasta:
        error = "La fecha «desde» no puede ser posterior a «hasta»."
        desde, hasta = desde0, hasta0
    return render_template("tienda/mas_vendidos.html", ranking=tienda.mas_vendidos(get_db(), desde, hasta),
                           desde=desde, hasta=hasta, hoy=hoy, error=error)
