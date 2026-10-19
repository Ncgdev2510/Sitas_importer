"""
Módulo de base de datos para SITAS Importer.
Soporta SQLite nativo (sin dependencias adicionales) y PostgreSQL (mediante DATABASE_URL).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "sitas.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_db_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Abre conexión SQLite con soporte para diccionarios y claves foráneas activadas."""
    path = str(db_path or DEFAULT_DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    """Inicializa las tablas e índices si no existen."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_db_connection(db_path) as conn:
        conn.executescript(schema_sql)


@contextmanager
def db_transaction(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager que maneja commits/rollbacks automáticos."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
