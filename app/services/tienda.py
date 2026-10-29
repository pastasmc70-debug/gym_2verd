"""Módulo Tienda (suplementos): productos, venta de mostrador, stock, faltantes y reportes.

Reglas:
  - El stock nunca queda negativo: si no alcanza, la venta se rechaza diciendo qué falta.
  - Cada cambio de stock (venta, anulación, entrada, ajuste) deja un movimiento con quién, cuándo y por qué.
  - Una venta guarda el nombre, el precio y el costo del momento: editar el producto después no la altera.
  - Anular una venta (con motivo) devuelve el stock y deja de contar en la caja y en los reportes.
  - Sin facturación electrónica: esto es un registro interno de ventas.
"""
from datetime import date, datetime, timedelta

from .. import models, timeutils
from .errors import ErrorDeNegocio
from .validation import MONTO_MAXIMO_CENTAVOS, limpiar, parse_monto

STOCK_MAXIMO = 1_000_000
CANTIDAD_MAXIMA_POR_ITEM = 1000
MOTIVO_MAX = 300


def _ahora_iso() -> str:
    return timeutils.ahora().isoformat(timespec="seconds")


def _entero(texto, minimo: int, maximo: int):
    try:
        n = int(limpiar(str(texto)))
    except (ValueError, TypeError):
        return None
    return n if minimo <= n <= maximo else None


def _motivo(texto, obligatorio_msg="Escribí el motivo.") -> str:
    texto = limpiar(texto)
    if not texto:
        raise ErrorDeNegocio(obligatorio_msg, "motivo")
    if len(texto) > MOTIVO_MAX:
        raise ErrorDeNegocio(f"El motivo es demasiado largo (máximo {MOTIVO_MAX} caracteres).", "motivo")
    return texto


# ------------------------------------------------------------------ productos
def obtener_producto(db, producto_id):
    return db.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()


def listar_productos(db, q: str = "", solo_activos: bool = False):
    donde, params = [], []
    if q:
        donde.append("(nombre LIKE ? OR marca LIKE ? OR categoria LIKE ?)")
        params += [f"%{q}%"] * 3
    if solo_activos:
        donde.append("activo = 1")
    sql = "SELECT * FROM productos" + (" WHERE " + " AND ".join(donde) if donde else "")
    return db.execute(sql + " ORDER BY activo DESC, nombre COLLATE NOCASE, marca COLLATE NOCASE", params).fetchall()


def categorias(db) -> list[str]:
    return [r[0] for r in db.execute(
        "SELECT DISTINCT categoria FROM productos WHERE categoria IS NOT NULL AND categoria <> '' ORDER BY categoria COLLATE NOCASE")]


def validar_producto(db, form, producto_id=None):
    """Devuelve (datos_limpios, errores). En la edición el stock no se toca: se cambia con entradas o ajustes."""
    errores, d = {}, {}

    d["nombre"] = limpiar(form.get("nombre"))
    if not d["nombre"]:
        errores["nombre"] = "Ingresá el nombre del producto."
    elif len(d["nombre"]) > 80:
        errores["nombre"] = "El nombre es demasiado largo (máximo 80 caracteres)."

    d["marca"] = limpiar(form.get("marca")) or None
    d["categoria"] = limpiar(form.get("categoria")) or None
    for campo, etiqueta in (("marca", "La marca"), ("categoria", "La categoría")):
        if d[campo] and len(d[campo]) > 60:
            errores[campo] = f"{etiqueta} es demasiado larga (máximo 60 caracteres)."

    if "nombre" not in errores:
        otro = db.execute(
            "SELECT id FROM productos WHERE lower(nombre) = lower(?) AND lower(COALESCE(marca, '')) = lower(?)",
            (d["nombre"], d["marca"] or "")).fetchone()
        if otro and otro["id"] != producto_id:
            errores["nombre"] = "Ya existe un producto con ese nombre y esa marca."

    d["precio_centavos"] = None
    try:
        precio = parse_monto(form.get("precio"))
        if precio <= 0:
            errores["precio"] = "El precio de venta tiene que ser mayor a cero."
        elif precio > MONTO_MAXIMO_CENTAVOS:
            errores["precio"] = "El precio es demasiado alto."
        else:
            d["precio_centavos"] = precio
    except ValueError:
        errores["precio"] = "Ingresá un precio válido, por ejemplo 18000 o 18.000,50."

    d["costo_centavos"] = None
    if limpiar(form.get("costo")):
        try:
            costo = parse_monto(form.get("costo"))
            if costo < 0 or costo > MONTO_MAXIMO_CENTAVOS:
                errores["costo"] = "El costo no puede ser negativo ni tan alto."
            else:
                d["costo_centavos"] = costo
        except ValueError:
            errores["costo"] = "Ingresá un costo válido o dejalo vacío."

    d["stock_minimo"] = _entero(form.get("stock_minimo") or "0", 0, STOCK_MAXIMO)
    if d["stock_minimo"] is None:
        errores["stock_minimo"] = "El stock mínimo tiene que ser un número entero de 0 en adelante."

    if producto_id is None:
        d["stock"] = _entero(form.get("stock") or "0", 0, STOCK_MAXIMO)
        if d["stock"] is None:
            errores["stock"] = "El stock inicial tiene que ser un número entero de 0 en adelante."
    return d, errores


def crear_producto(db, d, usuario: str | None = None) -> int:
    with db:
        cur = db.execute(
            """INSERT INTO productos (nombre, marca, categoria, precio_centavos, costo_centavos, stock, stock_minimo, creado_en)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (d["nombre"], d["marca"], d["categoria"], d["precio_centavos"], d["costo_centavos"], d["stock"],
             d["stock_minimo"], _ahora_iso()))
        if d["stock"] > 0:
            _movimiento(db, cur.lastrowid, "entrada", d["stock"], d["stock"], "Stock inicial", None, usuario)
    return cur.lastrowid


def actualizar_producto(db, producto_id, d) -> None:
    with db:
        db.execute(
            """UPDATE productos SET nombre = ?, marca = ?, categoria = ?, precio_centavos = ?, costo_centavos = ?,
                      stock_minimo = ? WHERE id = ?""",
            (d["nombre"], d["marca"], d["categoria"], d["precio_centavos"], d["costo_centavos"], d["stock_minimo"],
             producto_id))


def cambiar_activo(db, producto_id, activo: bool) -> None:
    with db:
        db.execute("UPDATE productos SET activo = ? WHERE id = ?", (1 if activo else 0, producto_id))


def _movimiento(db, producto_id, tipo, cantidad, stock_resultante, motivo, venta_id, usuario) -> None:
    db.execute(
        """INSERT INTO movimientos_stock (producto_id, tipo, cantidad, stock_resultante, motivo, venta_id, usuario, creado_en)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (producto_id, tipo, cantidad, stock_resultante, motivo, venta_id, usuario, _ahora_iso()))


def movimientos(db, producto_id, limite: int = 15):
    return db.execute("SELECT * FROM movimientos_stock WHERE producto_id = ? ORDER BY id DESC LIMIT ?",
                      (producto_id, limite)).fetchall()


# ---------------------------------------------------------------------- stock
def entrada_mercaderia(db, producto_id: int, cantidad, motivo, usuario: str | None = None) -> int:
    """Suma stock (compra a un proveedor, por ejemplo). Devuelve el stock resultante."""
    producto = obtener_producto(db, producto_id)
    if producto is None:
        raise ErrorDeNegocio("No encontramos el producto.", "producto")
    n = _entero(cantidad, 1, STOCK_MAXIMO)
    if n is None:
        raise ErrorDeNegocio("La cantidad de la entrada tiene que ser un número entero mayor a cero.", "cantidad")
    motivo = _motivo(motivo, "Escribí el motivo de la entrada (por ejemplo, la compra al proveedor).")
    nuevo = producto["stock"] + n
    if nuevo > STOCK_MAXIMO:
        raise ErrorDeNegocio("Con esa entrada el stock sería demasiado alto. Revisá la cantidad.", "cantidad")
    with db:
        db.execute("UPDATE productos SET stock = ? WHERE id = ?", (nuevo, producto_id))
        _movimiento(db, producto_id, "entrada", n, nuevo, motivo, None, usuario)
    return nuevo


def ajustar_stock(db, producto_id: int, stock_real, motivo, usuario: str | None = None) -> int:
    """Fija el stock en lo que realmente hay (conteo, rotura, vencimiento…). Devuelve la variación."""
    producto = obtener_producto(db, producto_id)
    if producto is None:
        raise ErrorDeNegocio("No encontramos el producto.", "producto")
    nuevo = _entero(stock_real, 0, STOCK_MAXIMO)
    if nuevo is None:
        raise ErrorDeNegocio("El stock real tiene que ser un número entero de 0 en adelante.", "cantidad")
    motivo = _motivo(motivo, "Escribí el motivo del ajuste (por ejemplo, «conteo del inventario» o «producto vencido»).")
    variacion = nuevo - producto["stock"]
    if variacion == 0:
        raise ErrorDeNegocio("El stock real es igual al que figura: no hay nada que ajustar.", "sin_cambio")
    with db:
        db.execute("UPDATE productos SET stock = ? WHERE id = ?", (nuevo, producto_id))
        _movimiento(db, producto_id, "ajuste", variacion, nuevo, motivo, None, usuario)
    return variacion


def faltantes(db):
    """Productos activos con stock en o por debajo del mínimo (los agotados incluidos), los más críticos primero."""
    return db.execute(
        """SELECT *, (stock_minimo - stock) AS faltan FROM productos
           WHERE activo = 1 AND stock <= stock_minimo ORDER BY stock - stock_minimo, nombre COLLATE NOCASE""").fetchall()


# --------------------------------------------------------------------- ventas
def registrar_venta(db, items, metodo: str, socio_id: int | None = None, usuario: str | None = None,
                    fecha: date | None = None, ahora: datetime | None = None) -> dict:
    """Registra una venta de mostrador y descuenta el stock. `items` es una lista de (producto_id, cantidad).

    Todo o nada: si algún producto no alcanza, no se vende ni se descuenta nada.
    """
    ahora = ahora or timeutils.ahora()
    fecha = fecha or ahora.date()
    if metodo not in models.METODOS_PAGO:
        raise ErrorDeNegocio("Elegí cómo pagó: efectivo, transferencia o tarjeta.", "metodo")
    if socio_id is not None and models.obtener_socio(db, socio_id) is None:
        raise ErrorDeNegocio("No encontramos al socio.", "socio")

    pedidos: dict[int, int] = {}
    for producto_id, cantidad in items:
        n = _entero(cantidad, 1, CANTIDAD_MAXIMA_POR_ITEM)
        if n is None:
            raise ErrorDeNegocio(f"Las cantidades tienen que ser números enteros entre 1 y {CANTIDAD_MAXIMA_POR_ITEM}.", "cantidad")
        pedidos[producto_id] = pedidos.get(producto_id, 0) + n
    if not pedidos:
        raise ErrorDeNegocio("Elegí al menos un producto para vender.", "sin_items")

    productos, sin_stock = {}, []
    for producto_id, n in pedidos.items():
        p = obtener_producto(db, producto_id)
        if p is None:
            raise ErrorDeNegocio("Uno de los productos ya no existe. Volvé a armar la venta.", "producto")
        if not p["activo"]:
            raise ErrorDeNegocio(f"«{p['nombre']}» está desactivado y no se puede vender.", "inactivo")
        if n > p["stock"]:
            sin_stock.append(f"«{p['nombre']}» (pediste {n}, hay {p['stock']})")
        productos[producto_id] = p
    if sin_stock:
        raise ErrorDeNegocio("No alcanza el stock: " + "; ".join(sin_stock) + ". Corregí las cantidades.", "sin_stock",
                             faltantes=sin_stock)

    total = sum(productos[i]["precio_centavos"] * n for i, n in pedidos.items())
    if total > MONTO_MAXIMO_CENTAVOS:
        raise ErrorDeNegocio("El total de la venta es demasiado alto. Revisá las cantidades.", "total")

    with db:
        cur = db.execute(
            """INSERT INTO ventas (fecha, hora, socio_id, metodo, total_centavos, cargada_por, creada_en)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (fecha.isoformat(), ahora.strftime("%H:%M:%S"), socio_id, metodo, total, usuario, _ahora_iso()))
        venta_id = cur.lastrowid
        for producto_id, n in pedidos.items():
            p = productos[producto_id]
            actualizado = db.execute("UPDATE productos SET stock = stock - ? WHERE id = ? AND stock >= ?",
                                     (n, producto_id, n))
            if actualizado.rowcount != 1:   # alguien vendió lo mismo justo antes: se deshace todo (rollback del with)
                raise ErrorDeNegocio(f"«{p['nombre']}» se quedó sin stock mientras armabas la venta.", "sin_stock")
            db.execute(
                """INSERT INTO venta_items (venta_id, producto_id, nombre_producto, cantidad, precio_unitario_centavos,
                                            costo_unitario_centavos) VALUES (?, ?, ?, ?, ?, ?)""",
                (venta_id, producto_id, p["nombre"] + (f" ({p['marca']})" if p["marca"] else ""), n,
                 p["precio_centavos"], p["costo_centavos"]))
            _movimiento(db, producto_id, "venta", -n, p["stock"] - n, f"Venta #{venta_id}", venta_id, usuario)
    return {"venta_id": venta_id, "total_centavos": total}


def anular_venta(db, venta_id: int, motivo, usuario: str) -> dict:
    """Anula la venta (no se borra), devuelve el stock y deja de contar en la caja y en los reportes."""
    motivo = _motivo(motivo, "Escribí el motivo de la anulación.")
    venta = obtener_venta(db, venta_id)
    if venta is None:
        raise ErrorDeNegocio("No encontramos la venta.", "venta")
    if venta["anulada"]:
        raise ErrorDeNegocio("Esa venta ya estaba anulada.", "ya_anulada")
    with db:
        for item in items_de_venta(db, venta_id):
            db.execute("UPDATE productos SET stock = stock + ? WHERE id = ?", (item["cantidad"], item["producto_id"]))
            stock = db.execute("SELECT stock FROM productos WHERE id = ?", (item["producto_id"],)).fetchone()[0]
            _movimiento(db, item["producto_id"], "anulacion_venta", item["cantidad"], stock,
                        f"Anulación de la venta #{venta_id}: {motivo}", venta_id, usuario)
        db.execute("UPDATE ventas SET anulada = 1, anulada_en = ?, anulada_por = ?, anulada_motivo = ? WHERE id = ?",
                   (_ahora_iso(), usuario, motivo, venta_id))
    return {"venta": venta}


def obtener_venta(db, venta_id):
    return db.execute(
        """SELECT v.*, s.nombre AS socio_nombre, s.dni AS socio_dni FROM ventas v
           LEFT JOIN socios s ON s.id = v.socio_id WHERE v.id = ?""", (venta_id,)).fetchone()


def items_de_venta(db, venta_id):
    return db.execute("SELECT * FROM venta_items WHERE venta_id = ? ORDER BY id", (venta_id,)).fetchall()


def ventas_del_dia(db, fecha: date):
    """Todas las ventas del día (las anuladas también, marcadas) con la cantidad de unidades de cada una."""
    return db.execute(
        """SELECT v.*, s.nombre AS socio_nombre,
                  (SELECT SUM(cantidad) FROM venta_items WHERE venta_id = v.id) AS unidades
           FROM ventas v LEFT JOIN socios s ON s.id = v.socio_id WHERE v.fecha = ? ORDER BY v.id DESC""",
        (fecha.isoformat(),)).fetchall()


# ---------------------------------------------------------- caja y reportes
def caja_del_dia(db, fecha: date) -> dict:
    ventas = ventas_del_dia(db, fecha)
    vigentes = [v for v in ventas if not v["anulada"]]
    por_metodo = {m: 0 for m in models.METODOS_PAGO}
    for v in vigentes:
        por_metodo[v["metodo"]] += v["total_centavos"]
    return {"ventas": ventas, "total_centavos": sum(v["total_centavos"] for v in vigentes), "por_metodo": por_metodo,
            "cantidad": len(vigentes), "anuladas": len(ventas) - len(vigentes)}


def ingresos_del_mes(db, hoy: date) -> int:
    desde, hasta = timeutils.primer_dia_mes(hoy), timeutils.primer_dia_mes_siguiente(hoy)
    return db.execute("SELECT COALESCE(SUM(total_centavos), 0) FROM ventas WHERE anulada = 0 AND fecha >= ? AND fecha < ?",
                      (desde.isoformat(), hasta.isoformat())).fetchone()[0]


def mas_vendidos(db, desde: date, hasta: date, limite: int = 10):
    """Productos más vendidos entre dos fechas (inclusive), por unidades. Las ventas anuladas no cuentan."""
    return db.execute(
        """SELECT i.producto_id, p.nombre, p.marca, SUM(i.cantidad) AS unidades,
                  SUM(i.cantidad * i.precio_unitario_centavos) AS importe_centavos,
                  SUM(CASE WHEN i.costo_unitario_centavos IS NOT NULL
                           THEN i.cantidad * (i.precio_unitario_centavos - i.costo_unitario_centavos) END) AS ganancia_centavos
           FROM venta_items i JOIN ventas v ON v.id = i.venta_id JOIN productos p ON p.id = i.producto_id
           WHERE v.anulada = 0 AND v.fecha >= ? AND v.fecha <= ?
           GROUP BY i.producto_id ORDER BY unidades DESC, importe_centavos DESC, p.nombre COLLATE NOCASE LIMIT ?""",
        (desde.isoformat(), hasta.isoformat(), limite)).fetchall()


def periodo_por_defecto(hoy: date) -> tuple[date, date]:
    """Últimos 30 días, hoy incluido."""
    return hoy - timedelta(days=29), hoy
