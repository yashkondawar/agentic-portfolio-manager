"""Offline tests for afund.portfolio.risk.

All synthetic data seeded into a temp SQLite DB built from schema.sql. No
network, no LLM calls. Golden numbers hand-computed in comments — the
deterministic alternating +/-1% NAV series is chosen specifically because
its returns have an exact, simple closed form (mean 0, all magnitudes
0.01) so every downstream stat can be verified by hand.
"""
from __future__ import annotations

import math
import sqlite3
import statistics
from pathlib import Path

import pytest

from afund.portfolio import risk

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"

BENCHMARK = "NIFTY 50"  # matches config/settings.yaml -> portfolio.benchmark


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


def _dates(n, start="2026-01-01"):
    import datetime as dt

    d0 = dt.date.fromisoformat(start)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]


def _seed_nav_history(conn, dates, navs):
    prev_total = None
    for date, total in zip(dates, navs):
        daily_return = None
        if prev_total:
            daily_return = (total - prev_total) / prev_total
        conn.execute(
            "INSERT INTO nav_history (date, market_value, cash, total_nav, daily_return) VALUES (?, 0, ?, ?, ?)",
            (date, total, total, daily_return),
        )
        prev_total = total
    conn.commit()


def _seed_index(conn, index_name, dates, closes):
    for date, close in zip(dates, closes):
        conn.execute(
            "INSERT INTO index_data (index_name, date, close) VALUES (?, ?, ?)",
            (index_name, date, close),
        )
    conn.commit()


def _alternating_returns(n):
    """[+0.01, -0.01, +0.01, -0.01, ...] length n."""
    return [0.01 if i % 2 == 0 else -0.01 for i in range(n)]


def _navs_from_returns(nav0, returns):
    navs = [nav0]
    for r in returns:
        navs.append(navs[-1] * (1 + r))
    return navs


# ---------------------------------------------------------------------------
# SD / VaR / drawdown on a deterministic alternating +/-1% series
# ---------------------------------------------------------------------------


def test_sd_var_drawdown_alternating_series_golden(conn):
    n_returns = 40
    returns = _alternating_returns(n_returns)  # 20x +1%, 20x -1%, mean=0
    navs = _navs_from_returns(1_000_000.0, returns)
    dates = _dates(len(navs))
    _seed_nav_history(conn, dates, navs)

    snap = risk.snapshot(conn)

    assert snap["observations"] == n_returns
    assert snap["insufficient_history"] is False  # 40 >= MIN_OBSERVATIONS(30)

    # sd_annualized: statistics.stdev is the SAMPLE stdev (n-1 denominator).
    # For 40 values alternating exactly +/-0.01 with mean 0:
    #   stdev = sqrt(sum((x-0)^2)/(n-1)) = sqrt(40*0.0001/39) = 0.01*sqrt(40/39)
    expected_sd_daily = 0.01 * math.sqrt(40 / 39)
    expected_sd_annualized = expected_sd_daily * math.sqrt(252)
    assert snap["sd_annualized"] == pytest.approx(expected_sd_annualized)

    # VaR 95% 1d, nearest-rank/floor method: idx = floor(0.05*40) = 2.
    # sorted_returns = [-0.01]*20 + [0.01]*20 -> sorted_returns[2] == -0.01
    # var_95_1d_pct = -(-0.01) = 0.01 (positive loss fraction)
    assert snap["var_95_1d_pct"] == pytest.approx(0.01)
    assert snap["var_95_1d_value"] == pytest.approx(0.01 * navs[-1])

    # max_drawdown_pct: computed by walking the NAV path and tracking the
    # running peak; since consecutive pairs (+1%,-1%) multiply to 0.9999 < 1,
    # the series drifts slightly down after every pair, so the max drawdown
    # is realized at the final trough. Verified independently via a plain
    # peak-tracking loop over the same `navs` list (see nav.py's docstring
    # for the identical algorithm) -> -1.1879...%
    peak = navs[0]
    max_dd = 0.0
    for v in navs:
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < max_dd:
            max_dd = dd
    assert snap["max_drawdown_pct"] == pytest.approx(max_dd * 100.0)
    assert snap["max_drawdown_pct"] < 0  # sanity: a drawdown is negative


def test_insufficient_history_flag_below_min_observations(conn):
    # Only 10 returns (< MIN_OBSERVATIONS=30) -> sd/VaR/beta/alpha all None,
    # but the metric that doesn't need a long window (max_drawdown) still computes.
    n_returns = 10
    returns = _alternating_returns(n_returns)
    navs = _navs_from_returns(1_000_000.0, returns)
    dates = _dates(len(navs))
    _seed_nav_history(conn, dates, navs)

    snap = risk.snapshot(conn)
    assert snap["observations"] == n_returns
    assert snap["insufficient_history"] is True
    assert snap["var_95_1d_pct"] is None  # needs >= 30 observations
    assert snap["beta"] is None
    assert snap["jensens_alpha_annualized"] is None
    # sd_annualized only needs >=2 points, so it's still computed.
    assert snap["sd_annualized"] is not None
    # max_drawdown only needs >=2 nav points too.
    assert snap["max_drawdown_pct"] is not None


def test_snapshot_no_nav_history_all_none(conn):
    snap = risk.snapshot(conn)
    assert snap["observations"] == 0
    assert snap["insufficient_history"] is True
    assert snap["sd_annualized"] is None
    assert snap["var_95_1d_pct"] is None
    assert snap["max_drawdown_pct"] is None
    assert snap["beta"] is None
    assert snap["jensens_alpha_annualized"] is None
    assert snap["positions_detail"] == []


# ---------------------------------------------------------------------------
# beta / Jensen's alpha
# ---------------------------------------------------------------------------


def test_beta_one_alpha_zero_when_portfolio_equals_benchmark(conn):
    n_returns = 40
    returns = _alternating_returns(n_returns)
    navs = _navs_from_returns(1_000_000.0, returns)
    dates = _dates(len(navs))
    _seed_nav_history(conn, dates, navs)

    # Benchmark index closes follow the EXACT same return series (rebased to
    # an arbitrary starting level, e.g. 20000) so Rp == Rm on every overlapping day.
    index_closes = _navs_from_returns(20_000.0, returns)
    _seed_index(conn, BENCHMARK, dates, index_closes)

    snap = risk.snapshot(conn)

    # When Rp == Rm for every observation: Cov(Rp,Rm) == Var(Rm) -> beta == 1.0
    # exactly, and mean_rp == mean_rm so alpha_daily = mean_rp - (rf + 1*(mean_rm-rf))
    # = mean_rp - mean_rm = 0 exactly (rf terms cancel when beta==1).
    assert snap["beta"] == pytest.approx(1.0)
    assert snap["jensens_alpha_annualized"] == pytest.approx(0.0, abs=1e-9)


def test_beta_none_when_insufficient_overlap(conn):
    n_returns = 10  # below MIN_OBSERVATIONS
    returns = _alternating_returns(n_returns)
    navs = _navs_from_returns(1_000_000.0, returns)
    dates = _dates(len(navs))
    _seed_nav_history(conn, dates, navs)
    index_closes = _navs_from_returns(20_000.0, returns)
    _seed_index(conn, BENCHMARK, dates, index_closes)

    snap = risk.snapshot(conn)
    assert snap["beta"] is None
    assert snap["jensens_alpha_annualized"] is None


# ---------------------------------------------------------------------------
# concentration + positions_detail
# ---------------------------------------------------------------------------


def _seed_instrument(conn, id_, symbol, instrument_type="STOCK"):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (?, ?, ?, 1)",
        (id_, symbol, instrument_type),
    )
    conn.commit()


def _seed_position(conn, instrument_id, qty, avg_cost, realized_pnl=0.0):
    conn.execute(
        "INSERT INTO positions (instrument_id, qty, avg_cost, realized_pnl, updated_at) VALUES (?, ?, ?, ?, '2026-02-10')",
        (instrument_id, qty, avg_cost, realized_pnl),
    )
    conn.commit()


def _seed_daily_price(conn, instrument_id, date, close):
    conn.execute(
        "INSERT INTO daily_prices (instrument_id, date, close, source) VALUES (?, ?, ?, 'test')",
        (instrument_id, date, close),
    )
    conn.commit()


def test_concentration_and_positions_detail(conn):
    _seed_instrument(conn, 1, "INFY")
    _seed_instrument(conn, 2, "TCS")
    _seed_daily_price(conn, 1, "2026-02-10", 150.0)  # mv = 10*150 = 1500
    _seed_daily_price(conn, 2, "2026-02-10", 100.0)  # mv = 10*100 = 1000
    _seed_position(conn, 1, qty=10, avg_cost=100.0)   # unrealized = 10*(150-100)=500
    _seed_position(conn, 2, qty=10, avg_cost=120.0)   # unrealized = 10*(100-120)=-200

    # minimal nav_history so as_of resolves without needing a full snapshot
    conn.execute(
        "INSERT INTO nav_history (date, market_value, cash, total_nav, daily_return) VALUES ('2026-02-10', 2500, 997500, 1000000, NULL)"
    )
    conn.commit()

    snap = risk.snapshot(conn, as_of="2026-02-10")

    total_mv = 1500.0 + 1000.0
    conc = snap["concentration"]
    assert conc["position_count"] == 2
    # weights: 1500/2500=0.6, 1000/2500=0.4 -> hhi = 0.6^2+0.4^2 = 0.36+0.16=0.52
    assert conc["hhi"] == pytest.approx(0.52)
    assert conc["top5_weight_pct"] == pytest.approx(100.0)  # only 2 positions, both counted

    detail_by_symbol = {d["symbol"]: d for d in snap["positions_detail"]}
    assert detail_by_symbol["INFY"]["market_value"] == pytest.approx(1500.0)
    assert detail_by_symbol["INFY"]["weight_pct"] == pytest.approx(60.0)
    assert detail_by_symbol["INFY"]["unrealized_pnl"] == pytest.approx(500.0)
    assert detail_by_symbol["INFY"]["unrealized_pnl_pct"] == pytest.approx(50.0)

    assert detail_by_symbol["TCS"]["market_value"] == pytest.approx(1000.0)
    assert detail_by_symbol["TCS"]["weight_pct"] == pytest.approx(40.0)
    assert detail_by_symbol["TCS"]["unrealized_pnl"] == pytest.approx(-200.0)
    # unrealized_pnl_pct = (last_price - avg_cost) / avg_cost * 100 = (100-120)/120*100 = -16.667%
    assert detail_by_symbol["TCS"]["unrealized_pnl_pct"] == pytest.approx((100 - 120) / 120 * 100)


def test_concentration_empty_when_no_positions(conn):
    snap = risk.snapshot(conn)
    assert snap["concentration"]["hhi"] is None
    assert snap["concentration"]["top5_weight_pct"] is None
    assert snap["concentration"]["position_count"] == 0
    assert snap["positions_detail"] == []
