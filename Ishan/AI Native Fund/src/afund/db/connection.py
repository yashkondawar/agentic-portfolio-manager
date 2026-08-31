"""SQLite connection helper.

Every connection returned by get_conn():
  - enables WAL journal mode (concurrent readers, single writer, crash-safe)
  - enables foreign_keys enforcement (off by default in SQLite)
  - uses sqlite3.Row so results are accessible by column name
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from afund.config import get_db_path


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign keys enabled.

    Args:
        db_path: optional override. Defaults to config/settings.yaml's db_path.
    """
    resolved_path = Path(db_path) if db_path is not None else get_db_path()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn
