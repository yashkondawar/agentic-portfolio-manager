"""Schema-level tests: table existence, PRAGMA settings, UNIQUE constraints."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"

EXPECTED_TABLES = {
    "schema_migrations",
    "instruments",
    "universe_membership",
    "daily_prices",
    "corporate_actions",
    "index_data",
    "financials_quarterly",
    "derived_ratios",
    "macro_series",
    "news_items",
    "newsletters",
    "mf_navs",
    "mf_holdings",
    "transactions",
    "positions",
    "nav_history",
    "decision_log",
    "thesis_tracker",
    "knowledge_base",
    "lessons",
    "calibration",
    "agent_runs",
    "job_runs",
}


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "afund_test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()
    yield connection
    connection.close()


def test_all_tables_exist(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    actual_tables = {row["name"] for row in rows}
    missing = EXPECTED_TABLES - actual_tables
    assert not missing, f"Missing tables: {missing}"
    # Sanity: at least the expected count (allows for incidental extras, never fewer).
    assert len(actual_tables) >= len(EXPECTED_TABLES)


def test_foreign_keys_pragma_on(conn):
    result = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert result == 1


def test_journal_mode_wal(conn):
    result = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert result.lower() == "wal"


def test_daily_prices_unique_constraint(conn):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type) VALUES (1, 'TCS', 'STOCK')"
    )
    conn.execute(
        "INSERT INTO daily_prices (instrument_id, date, close) VALUES (1, '2026-07-01', 100.0)"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO daily_prices (instrument_id, date, close) VALUES (1, '2026-07-01', 101.0)"
        )


def test_instruments_unique_symbol_type(conn):
    conn.execute(
        "INSERT INTO instruments (symbol, instrument_type) VALUES ('INFY', 'STOCK')"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO instruments (symbol, instrument_type) VALUES ('INFY', 'STOCK')"
        )


def test_news_items_url_unique(conn):
    conn.execute(
        "INSERT INTO news_items (url, event_scope, impact) VALUES ('http://example.com/a', 'MICRO', 'POSITIVE')"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO news_items (url, event_scope, impact) VALUES ('http://example.com/a', 'MACRO', 'NEGATIVE')"
        )
