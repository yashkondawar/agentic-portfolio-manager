"""
indicators.py
=============

Vectorized, strictly *causal* indicator series for the GFS backtest.

Every function here returns a series aligned to the daily index in which the
value at position ``t`` is computable from rows ``<= t`` only. That property is
what makes the whole backtest trustworthy, and it is asserted directly by
``tests/test_gfs_leakage.py`` (truncating the input must not change any earlier
output).

The interesting function is :func:`htf_rsi_daily`, which projects a
higher-timeframe (weekly / monthly) RSI onto daily dates.

Why this is subtle
------------------
The naive implementation - resample the whole daily history to monthly, compute
RSI, then read "the last row" - is a look-ahead bug. On 2024-03-06 that last
monthly bar spans all of March, including sessions that have not happened yet.
Backtests built that way show spectacular results that evaporate live.

The fix has two parts:

1. **Closed bars are addressed by their period-end label.** A month's candle is
   labelled with its month-end date, so ``reindex(daily_index, method="ffill")``
   at day ``t`` resolves to the last candle whose period ended on or before
   ``t``. A partially elapsed period simply has no label yet, so it cannot be
   picked up.

2. **The in-progress bar is reconstructed incrementally.** Wilder's RSI is a
   recursive average, so the state after the last *closed* higher-timeframe bar
   is a fixed pair ``(avg_gain, avg_loss)``. Appending one more bar - whose
   close is *today's* daily close - is a single O(1) update. That makes the
   "live" chart value exactly reproducible for every day at once, without ever
   touching a future session.

A pleasant consequence of (2): on the last daily session of a period, the "live"
value is exactly the RSI that period will be stamped with once it closes. So
``live`` on 30-April equals ``closed`` on the first session of May - the live
series is the closed series shifted forward to the moment the information
actually became available. ``closed`` mode lags by design: it will not show
April's value until April's period-end label has passed, which is the
conservative choice when the label falls on a weekend.
"""

import math
from typing import Optional, Tuple

import numpy as np
import pandas as pd

# pandas >= 2.2 spells month-end "ME"; weeks are labelled on their Friday.
MONTHLY_RULE = "ME"
WEEKLY_RULE = "W-FRI"


# ── Single-timeframe primitives ──────────────────────────────────────────────


def _wilder_smooth(values: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing with Wilder's *seed*.

    This is deliberately not a plain ``ewm(alpha=1/period, adjust=False)``.
    ``ewm`` seeds the recursion with the first observation, whereas Wilder (and
    therefore TradingView, Chartink and every platform a discretionary trader
    actually looks at) seeds it with the simple mean of the first ``period``
    observations. The two converge - the discrepancy decays by a factor of
    ``(1 - 1/period)`` per bar - but "eventually converges" is worthless on a
    *monthly* series that only has a few dozen bars in total. Getting this wrong
    would mean backtesting a different indicator from the one the strategy is
    defined in terms of.
    """
    out = pd.Series(np.nan, index=values.index, dtype="float64")
    if len(values) < period + 1:
        return out
    seed_window = values.iloc[1 : period + 1]
    if seed_window.isna().any():
        return out
    seed = float(seed_window.mean())

    seed_point = pd.Series([seed], index=values.index[period : period + 1], dtype="float64")
    recursion = pd.concat([seed_point, values.iloc[period + 1 :]])
    smoothed = recursion.ewm(alpha=1.0 / period, adjust=False).mean()
    out.loc[smoothed.index] = smoothed
    return out


def wilder_avg_gain_loss(
    close: pd.Series, period: int = 14
) -> Tuple[pd.Series, pd.Series]:
    """Wilder's smoothed average gain / loss series (causal).

    Exposed separately from :func:`rsi_series` because the incremental "live
    bar" update in :func:`htf_rsi_daily` needs the running state, not just the
    resulting RSI.
    """
    close = close.astype("float64")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    return _wilder_smooth(gain, period), _wilder_smooth(loss, period)


def _rsi_from_avgs(avg_gain: pd.Series, avg_loss: pd.Series) -> pd.Series:
    """RSI from smoothed averages, handling the zero-loss edge case."""
    avg_gain = avg_gain.astype("float64")
    avg_loss = avg_loss.astype("float64")
    out = pd.Series(np.nan, index=avg_gain.index, dtype="float64")
    valid = avg_gain.notna() & avg_loss.notna()
    if not valid.any():
        return out
    g = avg_gain[valid]
    loss_ = avg_loss[valid]
    rs = g / loss_.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    # avg_loss == 0 means an unbroken run of up-bars -> RSI is 100 by definition
    # (and 50 in the degenerate flat case where there is no movement at all).
    rsi = rsi.where(loss_ != 0.0, other=np.where(g > 0, 100.0, 50.0))
    out.loc[valid] = rsi
    return out


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI as a full causal series."""
    avg_gain, avg_loss = wilder_avg_gain_loss(close, period)
    return _rsi_from_avgs(avg_gain, avg_loss)


def atr_series(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Wilder ATR as a full causal series.

    The first bar has no previous close, so its "true range" is not a true range
    at all; it is dropped rather than allowed to contaminate the seed.
    """
    prev_close = close.shift()
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    tr.iloc[0] = np.nan
    return _wilder_smooth(tr, period)


def rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    """Scalar RSI at the last row (convenience for ad-hoc checks / tests)."""
    if len(close) < period + 1:
        return None
    val = rsi_series(close, period).iloc[-1]
    return None if (val is None or math.isnan(val)) else float(val)


# ── Higher-timeframe projection ──────────────────────────────────────────────


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample daily OHLCV to ``rule``, labelled at the period END.

    Empty periods (market-wide holidays covering a whole week) are dropped so a
    gap never manufactures a synthetic candle.
    """
    agg = {}
    for col, how in (
        ("Open", "first"),
        ("High", "max"),
        ("Low", "min"),
        ("Close", "last"),
        ("Volume", "sum"),
    ):
        if col in df.columns:
            agg[col] = how
    out = df.resample(rule, label="right", closed="right").agg(agg)
    return out.dropna(subset=["Close"])


def htf_rsi_daily(
    daily: pd.DataFrame,
    rule: str,
    period: int = 14,
    mode: str = "closed",
) -> Tuple[pd.Series, pd.Series]:
    """Project a higher-timeframe RSI onto the daily index.

    Parameters
    ----------
    daily:
        Daily OHLCV with a sorted, unique, tz-naive ``DatetimeIndex``.
    rule:
        ``WEEKLY_RULE`` or ``MONTHLY_RULE``.
    period:
        RSI lookback in higher-timeframe bars.
    mode:
        ``"closed"`` uses only completed candles. ``"live"`` additionally folds
        in the in-progress candle using today's daily close as its running
        close - the value a trader actually reads off a chart intraday.

    Returns
    -------
    (rsi_daily, closed_bar_count)
        Both indexed by ``daily.index``. ``closed_bar_count`` is how many
        higher-timeframe candles had already closed as of each day, used to
        enforce warmup instead of silently trading a half-warm indicator.
    """
    idx = daily.index
    if len(idx) == 0:
        empty = pd.Series(dtype="float64")
        return empty, empty.copy()

    htf = resample_ohlc(daily, rule)
    if htf.empty:
        nan = pd.Series(np.nan, index=idx, dtype="float64")
        return nan, pd.Series(0, index=idx, dtype="int64")

    avg_gain, avg_loss = wilder_avg_gain_loss(htf["Close"], period)
    closed_rsi = _rsi_from_avgs(avg_gain, avg_loss)

    # Period-end labels can legitimately fall on non-trading days (a month
    # ending on a Sunday). Sorting is guaranteed by resample; reindex+ffill then
    # resolves each daily date to the most recent *closed* period.
    bar_index = pd.Series(np.arange(1, len(htf) + 1), index=htf.index, dtype="float64")
    n_closed = bar_index.reindex(idx, method="ffill").fillna(0.0).astype("int64")

    if mode == "closed":
        return closed_rsi.reindex(idx, method="ffill"), n_closed

    if mode != "live":
        raise ValueError(f"unknown htf mode {mode!r}")

    # Live mode: one Wilder step past the last closed bar, using today's close.
    prev_gain = avg_gain.reindex(idx, method="ffill")
    prev_loss = avg_loss.reindex(idx, method="ffill")
    prev_close = htf["Close"].reindex(idx, method="ffill")

    delta = daily["Close"].astype("float64") - prev_close
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    alpha = 1.0 / period
    live_gain = prev_gain * (1.0 - alpha) + gain * alpha
    live_loss = prev_loss * (1.0 - alpha) + loss * alpha
    return _rsi_from_avgs(live_gain, live_loss), n_closed


# ── Misc causal helpers ──────────────────────────────────────────────────────


def rolling_median_turnover_cr(
    close: pd.Series, volume: pd.Series, window: int = 20
) -> pd.Series:
    """Median daily traded value over ``window`` sessions, in Rs crore.

    Median rather than mean so a single delivery-block day cannot make an
    illiquid name look tradable.
    """
    return (close * volume).rolling(window, min_periods=window).median() / 1e7


def prior_swing_high(high: pd.Series, window: int) -> pd.Series:
    """Highest high over the previous ``window`` bars, EXCLUDING the current bar.

    Excluding the current bar is what makes "price reached a previously
    identified resistance" a level that was knowable beforehand.
    """
    return high.rolling(window, min_periods=window).max().shift(1)


def rolling_swing_low(low: pd.Series, window: int) -> pd.Series:
    """Lowest low over the trailing ``window`` bars, including the current one."""
    return low.rolling(window, min_periods=window).min()


def pct_return_series(close: pd.Series, lookback: int) -> pd.Series:
    """Trailing ``lookback``-session percentage return."""
    return (close / close.shift(lookback) - 1.0) * 100.0
