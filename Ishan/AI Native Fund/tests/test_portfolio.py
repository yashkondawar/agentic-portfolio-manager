"""Offline tests for afund.portfolio.ledger + afund.portfolio.nav.

All synthetic data seeded into a temp SQLite DB built from schema.sql. No
network, no LLM calls. Golden numbers are hand-computed in comments next to
each assertion.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from afund.portfolio import ledger, nav

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"

INITIAL_CAPITAL = 1_000_000.0  # matches config/settings.yaml -> portfolio.initial_capital


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


def _seed_instrument(conn, id_, symbol, instrument_type="STOCK", amfi_scheme_code=None):
    conn.execute(
        """
        INSERT INTO instruments (id, symbol, instrument_type, amfi_scheme_code, active)
        VALUES (?, ?, ?, ?, 1)
        """,
        (id_, symbol, instrument_type, amfi_scheme_code),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# ledger: average-cost accounting
# ---------------------------------------------------------------------------


def test_buy_then_buy_then_sell_average_cost_golden(conn):
    _seed_instrument(conn, 1, "INFY")

    # BUY 10@100, fees 10 -> cost = 10*100+10 = 1010; avg = 1010/10 = 101
    ledger.add_transaction(
        conn, trade_date="2026-01-01", symbol_or_instrument_id="INFY",
        side="BUY", qty=10, price=100, fees=10,
    )
    pos = conn.execute("SELECT * FROM positions WHERE instrument_id=1").fetchone()
    assert pos["qty"] == pytest.approx(10)
    assert pos["avg_cost"] == pytest.approx(101.0)

    # BUY 10@120, fees 0 -> new_qty=20; avg = (10*101 + 10*120 + 0)/20 = 2210/20 = 110.5
    ledger.add_transaction(
        conn, trade_date="2026-01-02", symbol_or_instrument_id="INFY",
        side="BUY", qty=10, price=120, fees=0,
    )
    pos = conn.execute("SELECT * FROM positions WHERE instrument_id=1").fetchone()
    assert pos["qty"] == pytest.approx(20)
    assert pos["avg_cost"] == pytest.approx(110.5)

    # SELL 5@130, fees 5 -> realized_pnl = 5*(130-110.5)-5 = 97.5-5 = 92.5; qty=15; avg unchanged
    ledger.add_transaction(
        conn, trade_date="2026-01-03", symbol_or_instrument_id="INFY",
        side="SELL", qty=5, price=130, fees=5,
    )
    pos = conn.execute("SELECT * FROM positions WHERE instrument_id=1").fetchone()
    assert pos["qty"] == pytest.approx(15)
    assert pos["avg_cost"] == pytest.approx(110.5)  # unchanged on SELL
    assert pos["realized_pnl"] == pytest.approx(92.5)

    # cash: initial - 1010 - 1200 + (5*130 - 5) = initial - 2210 + 645 = initial - 1565
    expected_cash = INITIAL_CAPITAL - 1010 - 1200 + 645
    assert ledger.cash_balance(conn) == pytest.approx(expected_cash)


def test_sell_more_than_held_raises(conn):
    _seed_instrument(conn, 1, "INFY")
    ledger.add_transaction(
        conn, trade_date="2026-01-01", symbol_or_instrument_id="INFY",
        side="BUY", qty=10, price=100, fees=0,
    )
    with pytest.raises(ValueError, match="SELL"):
        ledger.add_transaction(
            conn, trade_date="2026-01-02", symbol_or_instrument_id="INFY",
            side="SELL", qty=11, price=100, fees=0,
        )


def test_buy_more_than_cash_raises(conn):
    _seed_instrument(conn, 1, "INFY")
    # cost = 1,000,000,000*1 -> way over cash balance
    with pytest.raises(ValueError, match="BUY"):
        ledger.add_transaction(
            conn, trade_date="2026-01-01", symbol_or_instrument_id="INFY",
            side="BUY", qty=2_000_000, price=1, fees=0,
        )


def test_qty_and_price_must_be_positive(conn):
    _seed_instrument(conn, 1, "INFY")
    with pytest.raises(ValueError):
        ledger.add_transaction(
            conn, trade_date="2026-01-01", symbol_or_instrument_id="INFY",
            side="BUY", qty=0, price=100,
        )
    with pytest.raises(ValueError):
        ledger.add_transaction(
            conn, trade_date="2026-01-01", symbol_or_instrument_id="INFY",
            side="BUY", qty=10, price=0,
        )
    with pytest.raises(ValueError):
        ledger.add_transaction(
            conn, trade_date="2026-01-01", symbol_or_instrument_id="INFY",
            side="BOGUS", qty=10, price=100,
        )


def test_rebuild_positions_idempotent(conn):
    _seed_instrument(conn, 1, "INFY")
    ledger.add_transaction(
        conn, trade_date="2026-01-01", symbol_or_instrument_id="INFY",
        side="BUY", qty=10, price=100, fees=10,
    )
    ledger.add_transaction(
        conn, trade_date="2026-01-02", symbol_or_instrument_id="INFY",
        side="BUY", qty=10, price=120, fees=0,
    )
    before = dict(conn.execute("SELECT * FROM positions WHERE instrument_id=1").fetchone())
    ledger.rebuild_positions(conn)
    ledger.rebuild_positions(conn)
    after = dict(conn.execute("SELECT * FROM positions WHERE instrument_id=1").fetchone())
    assert before["qty"] == after["qty"]
    assert before["avg_cost"] == pytest.approx(after["avg_cost"])
    assert before["realized_pnl"] == pytest.approx(after["realized_pnl"])


def test_cash_balance_no_transactions_equals_initial_capital(conn):
    assert ledger.cash_balance(conn) == pytest.approx(INITIAL_CAPITAL)


def test_add_transaction_by_instrument_id(conn):
    _seed_instrument(conn, 42, "TCS")
    ledger.add_transaction(
        conn, trade_date="2026-01-01", symbol_or_instrument_id=42,
        side="BUY", qty=5, price=100, fees=0,
    )
    pos = conn.execute("SELECT * FROM positions WHERE instrument_id=42").fetchone()
    assert pos["qty"] == pytest.approx(5)


# ---------------------------------------------------------------------------
# nav: pricing + compute_nav
# ---------------------------------------------------------------------------


def _seed_daily_price(conn, instrument_id, date, close):
    conn.execute(
        "INSERT INTO daily_prices (instrument_id, date, close, source) VALUES (?, ?, ?, 'test')",
        (instrument_id, date, close),
    )
    conn.commit()


def _seed_mf_nav(conn, scheme_code, date, nav_value):
    conn.execute(
        "INSERT INTO mf_navs (scheme_code, date, nav, source) VALUES (?, ?, ?, 'test')",
        (scheme_code, date, nav_value),
    )
    conn.commit()


def test_price_on_or_before_stock_carry_forward(conn):
    _seed_instrument(conn, 1, "INFY")
    _seed_daily_price(conn, 1, "2026-01-01", 100.0)
    # No price on 2026-01-02 -> carry forward from 2026-01-01
    assert nav.price_on_or_before(conn, 1, "2026-01-01") == pytest.approx(100.0)
    assert nav.price_on_or_before(conn, 1, "2026-01-02") == pytest.approx(100.0)
    # Before any price exists -> None
    assert nav.price_on_or_before(conn, 1, "2025-12-31") is None


def test_price_on_or_before_mutual_fund(conn):
    _seed_instrument(conn, 2, "SOMEFUND", instrument_type="MUTUAL_FUND", amfi_scheme_code="12345")
    _seed_mf_nav(conn, "12345", "2026-01-01", 50.0)
    _seed_mf_nav(conn, "12345", "2026-01-03", 55.0)
    assert nav.price_on_or_before(conn, 2, "2026-01-02") == pytest.approx(50.0)  # carry-forward
    assert nav.price_on_or_before(conn, 2, "2026-01-03") == pytest.approx(55.0)


def test_price_on_or_before_no_price_at_all_returns_none(conn):
    _seed_instrument(conn, 3, "NOPRICE")
    assert nav.price_on_or_before(conn, 3, "2026-01-01") is None


def test_compute_nav_all_cash_no_positions(conn):
    result = nav.compute_nav(conn, "2026-01-01")
    assert result["market_value"] == pytest.approx(0.0)
    assert result["cash"] == pytest.approx(INITIAL_CAPITAL)
    assert result["total_nav"] == pytest.approx(INITIAL_CAPITAL)
    assert result["daily_return"] is None  # no prior nav_history row

    row = conn.execute("SELECT * FROM nav_history WHERE date='2026-01-01'").fetchone()
    assert row is not None
    assert row["total_nav"] == pytest.approx(INITIAL_CAPITAL)


def test_compute_nav_with_positions_stock_and_mf_carry_forward(conn):
    _seed_instrument(conn, 1, "INFY")
    _seed_instrument(conn, 2, "SOMEFUND", instrument_type="MUTUAL_FUND", amfi_scheme_code="12345")

    # Day 1 prices
    _seed_daily_price(conn, 1, "2026-01-01", 100.0)
    _seed_mf_nav(conn, "12345", "2026-01-01", 50.0)

    # Day 2: only stock price published (mf carries forward from day 1)
    _seed_daily_price(conn, 1, "2026-01-02", 110.0)

    # Buy 10 INFY @100 (fees 0), 20 units of the MF @50 (fees 0) on day 1
    ledger.add_transaction(
        conn, trade_date="2026-01-01", symbol_or_instrument_id="INFY",
        side="BUY", qty=10, price=100, fees=0,
    )
    ledger.add_transaction(
        conn, trade_date="2026-01-01", symbol_or_instrument_id="SOMEFUND",
        side="BUY", qty=20, price=50, fees=0,
    )
    # cash after buys: initial - 1000 - 1000 = initial - 2000
    expected_cash = INITIAL_CAPITAL - 1000 - 1000

    day1 = nav.compute_nav(conn, "2026-01-01")
    # market_value day1 = 10*100 + 20*50 = 1000 + 1000 = 2000
    assert day1["market_value"] == pytest.approx(2000.0)
    assert day1["cash"] == pytest.approx(expected_cash)
    assert day1["total_nav"] == pytest.approx(expected_cash + 2000.0)
    assert day1["total_nav"] == pytest.approx(INITIAL_CAPITAL)  # buys are cash-neutral to total_nav

    day2 = nav.compute_nav(conn, "2026-01-02")
    # day2: INFY priced at 110 (fresh), MF carries forward at 50 (no day-2 nav)
    # market_value = 10*110 + 20*50 = 1100 + 1000 = 2100
    assert day2["market_value"] == pytest.approx(2100.0)
    assert day2["cash"] == pytest.approx(expected_cash)
    expected_total_day2 = expected_cash + 2100.0
    assert day2["total_nav"] == pytest.approx(expected_total_day2)

    # daily_return = (day2_total - day1_total) / day1_total
    expected_return = (expected_total_day2 - INITIAL_CAPITAL) / INITIAL_CAPITAL
    assert day2["daily_return"] == pytest.approx(expected_return)


def test_compute_nav_missing_price_excluded_not_crashed(conn):
    _seed_instrument(conn, 1, "NOPRICE")
    # Force a position without ever inserting a price for it, by hand (bypassing
    # ledger validation, since a BUY would need a price context anyway) — this
    # exercises compute_nav's graceful-degradation path directly.
    conn.execute(
        "INSERT INTO positions (instrument_id, qty, avg_cost, realized_pnl, updated_at) VALUES (1, 5, 100, 0, '2026-01-01')"
    )
    conn.commit()
    result = nav.compute_nav(conn, "2026-01-01")
    assert result["missing_prices"] == [1]
    assert result["market_value"] == pytest.approx(0.0)
    assert result["total_nav"] == pytest.approx(INITIAL_CAPITAL)  # cash only


def test_run_daily_nav_logs_job_run(conn):
    result = nav.run_daily_nav(conn, date="2026-01-01")
    assert result["total_nav"] == pytest.approx(INITIAL_CAPITAL)
    job = conn.execute(
        "SELECT * FROM job_runs WHERE job_name='daily_nav' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert job is not None
    assert job["status"] == "SUCCESS"


def test_run_daily_nav_defaults_to_today(conn, monkeypatch):
    import datetime as dt

    result = nav.run_daily_nav(conn)
    assert result["date"] == dt.date.today().isoformat()
