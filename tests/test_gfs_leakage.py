"""
Leakage tests for the GFS backtest.

These are the most important tests in the package. Everything else measures
performance; these establish whether the measurement means anything.

The central property being asserted is **truncation invariance**: if you delete
every row after some date T and recompute, nothing dated on or before T may
change. A backtest that violates this is reading the future, and its results are
worthless regardless of how good they look.

The second property is **future-insensitivity**: planting an extreme move after
T must not move a single value before T.
"""

import numpy as np
import pandas as pd
import pytest

from backtesting.gfs import indicators as ind
from backtesting.gfs.config import GFSConfig
from backtesting.gfs.panels import PANEL_COLUMNS, build_symbol_panel


def synthetic_ohlcv(n=1800, seed=11, start="2015-01-01"):
    """Business-day OHLCV with a gentle drift, deterministic per seed."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start=start, periods=n)
    steps = rng.normal(0.0005, 0.015, size=n)
    close = 100.0 * np.exp(np.cumsum(steps))
    spread = np.abs(rng.normal(0.0, 0.008, size=n)) * close
    frame = pd.DataFrame(
        {
            "Open": close * (1 + rng.normal(0, 0.003, size=n)),
            "High": close + spread,
            "Low": close - spread,
            "Close": close,
            "Volume": rng.integers(200_000, 3_000_000, size=n).astype(float),
        },
        index=idx,
    )
    frame["High"] = frame[["Open", "High", "Close"]].max(axis=1)
    frame["Low"] = frame[["Open", "Low", "Close"]].min(axis=1)
    return frame


@pytest.fixture(scope="module")
def daily():
    return synthetic_ohlcv()


@pytest.fixture()
def cfg():
    return GFSConfig(
        start_date=pd.Timestamp("2018-01-01").date(),
        end_date=pd.Timestamp("2021-12-31").date(),
        min_daily_bars=60,
        min_weekly_bars=20,
        min_monthly_bars=6,
        min_turnover_cr=0.0,
        min_price=0.0,
        max_atr_pct=100.0,
    )


# ── Wilder RSI correctness ───────────────────────────────────────────────────


def test_rsi_matches_manual_wilder():
    """Wilder RSI against an independently hand-rolled recursion."""
    rng = np.random.default_rng(3)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1.0, 200)))
    period = 14

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_g = gains.iloc[1 : period + 1].mean()
    avg_l = losses.iloc[1 : period + 1].mean()
    manual = [np.nan] * (period + 1)
    for i in range(period + 1, len(close)):
        avg_g = (avg_g * (period - 1) + gains.iloc[i]) / period
        avg_l = (avg_l * (period - 1) + losses.iloc[i]) / period
        manual.append(100.0 - 100.0 / (1.0 + avg_g / avg_l) if avg_l else 100.0)

    got = ind.rsi_series(close, period)
    np.testing.assert_allclose(got.iloc[period + 1 :], manual[period + 1 :], rtol=1e-9)


def test_rsi_bounds_and_edge_cases():
    flat = pd.Series([50.0] * 60)
    assert ind.rsi_series(flat, 14).dropna().eq(50.0).all()

    rising = pd.Series(np.arange(1.0, 61.0))
    assert ind.rsi_series(rising, 14).dropna().eq(100.0).all()

    noisy = ind.rsi_series(pd.Series(100 + np.cumsum(np.random.default_rng(5).normal(0, 1, 300))), 14)
    assert noisy.dropna().between(0, 100).all()


# ── Higher-timeframe projection ──────────────────────────────────────────────


@pytest.mark.parametrize("rule", [ind.WEEKLY_RULE, ind.MONTHLY_RULE])
@pytest.mark.parametrize("mode", ["closed", "live"])
def test_htf_rsi_is_truncation_invariant(daily, rule, mode):
    """Deleting the future must not change the past. The core leakage test."""
    cut = daily.index[1200]
    full, _ = ind.htf_rsi_daily(daily, rule, 14, mode)
    part, _ = ind.htf_rsi_daily(daily.loc[:cut], rule, 14, mode)
    pd.testing.assert_series_equal(
        full.loc[:cut], part, check_names=False, rtol=1e-12
    )


@pytest.mark.parametrize("rule", [ind.WEEKLY_RULE, ind.MONTHLY_RULE])
def test_htf_rsi_ignores_a_planted_future_shock(daily, rule):
    """A +80% spike after T must leave every value before T untouched."""
    cut_pos = 1200
    cut = daily.index[cut_pos]
    shocked = daily.copy()
    shocked.iloc[cut_pos + 1 :, shocked.columns.get_indexer(["Open", "High", "Low", "Close"])] *= 1.8

    base, _ = ind.htf_rsi_daily(daily, rule, 14, "live")
    after, _ = ind.htf_rsi_daily(shocked, rule, 14, "live")
    pd.testing.assert_series_equal(base.loc[:cut], after.loc[:cut], rtol=1e-12)


def test_closed_mode_never_reflects_the_current_period(daily):
    """On any day inside a month, the monthly RSI must equal the value that was
    already fixed when the previous month closed."""
    rsi_daily, n_closed = ind.htf_rsi_daily(daily, ind.MONTHLY_RULE, 14, "closed")
    monthly = ind.resample_ohlc(daily, ind.MONTHLY_RULE)
    monthly_rsi = ind.rsi_series(monthly["Close"], 14)

    checked = 0
    for ts in daily.index[600:900]:
        expected_label = monthly.index[monthly.index <= ts]
        if len(expected_label) == 0:
            continue
        expected = monthly_rsi.loc[expected_label[-1]]
        if np.isnan(expected):
            continue
        assert rsi_daily.loc[ts] == pytest.approx(expected, rel=1e-12)
        assert n_closed.loc[ts] == len(expected_label)
        checked += 1
    assert checked > 100


def test_live_mode_equals_the_period_value_on_its_last_session(daily):
    """On the last daily session of a month, the in-progress monthly candle is
    complete in all but name, so the live RSI must equal the value that candle
    is stamped with once it closes.

    This is the precise sense in which live mode is "what the chart shows" while
    remaining leak-free: it uses today's close and nothing after it.
    """
    live, _ = ind.htf_rsi_daily(daily, ind.MONTHLY_RULE, 14, "live")
    monthly = ind.resample_ohlc(daily, ind.MONTHLY_RULE)
    monthly_rsi = ind.rsi_series(monthly["Close"], 14)

    checked = 0
    for label in monthly.index:
        sessions = daily.index[(daily.index <= label)]
        if len(sessions) == 0 or np.isnan(monthly_rsi.loc[label]):
            continue
        last_session = sessions[-1]
        if last_session not in live.index or np.isnan(live.loc[last_session]):
            continue
        assert live.loc[last_session] == pytest.approx(
            monthly_rsi.loc[label], rel=1e-9
        ), label
        checked += 1
    assert checked > 20


def test_closed_mode_publishes_the_period_value_only_after_it_closes(daily):
    """The closed series must never show a period's value before that period's
    end label has passed - the whole point of the mode."""
    closed, _ = ind.htf_rsi_daily(daily, ind.MONTHLY_RULE, 14, "closed")
    monthly = ind.resample_ohlc(daily, ind.MONTHLY_RULE)
    monthly_rsi = ind.rsi_series(monthly["Close"], 14)

    for label in monthly.index[20:60]:
        value = monthly_rsi.loc[label]
        if np.isnan(value):
            continue
        before = closed.loc[:label].iloc[:-1] if label in closed.index else closed.loc[:label]
        in_period = before.loc[before.index > (label - pd.offsets.MonthEnd(1))]
        if len(in_period):
            assert not np.isclose(in_period.dropna(), value, rtol=1e-9).any(), label
        after = closed.loc[closed.index > label]
        if len(after.dropna()):
            assert after.dropna().iloc[0] == pytest.approx(value, rel=1e-9), label


def test_live_mode_reacts_within_the_period_but_closed_mode_does_not(daily):
    """Sanity check that the two modes are genuinely different mid-period,
    otherwise the boundary test above would be vacuous."""
    closed, _ = ind.htf_rsi_daily(daily, ind.MONTHLY_RULE, 14, "closed")
    live, _ = ind.htf_rsi_daily(daily, ind.MONTHLY_RULE, 14, "live")
    both = pd.concat([closed, live], axis=1).dropna()
    assert (both.iloc[:, 0] - both.iloc[:, 1]).abs().max() > 0.5


def test_resample_labels_at_period_end(daily):
    monthly = ind.resample_ohlc(daily, ind.MONTHLY_RULE)
    for label in monthly.index[:12]:
        members = daily.loc[(daily.index <= label)]
        members = members[members.index > (label - pd.offsets.MonthEnd(1))]
        assert monthly.loc[label, "Close"] == pytest.approx(members["Close"].iloc[-1])
        assert monthly.loc[label, "High"] == pytest.approx(members["High"].max())
        # The label is on or after every session it summarises - never before.
        assert members.index.max() <= label


def test_prior_swing_high_excludes_current_bar():
    high = pd.Series([1, 2, 3, 10, 4, 5], dtype="float64")
    got = ind.prior_swing_high(high, 3)
    # At position 3 (value 10) the prior 3-bar high is max(1,2,3) = 3, not 10.
    assert got.iloc[3] == 3.0


# ── Whole-panel invariance ───────────────────────────────────────────────────


def test_panel_is_truncation_invariant(daily, cfg):
    cut = daily.index[1400]
    full = build_symbol_panel("TEST", "Sector", daily, cfg)
    part = build_symbol_panel("TEST", "Sector", daily.loc[:cut], cfg)
    assert full is not None and part is not None

    a = full.frame.loc[:cut]
    b = part.frame
    assert list(a.columns) == list(b.columns) == list(PANEL_COLUMNS)
    for col in PANEL_COLUMNS:
        pd.testing.assert_series_equal(
            a[col], b[col], check_names=False, rtol=1e-10, check_dtype=False
        )


def test_panel_ignores_planted_future_data(daily, cfg):
    cut_pos, cut = 1400, daily.index[1400]
    shocked = daily.copy()
    cols = shocked.columns.get_indexer(["Open", "High", "Low", "Close"])
    shocked.iloc[cut_pos + 1 :, cols] *= 0.4  # a crash after the cut

    base = build_symbol_panel("TEST", "Sector", daily, cfg).frame.loc[:cut]
    after = build_symbol_panel("TEST", "Sector", shocked, cfg).frame.loc[:cut]
    for col in PANEL_COLUMNS:
        pd.testing.assert_series_equal(
            base[col], after[col], check_names=False, rtol=1e-10, check_dtype=False
        )
