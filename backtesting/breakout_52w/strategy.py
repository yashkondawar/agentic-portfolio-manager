"""Point-in-time entry, sizing, and exit rules for 52-week breakouts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

import pandas as pd

from backtesting.swing_trading import indicators as ind
from backtesting.swing_trading.portfolio import Position

from .config import BreakoutConfig


@dataclass(frozen=True)
class EntrySignal:
    symbol: str
    signal_date: date
    signal_close: float
    signal_low: float
    breakout_level: float
    atr: float
    volume_ratio: float
    average_volume_50: float
    average_turnover_cr: float
    score: float


@dataclass(frozen=True)
class ExitOp:
    price: float
    reason: str
    fraction: float = 1.0


def market_regime_allows_entries(
    benchmark: Optional[pd.DataFrame], cfg: BreakoutConfig
) -> bool:
    if benchmark is None or len(benchmark) < cfg.regime_sma_slow:
        return False
    close = benchmark["Close"]
    price = float(close.iloc[-1])
    fast = ind.sma(close, cfg.regime_sma_fast)
    slow = ind.sma(close, cfg.regime_sma_slow)
    return bool(fast is not None and slow is not None and price > fast and price > slow)


def _quantize(value: float, step: float = 0.25) -> float:
    return max(0.0, min(1.0, round(value / step) * step))


def regime_exposure(
    benchmark: Optional[pd.DataFrame],
    breadth_pct: Optional[float],
    cfg: BreakoutConfig,
) -> float:
    """Continuous gross-exposure multiplier in [0, 1] for the current regime.

    Combines the index trend (vs SMA200/SMA50) and market breadth (% of the
    universe above its SMA200) into a single multiplier, quantized to 0.25 tiers
    to limit whipsaw. A value of 0 blocks all new entries (index below its
    long-term average); 1.0 is full risk-on.

    NOTE: empirically the simple binary gate (``regime_scaling=False``) delivered
    better drawdown and risk-adjusted returns than continuous scaling on this
    universe, so scaling is off by default and kept as an optional toggle.
    """
    if not cfg.regime_scaling:
        return 1.0 if market_regime_allows_entries(benchmark, cfg) else 0.0
    if benchmark is None or len(benchmark) < cfg.regime_sma_slow:
        return 0.0

    close = benchmark["Close"].dropna()
    price = float(close.iloc[-1])
    sma50 = ind.sma(close, cfg.regime_sma_fast)
    sma200 = ind.sma(close, cfg.regime_sma_slow)
    if sma50 is None or sma200 is None:
        return 0.0

    # Primary trend gate: below the long-term average is a hard risk-off.
    if price <= sma200:
        return 0.0

    # Above the long-term trend we stay meaningfully invested. Exposure is
    # modulated by two forward-looking, slow-moving signals only: whether the
    # index also holds its intermediate (SMA50) trend, and how broadly the
    # universe participates (breadth). Reactive vol/drawdown penalties were
    # removed because they fire only after a decline and whipsaw exposure,
    # locking in losses and missing the recovery.
    score = 1.0
    if price <= sma50:
        score *= 0.75

    if cfg.regime_use_breadth and breadth_pct is not None:
        if breadth_pct < 30.0:
            score *= 0.5
        elif breadth_pct < 45.0:
            score *= 0.75

    return _quantize(score)


def compute_entry_signal(
    df: pd.DataFrame,
    benchmark: Optional[pd.DataFrame],
    symbol: str,
    signal_date: date,
    cfg: BreakoutConfig,
) -> Optional[EntrySignal]:
    required = max(
        cfg.breakout_lookback + 1,
        200,
        cfg.liquidity_average_days + 1,
        cfg.volume_average_days + 1,
        cfg.relative_strength_days + 1,
        50 + cfg.sma50_slope_days,
    )
    if df is None or len(df) < required:
        return None
    if benchmark is None or len(benchmark) < cfg.relative_strength_days + 1:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"].fillna(0)
    price = float(close.iloc[-1])
    if not math.isfinite(price) or price < cfg.min_price:
        return None

    breakout_level = ind.rolling_high(high, cfg.breakout_lookback, exclude_last=True)
    sma20 = ind.sma(close, 20)
    sma50 = ind.sma(close, 50)
    sma200 = ind.sma(close, 200)
    atr = ind.atr(high, low, close, 14)
    if None in (breakout_level, sma20, sma50, sma200, atr) or not atr:
        return None

    prior_volume = volume.iloc[:-1]
    avg_volume_20 = float(prior_volume.tail(cfg.volume_average_days).mean())
    avg_volume_50 = float(prior_volume.tail(cfg.liquidity_average_days).mean())
    prior_turnover = (close.iloc[:-1] * volume.iloc[:-1]).tail(
        cfg.liquidity_average_days
    )
    avg_turnover_cr = float(prior_turnover.mean()) / 1e7
    volume_ratio = float(volume.iloc[-1]) / avg_volume_20 if avg_volume_20 > 0 else 0.0
    extension = price - breakout_level
    breakout_pct = (price / breakout_level - 1.0) * 100.0
    stock_return_3m_pct = (
        price / float(close.iloc[-(cfg.relative_strength_days + 1)]) - 1.0
    ) * 100.0
    benchmark_close = benchmark["Close"].dropna()
    if len(benchmark_close) < cfg.relative_strength_days + 1:
        return None
    benchmark_return_3m_pct = (
        float(benchmark_close.iloc[-1])
        / float(benchmark_close.iloc[-(cfg.relative_strength_days + 1)])
        - 1.0
    ) * 100.0
    relative_strength_3m_pct = stock_return_3m_pct - benchmark_return_3m_pct
    prior_sma50 = float(close.iloc[: -cfg.sma50_slope_days].tail(50).mean())
    sma50_slope_pct = (sma50 / prior_sma50 - 1.0) * 100.0

    if not price > breakout_level:
        return None
    if breakout_pct < cfg.min_breakout_pct:
        return None
    if volume_ratio < cfg.min_volume_ratio:
        return None
    if not sma20 > sma50 > sma200:
        return None
    if relative_strength_3m_pct < cfg.min_relative_strength_3m_pct:
        return None
    if sma50_slope_pct < cfg.min_sma50_slope_pct:
        return None
    if extension > cfg.max_extension_atr * atr:
        return None
    if avg_volume_50 < cfg.min_average_volume:
        return None
    if avg_turnover_cr < cfg.min_turnover_cr:
        return None

    extension_atr = extension / atr
    score = volume_ratio + max(0.0, 1.0 - extension_atr)
    return EntrySignal(
        symbol=symbol,
        signal_date=signal_date,
        signal_close=price,
        signal_low=float(low.iloc[-1]),
        breakout_level=float(breakout_level),
        atr=float(atr),
        volume_ratio=round(volume_ratio, 4),
        average_volume_50=round(avg_volume_50, 2),
        average_turnover_cr=round(avg_turnover_cr, 2),
        score=round(score, 4),
    )


def initial_stop(fill_price: float, signal: EntrySignal, cfg: BreakoutConfig) -> float:
    volatility_stop = fill_price - cfg.atr_stop_mult * signal.atr
    technical_stop = signal.signal_low - cfg.technical_stop_buffer_atr * signal.atr
    if cfg.stop_method == "breakout_candle":
        return technical_stop
    if cfg.stop_method == "wider":
        return min(volatility_stop, technical_stop)
    return volatility_stop


def profit_target(fill_price: float, atr: float, cfg: BreakoutConfig) -> float:
    """First profit target: the partial-booking level when partial profit is on,
    otherwise the single full-exit target."""
    mult = (
        cfg.partial_profit_atr if cfg.enable_partial_profit else cfg.profit_target_atr
    )
    return fill_price + mult * atr


def size_position(
    fill_price: float,
    signal: EntrySignal,
    equity: float,
    cash: float,
    open_risk: float,
    cfg: BreakoutConfig,
) -> Tuple[int, float]:
    stop = initial_stop(fill_price, signal, cfg)
    risk_per_share = fill_price - stop
    if fill_price <= 0 or risk_per_share <= 0:
        return 0, stop

    per_trade_budget = equity * cfg.risk_per_trade_pct / 100.0
    heat_remaining = max(0.0, equity * cfg.max_open_risk_pct / 100.0 - open_risk)
    shares = math.floor(min(per_trade_budget, heat_remaining) / risk_per_share)
    shares = min(
        shares,
        math.floor((equity * cfg.max_position_pct / 100.0) / fill_price),
        math.floor((cash * 0.999) / fill_price),
    )
    return max(shares, 0), stop


def evaluate_exit(
    pos: Position,
    bar: pd.Series,
    df_asof: pd.DataFrame,
    cfg: BreakoutConfig,
) -> List[ExitOp]:
    open_price = float(bar["Open"])
    low = float(bar["Low"])
    high = float(bar["High"])
    close_price = float(bar["Close"])

    if open_price <= pos.stop_loss:
        return [ExitOp(open_price, "STOP-GAP")]
    if low <= pos.stop_loss:
        return [ExitOp(pos.stop_loss, "STOP")]

    ops: List[ExitOp] = []
    if cfg.enable_partial_profit:
        # Book a slice at the first target, move the remainder's stop to breakeven,
        # then let it ride an uncapped trailing stop (no hard full target).
        if not pos.partial_booked and high >= pos.target_price:
            pos.partial_booked = True
            pos.stop_loss = max(pos.stop_loss, pos.entry_price)
            ops.append(
                ExitOp(
                    max(open_price, pos.target_price),
                    "PARTIAL-TARGET",
                    cfg.partial_profit_fraction,
                )
            )
    elif high >= pos.target_price:
        return [ExitOp(max(open_price, pos.target_price), "TARGET")]

    pos.bars_held += 1
    pos.highest_high = max(pos.highest_high, high)
    if close_price < pos.breakout_level:
        pos.below_breakout_closes += 1
    else:
        pos.below_breakout_closes = 0
    if pos.below_breakout_closes >= cfg.false_breakout_closes:
        return ops + [ExitOp(close_price, "FALSE-BREAKOUT")]

    if pos.highest_high >= (
        pos.entry_price + cfg.trail_activation_atr * pos.atr_at_entry
    ):
        pos.trailing_active = True
    if pos.partial_booked:
        pos.trailing_active = True

    if pos.trailing_active:
        if cfg.trail_method == "sma20":
            sma20 = ind.sma(df_asof["Close"], 20)
            if sma20 is not None and close_price < sma20:
                return ops + [ExitOp(close_price, "TRAIL-SMA20")]
        else:
            atr = (
                ind.atr(df_asof["High"], df_asof["Low"], df_asof["Close"], 14)
                or pos.atr_at_entry
            )
            chandelier = pos.highest_high - cfg.chandelier_atr_mult * atr
            pos.stop_loss = max(pos.stop_loss, chandelier)

    progress_pct = (
        (pos.highest_high / pos.entry_price - 1.0) * 100.0 if pos.entry_price else 0.0
    )
    if (
        not pos.partial_booked
        and pos.bars_held >= cfg.time_exit_sessions
        and progress_pct < cfg.time_exit_progress_pct
    ):
        return ops + [ExitOp(close_price, "TIME-EXIT")]
    return ops
