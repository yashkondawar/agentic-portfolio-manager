"""Offline tests for afund.derive.* — returns, regime, ratios, technicals.

All synthetic data, seeded into a temp SQLite DB built from schema.sql. No
network, no dependency on the real afund.db data.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from afund.derive import ratios, regime, returns, technicals

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"


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


def _seed_index_series(conn, index_name: str, start: dt.date, days: int, start_price: float, daily_growth: float, pe_base: float = 20.0):
    """Insert `days` daily closes (every calendar day, simple for test purposes)
    starting at start_price and compounding by daily_growth each day."""
    price = start_price
    for i in range(days):
        date = (start + dt.timedelta(days=i)).isoformat()
        pe = pe_base + (i % 7) - 3  # oscillate a bit so percentile/z-score aren't degenerate
        conn.execute(
            "INSERT INTO index_data (index_name, date, close, pe, pb, div_yield) VALUES (?, ?, ?, ?, ?, ?)",
            (index_name, date, price, pe, 3.0, 1.2),
        )
        price *= (1 + daily_growth)
    conn.commit()


def _seed_instrument_prices(conn, instrument_id: int, start: dt.date, days: int, start_price: float, daily_growth: float):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (?, 'TESTSTOCK', 'STOCK', 1)",
        (instrument_id,),
    )
    price = start_price
    for i in range(days):
        date = (start + dt.timedelta(days=i)).isoformat()
        conn.execute(
            "INSERT INTO daily_prices (instrument_id, date, close) VALUES (?, ?, ?)",
            (instrument_id, date, price),
        )
        price *= (1 + daily_growth)
    conn.commit()


# --- returns.py -------------------------------------------------------------

def test_trailing_return_and_cagr_on_flat_index(conn):
    start = dt.date(2020, 1, 1)
    # Flat price (no growth) over 6 years -> 1y return ~0, 5y CAGR ~0
    _seed_index_series(conn, "TEST_IDX", start, days=365 * 6, start_price=100.0, daily_growth=0.0)
    as_of = (start + dt.timedelta(days=365 * 6 - 1)).isoformat()

    r1y = returns.trailing_return(conn, index_name="TEST_IDX", years=1.0, as_of=as_of)
    c5y = returns.cagr(conn, index_name="TEST_IDX", years=5.0, as_of=as_of)
    assert r1y == pytest.approx(0.0, abs=1e-9)
    assert c5y == pytest.approx(0.0, abs=1e-9)


def test_trailing_return_insufficient_history_returns_none(conn):
    start = dt.date(2026, 1, 1)
    _seed_index_series(conn, "SHORT_IDX", start, days=30, start_price=100.0, daily_growth=0.0)
    as_of = (start + dt.timedelta(days=29)).isoformat()
    r1y = returns.trailing_return(conn, index_name="SHORT_IDX", years=1.0, as_of=as_of)
    assert r1y is None


def test_history_span_years(conn):
    start = dt.date(2020, 1, 1)
    _seed_index_series(conn, "SPAN_IDX", start, days=365 * 2, start_price=100.0, daily_growth=0.0)
    span = returns.history_span_years(conn, index_name="SPAN_IDX")
    assert 1.9 < span < 2.1


def test_daily_returns_length(conn):
    start = dt.date(2026, 1, 1)
    _seed_index_series(conn, "DR_IDX", start, days=10, start_price=100.0, daily_growth=0.01)
    dr = returns.daily_returns(conn, index_name="DR_IDX")
    assert len(dr) == 9
    assert dr[0][1] == pytest.approx(0.01, abs=1e-6)


# --- regime.py ---------------------------------------------------------------

def test_evaluate_regime_euphoria_signal(conn):
    start = dt.date(2025, 1, 1)
    # ~110% growth over the year -> euphoria_avoid should trigger
    days = 366
    daily_growth = (2.10) ** (1 / days) - 1
    _seed_index_series(conn, "EUPHORIA_IDX", start, days=days, start_price=100.0, daily_growth=daily_growth)
    as_of = (start + dt.timedelta(days=days - 1)).isoformat()

    result = regime.evaluate_regime(conn, "EUPHORIA_IDX", as_of=as_of)
    assert "euphoria_avoid" in result["signals"]
    assert result["ret_1y"] > 1.0


def test_evaluate_regime_panic_signal(conn):
    start = dt.date(2025, 1, 1)
    days = 366
    # -50% over the year -> panic_buy should trigger
    daily_growth = (0.50) ** (1 / days) - 1
    _seed_index_series(conn, "PANIC_IDX", start, days=days, start_price=100.0, daily_growth=daily_growth)
    as_of = (start + dt.timedelta(days=days - 1)).isoformat()

    result = regime.evaluate_regime(conn, "PANIC_IDX", as_of=as_of)
    assert "panic_buy" in result["signals"]
    assert result["ret_1y"] < -0.4


def test_evaluate_regime_insufficient_history_flag(conn):
    start = dt.date(2026, 6, 1)
    _seed_index_series(conn, "NEW_IDX", start, days=10, start_price=100.0, daily_growth=0.0)
    as_of = (start + dt.timedelta(days=9)).isoformat()

    result = regime.evaluate_regime(conn, "NEW_IDX", as_of=as_of)
    assert result["insufficient_history"] is True
    assert result["signals"] == []


def test_evaluate_regime_unknown_index_degrades_gracefully(conn):
    result = regime.evaluate_regime(conn, "DOES_NOT_EXIST")
    assert result["pe"] is None
    assert result["ret_1y"] is None
    assert result["signals"] == []
    assert result["insufficient_history"] is True


# --- ratios.py -----------------------------------------------------------

def test_latest_quarter_ratios_yoy_and_margins(conn):
    conn.execute("INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (1, 'TCS', 'STOCK', 1)")
    quarters = [
        ("2025-03-31", 1000.0, 200.0, 150.0, 10.0),
        ("2025-06-30", 1050.0, 210.0, 155.0, 10.5),
        ("2025-09-30", 1100.0, 220.0, 160.0, 11.0),
        ("2025-12-31", 1150.0, 230.0, 165.0, 11.5),
        ("2026-03-31", 1200.0, 250.0, 180.0, 12.0),  # same quarter as row 0, 1y later
    ]
    for period_end, revenue, op_profit, net_profit, eps in quarters:
        conn.execute(
            """
            INSERT INTO financials_quarterly
                (instrument_id, period_end, statement_type, revenue, operating_profit, net_profit, eps)
            VALUES (1, ?, 'consolidated', ?, ?, ?, ?)
            """,
            (period_end, revenue, op_profit, net_profit, eps),
        )
    conn.commit()

    result = ratios.latest_quarter_ratios(conn, instrument_id=1)
    assert result["period_end"] == "2026-03-31"
    assert result["revenue_yoy"] == pytest.approx((1200 - 1000) / 1000)
    assert result["net_profit_yoy"] == pytest.approx((180 - 150) / 150)
    assert result["operating_margin"] == pytest.approx(250 / 1200)
    assert result["net_margin"] == pytest.approx(180 / 1200)


def test_latest_quarter_ratios_no_data_degrades_gracefully(conn):
    conn.execute("INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (1, 'TCS', 'STOCK', 1)")
    conn.commit()
    result = ratios.latest_quarter_ratios(conn, instrument_id=1)
    assert result["period_end"] is None
    assert result["revenue_yoy"] is None


def test_yoy_growth_zero_base_returns_none():
    assert ratios.yoy_growth(100.0, 0.0) is None
    assert ratios.yoy_growth(None, 100.0) is None


# --- technicals.py ---------------------------------------------------------

def test_compute_technicals_full_history(conn):
    start = dt.date(2024, 1, 1)
    _seed_instrument_prices(conn, instrument_id=1, start=start, days=300, start_price=100.0, daily_growth=0.001)

    result = technicals.compute_technicals(conn, instrument_id=1)
    assert result["dma_50"] is not None
    assert result["dma_200"] is not None
    assert result["rsi_14"] is not None
    assert 0 <= result["rsi_14"] <= 100
    assert result["high_52w"] is not None
    assert result["low_52w"] is not None
    # Monotonically increasing price series -> last close is the 52w high
    assert result["pct_from_52w_high"] == pytest.approx(0.0, abs=1e-9)
    assert result["pct_from_52w_low"] > 0


def test_compute_technicals_thin_history_degrades_gracefully(conn):
    start = dt.date(2026, 6, 1)
    _seed_instrument_prices(conn, instrument_id=1, start=start, days=5, start_price=100.0, daily_growth=0.0)

    result = technicals.compute_technicals(conn, instrument_id=1)
    assert result["last_close"] == pytest.approx(100.0, rel=0.01)
    assert result["dma_50"] is None
    assert result["dma_200"] is None
    assert result["rsi_14"] is None


def test_compute_technicals_no_data_returns_all_none(conn):
    conn.execute("INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (1, 'EMPTY', 'STOCK', 1)")
    conn.commit()
    result = technicals.compute_technicals(conn, instrument_id=1)
    assert result["last_close"] is None
    assert result["dma_50"] is None
