"""Offline tests for afund.data.fii_dii.parse_fii_dii_rows — the confirmed
live api/fiidiiTradeReact JSON shape ({"category": "DII"|"FII/FPI", "date":
"DD-Mon-YYYY", buy/sell/netValue as strings). No network."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from afund.data.fii_dii import FiiDiiPipeline, parse_fii_dii_rows

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"

# Verbatim live response shape from 2026-07 (values altered).
LIVE_SHAPE = [
    {"category": "DII", "date": "03-Jul-2026", "buyValue": "12,113.34",
     "sellValue": "14,067.23", "netValue": "-1,953.89"},
    {"category": "FII/FPI", "date": "03-Jul-2026", "buyValue": "18,406.75",
     "sellValue": "17,051.42", "netValue": "1,355.33"},
]


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


def test_parses_live_shape():
    parsed = parse_fii_dii_rows(LIVE_SHAPE)
    assert ("DII_NET", "2026-07-03", -1953.89) in parsed
    assert ("FII_NET", "2026-07-03", 1355.33) in parsed
    assert len(parsed) == 2


def test_category_variants_and_unknowns():
    rows = [
        {"category": "FII", "date": "02-Jul-2026", "netValue": "100.0"},
        {"category": "FPI", "date": "02-Jul-2026", "netValue": "200.0"},
        {"category": "MF", "date": "02-Jul-2026", "netValue": "300.0"},  # unknown -> skipped
    ]
    parsed = parse_fii_dii_rows(rows)
    assert [p[0] for p in parsed] == ["FII_NET", "FII_NET"]


def test_skips_malformed_rows():
    rows = [
        {"category": "DII", "date": "bad-date", "netValue": "1.0"},
        {"category": "DII", "date": "01-Jul-2026", "netValue": "not-a-number"},
        {"category": "DII", "date": "01-Jul-2026"},  # no netValue
        {"category": "DII", "date": "01-Jul-2026", "netValue": "-42.5"},
    ]
    assert parse_fii_dii_rows(rows) == [("DII_NET", "2026-07-01", -42.5)]


def test_upsert_idempotent_reruns_same_day(conn):
    pipeline = FiiDiiPipeline(conn=conn)
    parsed = parse_fii_dii_rows(LIVE_SHAPE)
    pipeline.upsert(parsed)
    pipeline.upsert(parsed)  # daily job re-run: no duplicates

    stored = conn.execute(
        "SELECT series_code, date, value FROM macro_series ORDER BY series_code"
    ).fetchall()
    assert len(stored) == 2
    assert stored[0]["series_code"] == "DII_NET"
    assert stored[0]["value"] == pytest.approx(-1953.89)
    assert stored[1]["series_code"] == "FII_NET"
    assert stored[1]["value"] == pytest.approx(1355.33)
