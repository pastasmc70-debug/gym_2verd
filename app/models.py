"""Capa de datos: constantes y consultas SQL. No hace commit; eso lo decide quien llama."""
from . import timeutils

ESTADOS_SOCIO = ("activo", "pausado", "baja")
METODOS_PAGO = ("efectivo", "transferencia", "tarjeta")

# Estados de la membresía (se calculan, no se guardan)
VIGENTE = "vigente"
POR_VENCER = "por_vencer"
VENCIDA = "vencida"
SIN_MEMBRESIA = "sin_membresia"


# ---------------------------------------------------------------- socios
def obtener_socio(db, socio_id):
    return db.execute("SELECT * FROM vista_socios WHERE id = ?", (socio_id,)).fetchone()


def obtener_socio_por_dni(db, dni):
    return db.execute("SELECT * FROM vista_socios WHERE dni = ?", (dni,)).fetchone()


def _filtro_socios(q, estado):
    donde, params = [], []
    if q:
        donde.append("(nombre LIKE ? OR dni LIKE ? OR telefono LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like]
    if estado:
        donde.append("estado = ?")
        params.append(estado)
    return (" WHERE " + " AND ".join(donde)) if donde else "", params


def listar_socios(db, q="", estado="", limite=20, desplazamiento=0):
    donde, params = _filtro_socios(q, estado)
    return db.execute(
        f"SELECT * FROM vista_socios{donde} ORDER BY nombre COLLATE NOCASE LIMIT ? OFFSET ?",
        params + [limite, desplazamiento],
    ).fetchall()


def contar_socios(db, q="", estado=""):
    donde, params = _filtro_socios(q, estado)
    return db.execute(f"SELECT COUNT(*) FROM vista_socios{donde}", params).fetchone()[0]


def todos_los_socios(db):
    return db.execute("SELECT * FROM vista_socios ORDER BY nombre COLLATE NOCASE").fetchall()


def crear_socio(db, d) -> int:
    cur = db.execute(
        """INSERT INTO socios (nombre, dni, telefono, email, fecha_alta, estado, foto, notas, creado_en)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (d["nombre"], d["dni"], d["telefono"], d["email"], d["fecha_alta"], d["estado"],
         d.get("foto"), d["notas"], timeutils.ahora().isoformat(timespec="seconds")),
    )
    return cur.lastrowid


def actualizar_socio(db, socio_id, d) -> None:
    db.execute(
        """UPDATE socios SET nombre = ?, dni = ?, telefono = ?, email = ?, fecha_alta = ?,
                  estado = ?, foto = ?, notas = ? WHERE id = ?""",
        (d["nombre"], d["dni"], d["telefono"], d["email"], d["fecha_alta"], d["estado"],
         d.get("foto"), d["notas"], socio_id),
    )


def socios_activos_con_vencimiento_hasta(db, fecha_limite):
    """Socios activos cuya membresía actual vence a más tardar en fecha_limite (incluye vencidas)."""
    return db.execute(
        """SELECT * FROM vista_socios
           WHERE estado = 'activo' AND fecha_vencimiento IS NOT NULL AND fecha_vencimiento <= ?
           ORDER BY fecha_vencimiento, nombre COLLATE NOCASE""",
        (fecha_limite.isoformat(),),
    ).fetchall()


# ---------------------------------------------------------------- planes
def listar_planes(db, solo_activos=False):
    donde = " WHERE activo = 1" if solo_activos else ""
    return db.execute(f"SELECT * FROM planes{donde} ORDER BY precio_centavos, nombre").fetchall()


def obtener_plan(db, plan_id):
    return db.execute("SELECT * FROM planes WHERE id = ?", (plan_id,)).fetchone()


def crear_plan(db, d) -> int:
    cur = db.execute(
        """INSERT INTO planes (nombre, precio_centavos, duracion_dias, clases_por_semana,
                               descuento_anual_tipo, descuento_anual_valor) VALUES (?, ?, ?, ?, ?, ?)""",
        (d["nombre"], d["precio_centavos"], d["duracion_dias"], d["clases_por_semana"],
         d.get("descuento_anual_tipo"), d.get("descuento_anual_valor")),
    )
    return cur.lastrowid


def actualizar_plan(db, plan_id, d) -> None:
    db.execute(
        """UPDATE planes SET nombre = ?, precio_centavos = ?, duracion_dias = ?, clases_por_semana = ?,
                  descuento_anual_tipo = ?, descuento_anual_valor = ? WHERE id = ?""",
        (d["nombre"], d["precio_centavos"], d["duracion_dias"], d["clases_por_semana"],
         d.get("descuento_anual_tipo"), d.get("descuento_anual_valor"), plan_id),
    )


def cantidad_membresias_del_plan(db, plan_id) -> int:
    return db.execute("SELECT COUNT(*) FROM membresias WHERE plan_id = ?", (plan_id,)).fetchone()[0]


def cambiar_activo_plan(db, plan_id, activo: bool) -> None:
    db.execute("UPDATE planes SET activo = ? WHERE id = ?", (1 if activo else 0, plan_id))


def borrar_plan(db, plan_id) -> None:
    db.execute("DELETE FROM planes WHERE id = ?", (plan_id,))


# ------------------------------------------------------------ membresías
def membresia_actual(db, socio_id):
    """La membresía más reciente que no esté anulada."""
    return db.execute(
        """SELECT m.id, m.socio_id, m.plan_id, m.fecha_inicio, m.fecha_vencimiento, m.dias_extra,
                  m.anulada, p.nombre AS plan_nombre,
                  COALESCE(m.duracion_dias, p.duracion_dias) AS duracion_dias,
                  COALESCE(m.precio_centavos, p.precio_centavos) AS precio_centavos,
                  p.clases_por_semana, p.descuento_anual_tipo, p.descuento_anual_valor
           FROM membresias m JOIN planes p ON p.id = m.plan_id
           WHERE m.socio_id = ? AND m.anulada = 0 ORDER BY m.id DESC LIMIT 1""",
        (socio_id,),
    ).fetchone()


def obtener_membresia(db, membresia_id):
    return db.execute(
        """SELECT m.id, m.socio_id, m.plan_id, m.fecha_inicio, m.fecha_vencimiento, m.dias_extra,
                  m.anulada, m.anulada_en, m.anulada_por, m.anulada_motivo, m.cargada_por,
                  p.nombre AS plan_nombre,
                  COALESCE(m.duracion_dias, p.duracion_dias) AS duracion_dias,
                  COALESCE(m.precio_centavos, p.precio_centavos) AS precio_centavos
           FROM membresias m JOIN planes p ON p.id = m.plan_id WHERE m.id = ?""",
        (membresia_id,),
    ).fetchone()


def historial_membresias(db, socio_id):
    """Todas, incluidas las anuladas (que se muestran marcadas)."""
    return db.execute(
        """SELECT m.*, p.nombre AS plan_nombre,
                  (SELECT COUNT(*) FROM pagos WHERE membresia_id = m.id AND anulado = 0) AS pagos_activos
           FROM membresias m JOIN planes p ON p.id = m.plan_id WHERE m.socio_id = ? ORDER BY m.id DESC""",
        (socio_id,),
    ).fetchall()


def pagos_activos_de_membresia(db, membresia_id):
    """Pagos no anulados en el orden en que se aplican (fecha, y a igual fecha el orden de carga)."""
    return db.execute(
        "SELECT * FROM pagos WHERE membresia_id = ? AND anulado = 0 ORDER BY fecha, id", (membresia_id,)
    ).fetchall()


# ----------------------------------------------------------------- pagos
def pagos_de_socio(db, socio_id):
    return db.execute(
        """SELECT pg.*, p.nombre AS plan_nombre FROM pagos pg
           JOIN membresias m ON m.id = pg.membresia_id JOIN planes p ON p.id = m.plan_id
           WHERE pg.socio_id = ? ORDER BY pg.fecha DESC, pg.id DESC""",
        (socio_id,),
    ).fetchall()


def obtener_pago(db, pago_id):
    return db.execute(
        """SELECT pg.*, s.nombre AS socio_nombre, s.dni AS socio_dni, p.nombre AS plan_nombre
           FROM pagos pg JOIN socios s ON s.id = pg.socio_id
           JOIN membresias m ON m.id = pg.membresia_id JOIN planes p ON p.id = m.plan_id
           WHERE pg.id = ?""",
        (pago_id,),
    ).fetchone()


def pagos_recientes(db, limite=100):
    return db.execute(
        """SELECT pg.*, s.nombre AS socio_nombre, s.dni AS socio_dni FROM pagos pg
           JOIN socios s ON s.id = pg.socio_id ORDER BY pg.fecha DESC, pg.id DESC LIMIT ?""",
        (limite,),
    ).fetchall()


def pagos_del_dia(db, fecha):
    """Todos los pagos con esa fecha, anulados incluidos (quien los muestra los marca)."""
    return db.execute(
        """SELECT pg.*, s.nombre AS socio_nombre, s.dni AS socio_dni FROM pagos pg
           JOIN socios s ON s.id = pg.socio_id WHERE pg.fecha = ? ORDER BY pg.id""",
        (fecha.isoformat(),),
    ).fetchall()


def todos_los_pagos(db):
    return db.execute(
        """SELECT pg.*, s.nombre AS socio_nombre, s.dni AS socio_dni, p.nombre AS plan_nombre
           FROM pagos pg JOIN socios s ON s.id = pg.socio_id
           JOIN membresias m ON m.id = pg.membresia_id JOIN planes p ON p.id = m.plan_id
           ORDER BY pg.fecha, pg.id"""
    ).fetchall()


# ----------------------------------------------------------- asistencias
def asistencias_del_dia(db, fecha):
    return db.execute(
        """SELECT a.*, s.nombre AS socio_nombre, s.dni AS socio_dni FROM asistencias a
           JOIN socios s ON s.id = a.socio_id WHERE a.fecha = ? ORDER BY a.hora DESC, a.id DESC""",
        (fecha.isoformat(),),
    ).fetchall()


def ultimas_asistencias(db, socio_id, limite=10):
    return db.execute(
        "SELECT * FROM asistencias WHERE socio_id = ? ORDER BY fecha DESC, hora DESC LIMIT ?", (socio_id, limite)
    ).fetchall()
