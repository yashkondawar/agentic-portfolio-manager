"""Offline tests for afund.data.financials.scrape_universe (Phase 12 batch
universe scrape). No real network calls: HTTP is faked via a small stub
session object; the screener.in HTML fixture (screener_infy_snippet.html)
stands in for a fetched company page. Focus areas: resumability (cached-HTML
skip and fresh-derived_ratios skip), per-symbol failure isolation (job_runs
logged, batch continues), and the disk cache being written on a real fetch.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from afund.data import financials as fin

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


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


def _insert_instrument(conn, instrument_id, symbol, instrument_type="STOCK", active=1):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (?, ?, ?, ?)",
        (instrument_id, symbol, instrument_type, active),
    )


class _FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


class _FakeSession:
    """Stand-in for requests.Session: search API returns a canned slug match,
    company page GET returns the fixture HTML. Records every URL hit so
    tests can assert on request counts (e.g. a skipped/cached symbol makes
    zero requests)."""

    def __init__(self, html: str):
        self.html = html
        self.urls_hit: list[str] = []

    def get(self, url, timeout=20, **kwargs):
        self.urls_hit.append(url)
        if "api/company/search" in url:
            return _FakeResponse(200, json_data=[{"id": 1, "name": "Test Co", "url": "/company/TESTCO/consolidated/"}])
        return _FakeResponse(200, text=self.html)


@pytest.fixture()
def fixture_html():
    return (FIXTURES / "screener_infy_snippet.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Resumability: cached HTML skip
# ---------------------------------------------------------------------------

def test_scrape_universe_skips_symbol_with_fresh_cached_html(conn, fixture_html, tmp_path, monkeypatch):
    monkeypatch.setattr(fin, "RAW_DIR", tmp_path / "raw_screener")
    fin.RAW_DIR.mkdir(parents=True, exist_ok=True)

    _insert_instrument(conn, 1, "FRESHCO")
    conn.commit()

    # Pre-populate a cache file with a recent mtime (fresh).
    cache_path = fin._raw_html_path("FRESHCO")
    cache_path.write_text(fixture_html, encoding="utf-8")

    session = _FakeSession(fixture_html)
    summary = fin.scrape_universe(conn, session=session)

    assert summary["skipped_fresh"] == 1
    assert summary["attempted"] == 0
    assert session.urls_hit == []  # no network request at all for a fresh-cached symbol


def test_scrape_universe_refetches_symbol_with_stale_cached_html(conn, fixture_html, tmp_path, monkeypatch):
    monkeypatch.setattr(fin, "RAW_DIR", tmp_path / "raw_screener")
    fin.RAW_DIR.mkdir(parents=True, exist_ok=True)

    _insert_instrument(conn, 1, "STALECO")
    conn.commit()

    cache_path = fin._raw_html_path("STALECO")
    cache_path.write_text(fixture_html, encoding="utf-8")
    # Back-date the file's mtime beyond the freshness window.
    old_time = (dt.datetime.now() - dt.timedelta(days=40)).timestamp()
    import os

    os.utime(cache_path, (old_time, old_time))

    session = _FakeSession(fixture_html)
    summary = fin.scrape_universe(conn, session=session)

    assert summary["attempted"] == 1
    assert summary["parsed_ok"] == 1
    assert len(session.urls_hit) >= 1  # a real request was made


# ---------------------------------------------------------------------------
# Resumability: fresh derived_ratios skip (no cached HTML needed)
# ---------------------------------------------------------------------------

def test_scrape_universe_skips_symbol_with_fresh_derived_ratios(conn, fixture_html, tmp_path, monkeypatch):
    monkeypatch.setattr(fin, "RAW_DIR", tmp_path / "raw_screener")
    fin.RAW_DIR.mkdir(parents=True, exist_ok=True)

    _insert_instrument(conn, 1, "DBFRESH")
    conn.execute(
        "INSERT INTO derived_ratios (instrument_id, as_of_date, metric_name, metric_value) VALUES (?, ?, ?, ?)",
        (1, dt.date.today().isoformat(), "stock_p_e", 25.0),
    )
    conn.commit()

    session = _FakeSession(fixture_html)
    summary = fin.scrape_universe(conn, session=session)

    assert summary["skipped_fresh"] == 1
    assert summary["attempted"] == 0
    assert session.urls_hit == []


def test_scrape_universe_does_not_skip_stale_derived_ratios(conn, fixture_html, tmp_path, monkeypatch):
    monkeypatch.setattr(fin, "RAW_DIR", tmp_path / "raw_screener")
    fin.RAW_DIR.mkdir(parents=True, exist_ok=True)

    _insert_instrument(conn, 1, "DBSTALE")
    old_date = (dt.date.today() - dt.timedelta(days=90)).isoformat()
    conn.execute(
        "INSERT INTO derived_ratios (instrument_id, as_of_date, metric_name, metric_value) VALUES (?, ?, ?, ?)",
        (1, old_date, "stock_p_e", 25.0),
    )
    conn.commit()

    session = _FakeSession(fixture_html)
    summary = fin.scrape_universe(conn, session=session)

    assert summary["attempted"] == 1
    assert summary["parsed_ok"] == 1


# ---------------------------------------------------------------------------
# Per-symbol failure isolation
# ---------------------------------------------------------------------------

def test_scrape_universe_logs_failure_and_continues_batch(conn, fixture_html, tmp_path, monkeypatch):
    monkeypatch.setattr(fin, "RAW_DIR", tmp_path / "raw_screener")
    fin.RAW_DIR.mkdir(parents=True, exist_ok=True)

    _insert_instrument(conn, 1, "NOMATCH")
    _insert_instrument(conn, 2, "GOODCO")
    conn.commit()

    class _PartialFailSession(_FakeSession):
        def get(self, url, timeout=20, **kwargs):
            self.urls_hit.append(url)
            if "api/company/search" in url:
                if "NOMATCH" in url:
                    return _FakeResponse(200, json_data=[])  # no match -> resolve_screener_slug returns None
                return _FakeResponse(200, json_data=[{"id": 1, "name": "Good Co", "url": "/company/GOODCO/consolidated/"}])
            return _FakeResponse(200, text=self.html)

    session = _PartialFailSession(fixture_html)
    summary = fin.scrape_universe(conn, session=session)

    assert summary["attempted"] == 2
    assert summary["parsed_ok"] == 1
    assert summary["failed"] == 1
    assert summary["failures"][0]["symbol"] == "NOMATCH"
    assert "no screener.in match" in summary["failures"][0]["reason"]

    # job_runs must carry a FAILED row for the batch job naming the symbol,
    # without the batch itself raising or aborting (GOODCO still parsed_ok).
    failed_rows = conn.execute(
        "SELECT * FROM job_runs WHERE job_name = 'financials_universe' AND status = 'FAILED'"
    ).fetchall()
    assert any("NOMATCH" in (r["error"] or "") for r in failed_rows)


# ---------------------------------------------------------------------------
# Disk cache is written on a real fetch
# ---------------------------------------------------------------------------

def test_scrape_universe_writes_html_cache_on_fetch(conn, fixture_html, tmp_path, monkeypatch):
    monkeypatch.setattr(fin, "RAW_DIR", tmp_path / "raw_screener")
    fin.RAW_DIR.mkdir(parents=True, exist_ok=True)

    _insert_instrument(conn, 1, "CACHEME")
    conn.commit()

    session = _FakeSession(fixture_html)
    fin.scrape_universe(conn, session=session)

    cache_path = fin._raw_html_path("CACHEME")
    assert cache_path.exists()
    assert "Sales" in cache_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# --limit flag
# ---------------------------------------------------------------------------

def test_scrape_universe_respects_limit(conn, fixture_html, tmp_path, monkeypatch):
    monkeypatch.setattr(fin, "RAW_DIR", tmp_path / "raw_screener")
    fin.RAW_DIR.mkdir(parents=True, exist_ok=True)

    for i in range(1, 6):
        _insert_instrument(conn, i, f"SYM{i}")
    conn.commit()

    session = _FakeSession(fixture_html)
    summary = fin.scrape_universe(conn, session=session, limit=2)

    assert summary["total_universe"] == 5
    assert summary["attempted"] + summary["skipped_fresh"] == 2


# ---------------------------------------------------------------------------
# Parsed data actually lands in financials_quarterly / derived_ratios
# ---------------------------------------------------------------------------

def test_scrape_universe_upserts_derived_ratios_and_financials(conn, fixture_html, tmp_path, monkeypatch):
    monkeypatch.setattr(fin, "RAW_DIR", tmp_path / "raw_screener")
    fin.RAW_DIR.mkdir(parents=True, exist_ok=True)

    _insert_instrument(conn, 1, "PARSEME")
    conn.commit()

    session = _FakeSession(fixture_html)
    summary = fin.scrape_universe(conn, session=session)
    assert summary["parsed_ok"] == 1

    ratios = conn.execute(
        "SELECT metric_name, metric_value FROM derived_ratios WHERE instrument_id = 1"
    ).fetchall()
    assert any(r["metric_name"] == "stock_p_e" for r in ratios)

    fin_rows = conn.execute(
        "SELECT * FROM financials_quarterly WHERE instrument_id = 1"
    ).fetchall()
    assert len(fin_rows) == 13
