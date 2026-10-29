"""Migraciones simples de la base de datos, numeradas y guardadas en PRAGMA user_version.

schema.sql crea la base original (versión 1). Cada migración de acá lleva una base existente a la
versión siguiente sin perder datos, así que quien ya tiene el sistema funcionando solo tiene que
reiniciarlo. Cada una corre dentro de una transacción: o se aplica entera o no se aplica.
Para agregar un cambio: sumá un elemento al final de MIGRACIONES con el número siguiente.
"""
import sqlite3

# ----------------------------------------------------------------------------------------------
# 2: anulaciones, pagos parciales, quién cargó cada cosa, planes con baja lógica, reingresos
# ----------------------------------------------------------------------------------------------
V2 = """
BEGIN;

ALTER TABLE planes ADD COLUMN activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1));

-- La membresía guarda su propia copia de la duración y del precio: si después se edita el plan,
-- los vencimientos ya otorgados no cambian.
ALTER TABLE membresias ADD COLUMN duracion_dias INTEGER;
ALTER TABLE membresias ADD COLUMN precio_centavos INTEGER;
ALTER TABLE membresias ADD COLUMN dias_extra INTEGER NOT NULL DEFAULT 0;
ALTER TABLE membresias ADD COLUMN cargada_por TEXT;
ALTER TABLE membresias ADD COLUMN anulada INTEGER NOT NULL DEFAULT 0 CHECK (anulada IN (0, 1));
ALTER TABLE membresias ADD COLUMN anulada_en TEXT;
ALTER TABLE membresias ADD COLUMN anulada_por TEXT;
ALTER TABLE membresias ADD COLUMN anulada_motivo TEXT;
UPDATE membresias SET
    duracion_dias   = (SELECT duracion_dias FROM planes WHERE planes.id = membresias.plan_id),
    precio_centavos = (SELECT precio_centavos FROM planes WHERE planes.id = membresias.plan_id);

ALTER TABLE pagos ADD COLUMN es_parcial INTEGER NOT NULL DEFAULT 0 CHECK (es_parcial IN (0, 1));
ALTER TABLE pagos ADD COLUMN cargado_por TEXT;
ALTER TABLE pagos ADD COLUMN anulado INTEGER NOT NULL DEFAULT 0 CHECK (anulado IN (0, 1));
ALTER TABLE pagos ADD COLUMN anulado_en TEXT;
ALTER TABLE pagos ADD COLUMN anulado_por TEXT;
ALTER TABLE pagos ADD COLUMN anulado_motivo TEXT;

-- Se reconstruye asistencias para sacarle UNIQUE (socio, fecha): ahora el reingreso es configurable.
CREATE TABLE asistencias_nueva (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    socio_id       INTEGER NOT NULL REFERENCES socios(id) ON DELETE RESTRICT,
    fecha          TEXT NOT NULL,
    hora           TEXT NOT NULL,
    registrado_por TEXT
);
INSERT INTO asistencias_nueva (id, socio_id, fecha, hora) SELECT id, socio_id, fecha, hora FROM asistencias;
DROP TABLE asistencias;
ALTER TABLE asistencias_nueva RENAME TO asistencias;
CREATE INDEX IF NOT EXISTS idx_asistencias_fecha ON asistencias(fecha);
CREATE INDEX IF NOT EXISTS idx_asistencias_socio_fecha ON asistencias(socio_id, fecha);

-- La membresía "actual" ignora las anuladas.
DROP VIEW IF EXISTS vista_socios;
CREATE VIEW vista_socios AS
SELECT s.id, s.nombre, s.dni, s.telefono, s.email, s.fecha_alta, s.estado, s.foto, s.notas,
       m.id AS membresia_id, m.plan_id, m.fecha_inicio, m.fecha_vencimiento, m.dias_extra,
       p.nombre AS plan_nombre
FROM socios s
LEFT JOIN membresias m ON m.id = (SELECT MAX(id) FROM membresias WHERE socio_id = s.id AND anulada = 0)
LEFT JOIN planes p ON p.id = m.plan_id;

PRAGMA user_version = 2;
COMMIT;
"""

# ----------------------------------------------------------------------------------------------
# 3: módulo Tienda (suplementos): productos, ventas de mostrador y movimientos de stock
# ----------------------------------------------------------------------------------------------
V3 = """
BEGIN;

CREATE TABLE productos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre           TEXT    NOT NULL,
    marca            TEXT,
    categoria        TEXT,
    precio_centavos  INTEGER NOT NULL CHECK (precio_centavos > 0),
    costo_centavos   INTEGER CHECK (costo_centavos IS NULL OR costo_centavos >= 0),
    stock            INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    stock_minimo     INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
    activo           INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    creado_en        TEXT    NOT NULL
);
CREATE UNIQUE INDEX ux_productos_nombre_marca ON productos (lower(nombre), lower(COALESCE(marca, '')));

CREATE TABLE ventas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha           TEXT    NOT NULL,
    hora            TEXT    NOT NULL,
    socio_id        INTEGER REFERENCES socios(id) ON DELETE RESTRICT,
    metodo          TEXT    NOT NULL CHECK (metodo IN ('efectivo', 'transferencia', 'tarjeta')),
    total_centavos  INTEGER NOT NULL CHECK (total_centavos > 0),
    cargada_por     TEXT,
    creada_en       TEXT    NOT NULL,
    anulada         INTEGER NOT NULL DEFAULT 0 CHECK (anulada IN (0, 1)),
    anulada_en      TEXT,
    anulada_por     TEXT,
    anulada_motivo  TEXT
);
CREATE INDEX idx_ventas_fecha ON ventas(fecha);

-- Cada renglón guarda el nombre, el precio y el costo de ese momento: si después cambian, la venta no se altera.
CREATE TABLE venta_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id                INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id             INTEGER NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
    nombre_producto         TEXT    NOT NULL,
    cantidad                INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario_centavos INTEGER NOT NULL CHECK (precio_unitario_centavos > 0),
    costo_unitario_centavos  INTEGER
);
CREATE INDEX idx_venta_items_venta ON venta_items(venta_id);
CREATE INDEX idx_venta_items_producto ON venta_items(producto_id);

-- Historial de stock: cada cambio queda con quién, cuándo y por qué. cantidad es la variación (negativa si baja).
CREATE TABLE movimientos_stock (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id      INTEGER NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
    tipo             TEXT    NOT NULL CHECK (tipo IN ('entrada', 'ajuste', 'venta', 'anulacion_venta')),
    cantidad         INTEGER NOT NULL CHECK (cantidad <> 0),
    stock_resultante INTEGER NOT NULL CHECK (stock_resultante >= 0),
    motivo           TEXT,
    venta_id         INTEGER REFERENCES ventas(id) ON DELETE RESTRICT,
    usuario          TEXT,
    creado_en        TEXT    NOT NULL
);
CREATE INDEX idx_movimientos_producto ON movimientos_stock(producto_id);

PRAGMA user_version = 3;
COMMIT;
"""

# ----------------------------------------------------------------------------------------------
# 4: configuración guardada en la base (asistente de primera vez y pantalla Configuración)
# ----------------------------------------------------------------------------------------------
V4 = """
BEGIN;

CREATE TABLE configuracion (
    clave          TEXT PRIMARY KEY,
    valor          TEXT NOT NULL,
    actualizada_en TEXT NOT NULL
);

PRAGMA user_version = 4;
COMMIT;
"""

# V5: cuentas de usuario en la base (recepción) y registro de importaciones.
# Los usuarios no se borran: se desactivan, así el nombre que figura en pagos, ventas e ingresos viejos
# sigue apuntando a una persona y no se puede reutilizar para otra.
V5 = """
BEGIN;
CREATE TABLE usuarios (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario        TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    clave_hash     TEXT    NOT NULL,
    rol            TEXT    NOT NULL DEFAULT 'recepcion' CHECK (rol IN ('admin', 'recepcion')),
    activo         INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    creado_en      TEXT    NOT NULL,
    creado_por     TEXT,
    desactivado_en TEXT
);
CREATE TABLE importaciones (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    creada_en  TEXT    NOT NULL,
    usuario    TEXT,
    importadas INTEGER NOT NULL CHECK (importadas >= 0),
    omitidas   INTEGER NOT NULL DEFAULT 0 CHECK (omitidas >= 0)
);
PRAGMA user_version = 5;
COMMIT;
"""

# ----------------------------------------------------------------------------------------------
# 6: pagos por varios períodos y descuento por pago anual (tarea H, IA 3)
#    (Era la V5 en la rama de la IA 3; al unir con la V5 de cuentas de usuario se renumeró a V6. Ver INFORME_UNION.md.)
# ----------------------------------------------------------------------------------------------
V6 = """
BEGIN;

-- Descuento opcional por pago anual, por plan: 'porcentaje' (valor = 1..99) o 'monto' (valor en centavos).
ALTER TABLE planes ADD COLUMN descuento_anual_tipo TEXT
    CHECK (descuento_anual_tipo IS NULL OR descuento_anual_tipo IN ('porcentaje', 'monto'));
ALTER TABLE planes ADD COLUMN descuento_anual_valor INTEGER
    CHECK (descuento_anual_valor IS NULL OR descuento_anual_valor > 0);

-- Descuento que se le hizo a un pago anual. monto_centavos sigue siendo la plata que entró de verdad
-- (la caja suma solo eso); el descuento cuenta como crédito al calcular cuántos períodos cubre el pago.
ALTER TABLE pagos ADD COLUMN descuento_centavos INTEGER NOT NULL DEFAULT 0 CHECK (descuento_centavos >= 0);

PRAGMA user_version = 6;
COMMIT;
"""

MIGRACIONES: list[tuple[int, str]] = [
    (2, V2),
    (3, V3),
    (4, V4),
    (5, V5),
    (6, V6),
]

VERSION_ACTUAL = MIGRACIONES[-1][0]


def version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def aplicar(conn: sqlite3.Connection) -> int:
    """Aplica las migraciones pendientes y devuelve la versión final."""
    actual = version(conn)
    for numero, sql in MIGRACIONES:
        if numero > actual:
            try:
                conn.executescript(sql)
            except sqlite3.Error:
                if conn.in_transaction:
                    conn.rollback()
                raise
            actual = numero
    return actual
