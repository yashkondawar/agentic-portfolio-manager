"""Tests for the GFS conviction study.

The two things worth testing here are the ones that would silently invalidate
every number the study produces: whether a feature can see the future, and
whether the standalone trade simulator agrees with the engine it claims to
mirror. Formatting and ranking are cosmetic by comparison.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtesting.gfs import conviction as cv
from backtesting.gfs.config import GFSConfig
from backtesting.gfs.panels import PANEL_COLUMNS


def make_cfg(**kw) -> GFSConfig:
    base = dict(atr_stop_mult=2.0, exit_rsi=65.0, s_rsi_entry=40.0,
                commission_pct=0.0, slippage_bps=0.0, max_holding_days=0)
    base.update(kw)
    return GFSConfig(**base)


def make_frame(n: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, n))), index=idx)
    frame = pd.DataFrame(index=idx)
    frame["Close"] = close
    frame["Open"] = close.shift(1).fillna(close.iloc[0])
    frame["High"] = frame[["Open", "Close"]].max(axis=1) * 1.01
    frame["Low"] = frame[["Open", "Close"]].min(axis=1) * 0.99
    frame["Volume"] = rng.integers(1e5, 1e6, n).astype(float)
    frame["rsi_d"] = rng.uniform(20, 80, n)
    frame["rsi_w"] = rng.uniform(40, 90, n)
    frame["rsi_m"] = rng.uniform(40, 90, n)
    frame["rsi_d_prev"] = frame["rsi_d"].shift(1)
    frame["n_weekly"] = np.arange(n) // 5
    frame["n_monthly"] = np.arange(n) // 21
    frame["atr"] = close * 0.02
    frame["atr_pct"] = 2.0
    frame["sma200"] = close.rolling(200, min_periods=1).mean()
    frame["above_sma200"] = frame["Close"] > frame["sma200"]
    frame["turnover_cr"] = 50.0
    frame["swing_low"] = close.rolling(20, min_periods=1).min()
    frame["resistance"] = close.rolling(63, min_periods=1).max()
    frame["headroom_pct"] = (frame["resistance"] - close) / close * 100.0
    for col in ("tradable", "gf_ok", "s_dip", "s_recross"):
        frame[col] = True
    return frame[PANEL_COLUMNS]


# ── Leakage ──────────────────────────────────────────────────────────────────


def test_features_do_not_see_the_future():
    """Truncating the frame must not change any feature value that survives.

    This is the only test that actually matters for the credibility of the
    study: a single forward-looking feature would make every win rate below
    meaningless, and lookahead is invisible to inspection.
    """
    cfg = make_cfg()
    frame = make_frame()
    full = cv.add_feature_columns(frame, cfg)
    cut = 300
    truncated = cv.add_feature_columns(frame.iloc[:cut], cfg)

    for col in truncated.columns:
        if col not in full.columns:
            continue
        a = full[col].iloc[:cut]
        b = truncated[col]
        if not pd.api.types.is_numeric_dtype(a):
            continue
        both = a.notna() & b.notna()
        assert np.allclose(a[both].to_numpy(), b[both].to_numpy()), (
            f"{col} changed when future bars were removed - it leaks."
        )


def test_signal_table_respects_the_configured_window():
    """The bar store holds more history than the window; signals outside the
    configured dates must not silently enter the sample."""
    cfg = make_cfg(start_date=pd.Timestamp("2016-01-01").date(),
                   end_date=pd.Timestamp("2016-06-30").date())
    frame = make_frame()

    class Panel:
        symbol, sector = "AAA", "Tech"

    panel = Panel()
    panel.frame = frame
    qualify = pd.DataFrame({"AAA": True}, index=frame.index)
    table = cv.build_signal_table(
        {"AAA": panel}, qualify, None, None, cfg, respect_gates=False
    )
    assert not table.empty
    assert table["signal_date"].min() >= pd.Timestamp("2016-01-01")
    assert table["signal_date"].max() <= pd.Timestamp("2016-06-30")


# ── Trade simulation ─────────────────────────────────────────────────────────


def test_entry_is_the_next_open_not_the_signal_close():
    cfg = make_cfg()
    frame = make_frame()
    out = cv.simulate_signal(frame, 100, cfg)
    assert out is not None
    assert out.entry_price == pytest.approx(frame["Open"].iloc[101])
    assert out.entry_date == frame.index[101]


def test_stop_is_honoured_and_a_gap_fills_at_the_open():
    """A bar that gaps below the stop cannot fill at the stop price."""
    cfg = make_cfg()
    frame = make_frame().copy()
    i = 100
    entry_open = frame["Open"].iloc[i + 1]
    stop = entry_open - 2.0 * frame["atr"].iloc[i]
    # Force the next bar to gap far below the stop.
    frame.iloc[i + 2, frame.columns.get_loc("Open")] = stop * 0.9
    frame.iloc[i + 2, frame.columns.get_loc("Low")] = stop * 0.85
    frame.iloc[i + 2, frame.columns.get_loc("High")] = stop * 0.95
    frame.iloc[i + 2, frame.columns.get_loc("Close")] = stop * 0.9

    out = cv.simulate_signal(frame, i, cfg)
    assert out.reason == "stop"
    assert out.exit_price == pytest.approx(stop * 0.9)
    assert out.exit_price < stop
    assert out.r_multiple < -1.0


def test_stop_takes_precedence_over_the_target_in_the_same_bar():
    """Daily bars cannot resolve intrabar order, so the loss must be assumed."""
    cfg = make_cfg()
    frame = make_frame().copy()
    i = 100
    entry_open = frame["Open"].iloc[i + 1]
    stop = entry_open - 2.0 * frame["atr"].iloc[i]
    target = frame["resistance"].iloc[i]
    frame.iloc[i + 2, frame.columns.get_loc("Low")] = stop * 0.98
    frame.iloc[i + 2, frame.columns.get_loc("High")] = target * 1.05

    out = cv.simulate_signal(frame, i, cfg)
    assert out.reason == "stop"


def test_rsi_exit_fills_at_the_following_open():
    """An RSI reading is only known at the close, so it cannot fill that day."""
    cfg = make_cfg()
    frame = make_frame().copy()
    i = 100
    frame.iloc[:, frame.columns.get_loc("resistance")] = 1e9  # disable the target
    frame.iloc[i + 1:, frame.columns.get_loc("rsi_d")] = 10.0
    frame.iloc[i + 3, frame.columns.get_loc("rsi_d")] = 90.0

    out = cv.simulate_signal(frame, i, cfg)
    assert out.reason == "rsi_target"
    assert out.exit_date == frame.index[i + 4]
    assert out.exit_price == pytest.approx(frame["Open"].iloc[i + 4])


def test_target_is_frozen_at_signal_time():
    """If the target tracked a rolling high, a later bar would define the exit."""
    cfg = make_cfg()
    frame = make_frame().copy()
    i = 100
    target = float(frame["resistance"].iloc[i])
    frame.iloc[i + 1:, frame.columns.get_loc("rsi_d")] = 10.0
    # A much higher resistance later must not move the exit level.
    frame.iloc[i + 5:, frame.columns.get_loc("resistance")] = target * 5
    frame.iloc[i + 2, frame.columns.get_loc("High")] = target * 1.02
    frame.iloc[i + 2, frame.columns.get_loc("Low")] = target * 0.99
    frame.iloc[i + 2, frame.columns.get_loc("Open")] = target * 0.995

    out = cv.simulate_signal(frame, i, cfg)
    assert out.reason == "resistance"
    assert out.exit_price == pytest.approx(target)


def test_no_time_stop_exists():
    """The user's requirement: nothing may close a trade on elapsed time."""
    cfg = make_cfg()
    frame = make_frame(n=900).copy()
    frame.iloc[:, frame.columns.get_loc("resistance")] = 1e9
    frame.iloc[:, frame.columns.get_loc("rsi_d")] = 10.0  # never hits the exit
    frame.iloc[:, frame.columns.get_loc("Low")] = frame["Close"] * 0.999
    out = cv.simulate_signal(frame, 100, cfg)
    assert out.reason == "open_at_horizon"
    assert out.open_at_horizon is True
    assert out.days_held == cv.MAX_TRACK_SESSIONS


def test_unresolved_trades_are_excluded_from_statistics():
    table = pd.DataFrame({
        "r_multiple": [1.0, -1.0, 5.0],
        "days_held": [5, 5, 500],
        "open_at_horizon": [False, False, True],
    })
    stats = cv.evaluate(table)
    assert stats["n"] == 2
    assert stats["win_rate"] == pytest.approx(50.0)


def test_costs_reduce_the_realised_return():
    frame = make_frame()
    free = cv.simulate_signal(frame, 100, make_cfg())
    costed = cv.simulate_signal(
        frame, 100, make_cfg(commission_pct=0.5, slippage_bps=50.0)
    )
    assert costed.entry_price > free.entry_price
    assert costed.r_multiple < free.r_multiple


# ── Analysis helpers ─────────────────────────────────────────────────────────


def test_split_is_chronological_and_does_not_overlap():
    """A random split would leak: same-day signals are effectively one bet."""
    table = pd.DataFrame({
        "signal_date": pd.bdate_range("2020-01-01", periods=100),
        "r_multiple": np.linspace(-1, 1, 100),
        "open_at_horizon": False,
    })
    train, test = cv.split_by_date(table, 0.6)
    assert train["signal_date"].max() < test["signal_date"].min()
    assert len(train) + len(test) == len(table)


def test_rule_mask_is_a_conjunction():
    table = pd.DataFrame({"a": [1, 2, 3, 4], "b": [10, 20, 30, 40]})
    mask = cv.rule_mask(table, {"a": (2, 4), "b": (10, 30)})
    assert mask.tolist() == [False, True, True, False]


def test_evaluate_reports_win_rate_and_expectancy_together():
    """Win rate alone is gameable through exit geometry, so both must exist."""
    table = pd.DataFrame({
        "r_multiple": [0.2, 0.2, 0.2, -3.0],
        "days_held": [1, 1, 1, 1],
        "open_at_horizon": [False] * 4,
    })
    stats = cv.evaluate(table)
    assert stats["win_rate"] == pytest.approx(75.0)
    assert stats["exp_r"] < 0  # high win rate, negative edge


def test_monotonic_detection():
    assert cv._is_monotonic(pd.Series([1.0, 2.0, 3.0, 4.0]))
    assert cv._is_monotonic(pd.Series([4.0, 3.0, 2.0, 1.0]))
    assert not cv._is_monotonic(pd.Series([1.0, 5.0, 2.0, 4.0]))
