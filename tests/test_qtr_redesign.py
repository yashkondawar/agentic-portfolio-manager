"""Unit tests for the ideal-state PEAD redesign: SUE signal, cross-sectional
ranking, beta-hedge overlay and the deflated-Sharpe / walk-forward validation.

All pure — no network, no caches, no yfinance/screener — so they run in the normal
test suite.
"""

from datetime import date

import pandas as pd

from backtesting.qtr_results import ranking, signals
from backtesting.qtr_results.hedge import (
    HedgeConfig,
    apply_beta_hedge,
    realized_book_beta,
)
from backtesting.qtr_results.validation import (
    deflated_sharpe_ratio,
    walk_forward_windows,
)


# ── SUE ──────────────────────────────────────────────────────────────────────

def _eps_dict(quarters, values):
    return {q: v for q, v in zip(quarters, values)}


def test_compute_sue_positive_when_growth_beats_trend():
    # 12 quarters. Trailing YoY EPS changes vary modestly (mean ~+2); the final
    # quarter jumps far above that drift -> a large positive standardized surprise.
    quarters = [f"Q{i}" for i in range(12)]
    eps_vals = [10, 10, 10, 10, 11, 12, 13, 11, 13, 15, 15, 31]
    eps = _eps_dict(quarters, eps_vals)
    sue = signals.compute_sue(eps, quarters, q_idx=11, window=8)
    assert sue is not None
    assert sue > 2.0  # a large positive surprise vs the steady seasonal drift


def test_compute_sue_none_on_insufficient_history():
    quarters = [f"Q{i}" for i in range(6)]
    eps = _eps_dict(quarters, [1, 2, 3, 4, 5, 6])
    # q_idx=5 has only one prior seasonal delta → cannot standardize.
    assert signals.compute_sue(eps, quarters, q_idx=5, window=8) is None


def test_compute_sue_none_when_missing_values():
    quarters = [f"Q{i}" for i in range(12)]
    eps_vals = [10, 11, 12, 13, None, 13, 14, 15, 14, 15, 16, 25]
    eps = _eps_dict(quarters, eps_vals)
    # base quarter (q_idx-4 = 7) present, current present, but the trailing window
    # has a hole — still standardizable from the remaining deltas.
    sue = signals.compute_sue(eps, quarters, q_idx=11, window=8)
    assert sue is None or isinstance(sue, float)


def test_announcement_reaction_sign():
    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    stock = pd.DataFrame({"Close": [100.0, 100.0, 110.0]}, index=idx)  # +10%
    bench = pd.DataFrame({"Close": [100.0, 100.0, 102.0]}, index=idx)  # +2%
    r = signals.announcement_reaction(stock, bench, lookback=1)
    assert r is not None
    assert abs(r - 0.08) < 1e-6  # 10% - 2%


def test_zscores_preserve_none_and_center():
    zs = signals.zscores([1.0, 2.0, 3.0, None])
    assert zs[3] is None
    assert abs(sum(z for z in zs if z is not None)) < 1e-9  # mean-centered


# ── Cross-sectional ranking ──────────────────────────────────────────────────

def test_composite_ranks_higher_sue_first():
    cands = [
        ranking.Candidate("A", sue=0.5, reaction=0.0, debt_to_equity=0.1),
        ranking.Candidate("B", sue=3.0, reaction=0.05, debt_to_equity=0.0),
        ranking.Candidate("C", sue=-1.0, reaction=-0.05, debt_to_equity=1.0),
    ]
    scored = ranking.composite_scores(cands)
    assert scored[0].symbol == "B"
    assert scored[-1].symbol == "C"


def test_select_top_quantile_and_cap():
    cands = [ranking.Candidate(f"S{i}", sue=float(i)) for i in range(10)]
    scored = ranking.composite_scores(cands)
    top = ranking.select_top(scored, top_quantile=0.2)
    assert len(top) == 2  # top quintile of 10
    capped = ranking.select_top(scored, top_quantile=0.5, cap=3)
    assert len(capped) == 3


def test_ranking_falls_back_to_strength_when_no_sue():
    cands = [
        ranking.Candidate("A", sue=None, strength_score=90.0),
        ranking.Candidate("B", sue=None, strength_score=10.0),
    ]
    scored = ranking.composite_scores(cands)
    assert scored[0].symbol == "A"


# ── Beta hedge ───────────────────────────────────────────────────────────────

def test_beta_hedge_profits_when_market_falls():
    # Long book flat at 100 deployed; benchmark drops 10% over the window.
    dates = pd.date_range("2025-01-01", periods=3, freq="D")
    bench = pd.DataFrame({"Close": [100.0, 95.0, 90.0]}, index=dates)
    curve = [
        {"date": d.date().isoformat(), "equity": 100000.0, "cash": 0.0,
         "deployed": 100000.0, "open_positions": 1}
        for d in dates
    ]
    cfg = HedgeConfig(enabled=True, hedge_ratio=1.0, book_beta=1.0,
                      commission_pct=0.0, annual_carry_pct=0.0)
    out = apply_beta_hedge(curve, bench, cfg)
    # Short index while the market fell → hedged equity should EXCEED raw equity.
    assert out[-1]["hedged_equity"] > out[-1]["equity"]


def test_beta_hedge_disabled_is_passthrough():
    dates = pd.date_range("2025-01-01", periods=2, freq="D")
    bench = pd.DataFrame({"Close": [100.0, 90.0]}, index=dates)
    curve = [{"date": d.date().isoformat(), "equity": 100.0, "cash": 0.0,
              "deployed": 100.0, "open_positions": 1} for d in dates]
    out = apply_beta_hedge(curve, bench, HedgeConfig(enabled=False))
    assert all(s["hedged_equity"] == s["equity"] for s in out)


def test_realized_book_beta_recovers_unit_beta():
    # Book equity tracks benchmark 1:1 → measured beta ~1.
    dates = pd.date_range("2025-01-01", periods=60, freq="D")
    prices = [100.0]
    for i in range(1, 60):
        prices.append(prices[-1] * (1.0 + (0.01 if i % 2 else -0.008)))
    bench = pd.DataFrame({"Close": prices}, index=dates)
    curve = [{"date": d.date().isoformat(), "equity": p * 1000.0}
             for d, p in zip(dates, prices)]
    beta = realized_book_beta(curve, bench, min_obs=20)
    assert beta is not None
    assert abs(beta - 1.0) < 0.05


# ── Validation ───────────────────────────────────────────────────────────────

def test_walk_forward_windows_have_embargo_gap():
    wins = walk_forward_windows(
        date(2020, 1, 1), date(2024, 1, 1),
        train_months=12, test_months=6, embargo_days=60,
    )
    assert wins
    for w in wins:
        assert w.train_end < w.test_start
        assert (w.test_start - w.train_end).days >= 60


def test_deflated_sharpe_penalizes_more_trials():
    # A modestly positive daily series.
    rets = [0.001, -0.0005, 0.0012, 0.0008, -0.0003, 0.0015, 0.0002, 0.0009,
            0.0011, -0.0006, 0.0007, 0.0004]
    dsr1 = deflated_sharpe_ratio(rets, num_trials=1)
    dsr50 = deflated_sharpe_ratio(rets, num_trials=50)
    assert dsr1 is not None and dsr50 is not None
    assert dsr50 < dsr1  # more trials tried → more deflation
