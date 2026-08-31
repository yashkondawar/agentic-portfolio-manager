"""Offline tests for macro_rbi.import_macro_csv() (and macro_mospi's thin
wrapper). No network — writes to a temp SQLite DB built from schema.sql."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from afund.data.macro_mospi import import_macro_csv as import_macro_csv_mospi
from afund.data.macro_rbi import import_macro_csv as import_macro_csv_rbi

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"
EXAMPLE_CSV = REPO_ROOT / "data" / "manual" / "example_repo_rate.csv"


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "afund_test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()
    yield connection
    connection.close()


def test_import_macro_csv_rbi(conn):
    rows_written = import_macro_csv_rbi(EXAMPLE_CSV, series_code="REPO_RATE", source="RBI", conn=conn)
    assert rows_written == 11

    stored = conn.execute(
        "SELECT date, value FROM macro_series WHERE series_code = 'REPO_RATE' ORDER BY date"
    ).fetchall()
    assert len(stored) == 11
    assert stored[0]["date"] == "2025-08-01"
    assert stored[0]["value"] == 6.50
    assert stored[-1]["date"] == "2026-06-01"
    assert stored[-1]["value"] == 5.75


def test_import_macro_csv_idempotent(conn):
    import_macro_csv_rbi(EXAMPLE_CSV, series_code="REPO_RATE", source="RBI", conn=conn)
    second_run_rows = import_macro_csv_rbi(EXAMPLE_CSV, series_code="REPO_RATE", source="RBI", conn=conn)
    assert second_run_rows == 0


def test_import_macro_csv_mospi_wrapper_sets_source(conn):
    rows_written = import_macro_csv_mospi(EXAMPLE_CSV, series_code="REPO_RATE_TEST", conn=conn)
    assert rows_written == 11
    row = conn.execute(
        "SELECT source FROM macro_series WHERE series_code = 'REPO_RATE_TEST' LIMIT 1"
    ).fetchone()
    assert row["source"] == "MOSPI"


def test_import_macro_csv_skips_malformed_rows(conn, tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("date,value\n2026-01-01,6.5\nnot-a-date,\n2026-02-01,notanumber\n2026-03-01,6.25\n", encoding="utf-8")
    rows_written = import_macro_csv_rbi(bad_csv, series_code="TEST_SERIES", conn=conn)
    assert rows_written == 2
