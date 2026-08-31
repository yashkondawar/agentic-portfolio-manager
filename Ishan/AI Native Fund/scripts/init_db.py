"""Idempotently create/upgrade the afund SQLite database from schema.sql.

Usage:
    .venv\\Scripts\\python scripts\\init_db.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from afund.config import get_db_path  # noqa: E402
from afund.db.connection import get_conn  # noqa: E402

SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"
SCHEMA_VERSION = "0001_phase0_initial"

# Post-Phase-0 additive migrations that CREATE TABLE IF NOT EXISTS can't
# express (new columns on a table that already exists in live DBs). Each is
# (version, idempotent_check_sql, ddl_sql). idempotent_check_sql must return
# a truthy first column when the migration has already been applied.
_COLUMN_MIGRATIONS = [
    (
        "0002_index_data_source",
        "SELECT 1 FROM pragma_table_info('index_data') WHERE name = 'source'",
        "ALTER TABLE index_data ADD COLUMN source TEXT",
    ),
    (
        "0003_research_reports_xlsx_path",
        "SELECT 1 FROM pragma_table_info('research_reports') WHERE name = 'xlsx_path'",
        "ALTER TABLE research_reports ADD COLUMN xlsx_path TEXT",
    ),
]


def _apply_column_migrations(conn) -> None:
    for version, check_sql, ddl_sql in _COLUMN_MIGRATIONS:
        already_applied = conn.execute(check_sql).fetchone()
        if already_applied:
            continue
        conn.execute(ddl_sql)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, dt.datetime.now(dt.timezone.utc).isoformat()),
        )


def init_db() -> int:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_conn(db_path)
    try:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema_sql)

        already_applied = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (SCHEMA_VERSION,)
        ).fetchone()
        if not already_applied:
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, dt.datetime.now(dt.timezone.utc).isoformat()),
            )

        _apply_column_migrations(conn)
        conn.commit()

        table_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
        return table_count
    finally:
        conn.close()


if __name__ == "__main__":
    count = init_db()
    print(f"afund database initialized at {get_db_path()}")
    print(f"Tables present: {count}")
