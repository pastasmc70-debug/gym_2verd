"""Acceso a SQLite (biblioteca estándar, sin ORM)."""
import sqlite3
from pathlib import Path

from flask import current_app, g

from . import migraciones

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(ruta: str) -> sqlite3.Connection:
    """Abre una conexión lista para usar. Sirve también para scripts (seed.py) y tests."""
    if ruta != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if ruta != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Crea la base si no existe y la lleva a la versión actual (ver migraciones.py)."""
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    migraciones.aplicar(conn)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_error=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
