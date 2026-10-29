-- Esquema de la base de datos. Es idempotente: se puede correr varias veces.
-- Fechas: texto ISO 'AAAA-MM-DD'. Montos: enteros en centavos (evita errores de redondeo).

CREATE TABLE IF NOT EXISTS planes (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre             TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    precio_centavos    INTEGER NOT NULL CHECK (precio_centavos > 0),
    duracion_dias      INTEGER NOT NULL CHECK (duracion_dias > 0),
    clases_por_semana  INTEGER CHECK (clases_por_semana IS NULL OR clases_por_semana > 0)  -- NULL = ilimitado
);

CREATE TABLE IF NOT EXISTS socios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT NOT NULL,
    dni         TEXT NOT NULL UNIQUE,
    telefono    TEXT NOT NULL,
    email       TEXT,
    fecha_alta  TEXT NOT NULL,
    estado      TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'pausado', 'baja')),
    foto        TEXT,
    notas       TEXT,
    creado_en   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS membresias (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    socio_id           INTEGER NOT NULL REFERENCES socios(id) ON DELETE RESTRICT,
    plan_id            INTEGER NOT NULL REFERENCES planes(id) ON DELETE RESTRICT,
    fecha_inicio       TEXT NOT NULL,
    fecha_vencimiento  TEXT NOT NULL,
    creada_en          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pagos (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    socio_id              INTEGER NOT NULL REFERENCES socios(id) ON DELETE RESTRICT,
    membresia_id          INTEGER NOT NULL REFERENCES membresias(id) ON DELETE RESTRICT,
    monto_centavos        INTEGER NOT NULL CHECK (monto_centavos > 0),
    fecha                 TEXT NOT NULL,
    metodo                TEXT NOT NULL CHECK (metodo IN ('efectivo', 'transferencia', 'tarjeta')),
    nota                  TEXT,
    vencimiento_anterior  TEXT NOT NULL,
    vencimiento_nuevo     TEXT NOT NULL,
    creado_en             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asistencias (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    socio_id   INTEGER NOT NULL REFERENCES socios(id) ON DELETE RESTRICT,
    fecha      TEXT NOT NULL,
    hora       TEXT NOT NULL,
    UNIQUE (socio_id, fecha)
);

CREATE INDEX IF NOT EXISTS idx_membresias_socio ON membresias(socio_id);
CREATE INDEX IF NOT EXISTS idx_pagos_socio      ON pagos(socio_id);
CREATE INDEX IF NOT EXISTS idx_pagos_fecha      ON pagos(fecha);
CREATE INDEX IF NOT EXISTS idx_asistencias_fecha ON asistencias(fecha);

-- Cada socio con su membresía más reciente (la "actual").
CREATE VIEW IF NOT EXISTS vista_socios AS
SELECT s.id, s.nombre, s.dni, s.telefono, s.email, s.fecha_alta, s.estado, s.foto, s.notas,
       m.id AS membresia_id, m.plan_id, m.fecha_inicio, m.fecha_vencimiento,
       p.nombre AS plan_nombre
FROM socios s
LEFT JOIN membresias m ON m.id = (SELECT MAX(id) FROM membresias WHERE socio_id = s.id)
LEFT JOIN planes p ON p.id = m.plan_id;
