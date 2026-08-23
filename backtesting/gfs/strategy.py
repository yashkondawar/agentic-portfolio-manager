"""
strategy.py
===========

The decisions. Everything here is a pure function of a panel row plus config, so
each rule can be unit-tested without a portfolio, a calendar or a download.

Entry (the funnel, narrowed in the same order as the strategy's own diagram)
---------------------------------------------------------------------------
1. **Helicopter** - the market regime gate must be open (handled in the engine,
   because it is a single global check).
2. **Aerial** - the stock's sector must rank inside the top ``sector_top_n`` by
   trailing relative strength.
3. **Microscopic** - Grandfather (monthly RSI) and Father (weekly RSI) above
   their thresholds, Son (daily RSI) dipping to/below its threshold, and the
   name must be liquid enough to actually trade.

Exit
----
Exits are split by *when they become knowable*, which is the detail that decides
whether a backtest is honest:

* **Price-level exits** - the stop, the profit target and the resistance level -
  are known before the session starts, so they may fill intrabar against the
  day's high/low.
* **Indicator exits** - "daily RSI reached 65" - are only known once the close
  that produced them exists. They are therefore queued and filled at the *next*
  session's open (``indicator_exit_delay``).

When both a stop and a target could have been touched within the same daily bar,
daily OHLC cannot say which came first, so the stop is always assumed to win.
That biases results downward, which is the correct direction for a bias you
cannot remove.
"""

# NOTE: no `from __future__ import annotations` - see portfolio.py.
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd

from .config import (
    EXIT_RESISTANCE,
    EXIT_RSI,
    EXIT_SCALE_OUT,
    EXIT_TRAIL,
    GFSConfig,
    RANK_COMPOSITE,
    RANK_DIP_DEPTH,
    RANK_HTF_STRENGTH,
    RANK_RANDOM,
    RANK_SECTOR_RS,
    SIZING_EQUAL,
    STOP_ATR,
    STOP_PCT,
    STOP_SWING,
)
from .portfolio import Position

# Fill timing for an exit operation.
FILL_NOW = "now"  # price level touched intrabar
FILL_NEXT_OPEN = "next_open"  # indicator condition observed at the close


@dataclass
class EntrySignal:
    symbol: str
    sector: str
    signal_date: date
    close: float
    atr: float
    stop_hint: float
    rsi_d: float
    rsi_w: float
    rsi_m: float
    sector_rank: Optional[float]
    resistance: Optional[float]
    score: float


@dataclass
class ExitOp:
    price: float
    reason: str
    fraction: float = 1.0
    fill: str = FILL_NOW


# ── Entry ────────────────────────────────────────────────────────────────────


def stop_for(entry_price: float, row: pd.Series, cfg: GFSConfig) -> float:
    """Initial stop level for a long entered at ``entry_price``.

    Falls back to the percentage stop whenever the preferred input is missing,
    so a data gap can never produce a position with no stop at all.
    """
    pct_stop = entry_price * (1.0 - cfg.fixed_stop_pct / 100.0)
    if cfg.stop_mode == STOP_PCT:
        return pct_stop
    if cfg.stop_mode == STOP_ATR:
        atr = row.get("atr")
        if atr is None or pd.isna(atr) or atr <= 0:
            return pct_stop
        return entry_price - cfg.atr_stop_mult * float(atr)
    if cfg.stop_mode == STOP_SWING:
        swing = row.get("swing_low")
        if swing is None or pd.isna(swing) or swing <= 0:
            return pct_stop
        level = float(swing) * (1.0 - cfg.swing_low_buffer_pct / 100.0)
        # A swing low sitting above the entry (possible right after a gap up)
        # would invert the trade; fall back rather than trade a negative risk.
        return level if level < entry_price else pct_stop
    return pct_stop


def _normalize(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def score_candidate(
    row: pd.Series,
    sector_rank: Optional[float],
    sector_count: int,
    cfg: GFSConfig,
    rng: random.Random,
) -> float:
    """Rank a qualifying candidate. Higher is preferred.

    ``RANK_RANDOM`` is the null hypothesis: if the composite score cannot beat
    random selection from the same qualifying pool, the ranking adds nothing and
    the honest thing is to say so.
    """
    if cfg.rank_by == RANK_RANDOM:
        return rng.random()

    rsi_d = float(row["rsi_d"])
    rsi_w = float(row["rsi_w"])
    rsi_m = float(row["rsi_m"])

    # Deeper dip = more of a pullback to buy. Bounded at 15 RSI points below the
    # threshold, beyond which "pullback" is better described as "breakdown".
    dip_depth = _normalize(cfg.s_rsi_entry - rsi_d, 0.0, 15.0)
    htf_strength = _normalize((rsi_w + rsi_m) / 2.0, 60.0, 85.0)
    if sector_rank is None or sector_count <= 1:
        sector_score = 0.5
    else:
        sector_score = _normalize(sector_count - sector_rank, 0.0, sector_count - 1)

    if cfg.rank_by == RANK_DIP_DEPTH:
        return dip_depth
    if cfg.rank_by == RANK_HTF_STRENGTH:
        return htf_strength
    if cfg.rank_by == RANK_SECTOR_RS:
        return sector_score
    if cfg.rank_by == RANK_COMPOSITE:
        return 0.4 * sector_score + 0.3 * htf_strength + 0.3 * dip_depth
    return 0.0


def qualifies(row: pd.Series, trigger_col: str) -> bool:
    """The mechanical GFS condition on one panel row."""
    return bool(row["tradable"]) and bool(row["gf_ok"]) and bool(row[trigger_col])


def build_signal(
    symbol: str,
    sector: str,
    row: pd.Series,
    day: date,
    sector_rank: Optional[float],
    sector_count: int,
    cfg: GFSConfig,
    rng: random.Random,
) -> Optional[EntrySignal]:
    close = float(row["Close"])
    if close <= 0:
        return None
    stop = stop_for(close, row, cfg)
    if stop >= close:
        return None
    atr = row.get("atr")
    resistance = row.get("resistance")
    return EntrySignal(
        symbol=symbol,
        sector=sector,
        signal_date=day,
        close=close,
        atr=0.0 if atr is None or pd.isna(atr) else float(atr),
        stop_hint=stop,
        rsi_d=float(row["rsi_d"]),
        rsi_w=float(row["rsi_w"]),
        rsi_m=float(row["rsi_m"]),
        sector_rank=sector_rank,
        resistance=None if resistance is None or pd.isna(resistance) else float(resistance),
        score=score_candidate(row, sector_rank, sector_count, cfg, rng),
    )


# ── Sizing ───────────────────────────────────────────────────────────────────


def size_position(
    fill_price: float,
    stop_price: float,
    equity: float,
    cfg: GFSConfig,
) -> float:
    """Desired share count before the cash book gets a veto.

    ``SIZING_EQUAL`` implements the strategy's own instruction to spread capital
    evenly across opportunities; ``SIZING_RISK`` sizes by distance-to-stop so a
    wide stop automatically buys fewer shares. Both are capped by the per-name
    concentration ceiling.
    """
    if fill_price <= 0:
        return 0.0
    cap_value = equity * cfg.max_position_pct / 100.0

    if cfg.sizing_mode == SIZING_EQUAL:
        target_value = min(equity / max(cfg.max_positions, 1), cap_value)
    else:
        risk_amount = equity * cfg.risk_per_trade_pct / 100.0
        per_share_risk = fill_price - stop_price
        if per_share_risk <= 0:
            return 0.0
        target_value = min(risk_amount / per_share_risk * fill_price, cap_value)

    return float(max(int(target_value / fill_price), 0))


# ── Exits ────────────────────────────────────────────────────────────────────


def _trail_level(pos: Position, row: pd.Series, cfg: GFSConfig) -> Optional[float]:
    atr = row.get("atr")
    if atr is None or pd.isna(atr) or atr <= 0:
        return None
    return float(pos.highest_close) - cfg.trail_atr_mult * float(atr)


def update_stop(pos: Position, row: pd.Series, cfg: GFSConfig) -> None:
    """Ratchet the stop upward (never downward) after a bar has been marked."""
    if cfg.move_stop_to_breakeven_at_r > 0 and not pos.partial_booked:
        trigger = pos.entry_price + cfg.move_stop_to_breakeven_at_r * pos.risk_per_share
        if pos.highest_close >= trigger:
            pos.stop_loss = max(pos.stop_loss, pos.entry_price)

    trailing_modes = (EXIT_TRAIL, EXIT_SCALE_OUT)
    if cfg.exit_mode in trailing_modes and (
        cfg.exit_mode == EXIT_TRAIL or pos.partial_booked
    ):
        level = _trail_level(pos, row, cfg)
        if level is not None:
            pos.stop_loss = max(pos.stop_loss, level)


def evaluate_exits(
    pos: Position,
    row: pd.Series,
    day: date,
    cfg: GFSConfig,
) -> List[ExitOp]:
    """Exit operations triggered by one session's data.

    ``row`` is the panel row for ``day``. The position must already have been
    marked with this bar's high/low/close by the caller.
    """
    ops: List[ExitOp] = []
    high = float(row["High"])
    low = float(row["Low"])
    close = float(row["Close"])

    # 1) Stop first, always. Daily bars cannot resolve intrabar ordering, so the
    #    unfavourable assumption is the only defensible one.
    if low <= pos.stop_loss:
        # A gap straight through the stop fills at the open, not at the stop.
        fill = min(pos.stop_loss, float(row["Open"]))
        reason = "stop" if pos.stop_loss <= pos.initial_stop else "trailing_stop"
        return [ExitOp(price=fill, reason=reason, fraction=1.0, fill=FILL_NOW)]

    # 2) Price-level profit exits (knowable in advance, so fillable intrabar).
    if cfg.exit_mode == EXIT_RESISTANCE:
        level = row.get("resistance")
        if level is not None and not pd.isna(level) and high >= float(level):
            fill = max(float(level), float(row["Open"]))
            return [ExitOp(price=fill, reason="resistance", fraction=1.0, fill=FILL_NOW)]

    # 3) Indicator exits (only knowable at this close -> next open).
    rsi_d = row.get("rsi_d")
    rsi_ready = rsi_d is not None and not pd.isna(rsi_d)
    if rsi_ready and float(rsi_d) >= cfg.exit_rsi:
        if cfg.exit_mode == EXIT_RSI:
            ops.append(
                ExitOp(price=close, reason="rsi_target", fraction=1.0, fill=_fill_mode(cfg))
            )
        elif cfg.exit_mode == EXIT_SCALE_OUT and not pos.partial_booked:
            ops.append(
                ExitOp(
                    price=close,
                    reason="rsi_partial",
                    fraction=cfg.scale_out_frac,
                    fill=_fill_mode(cfg),
                )
            )

    # 4) Time stop - a calendar rule, knowable in advance, so it fills at the
    #    next open like any other end-of-day decision.
    if not ops and cfg.max_holding_days > 0:
        if day - pos.entry_date >= timedelta(days=cfg.max_holding_days):
            ops.append(
                ExitOp(price=close, reason="time_stop", fraction=1.0, fill=FILL_NEXT_OPEN)
            )
    return ops


def _fill_mode(cfg: GFSConfig) -> str:
    return FILL_NEXT_OPEN if cfg.indicator_exit_delay else FILL_NOW


def target_for(entry_price: float, signal: EntrySignal, cfg: GFSConfig) -> float:
    """Reference target recorded on the position (informational for rsi-based
    modes, an actual exit level for ``EXIT_RESISTANCE``)."""
    if cfg.exit_mode == EXIT_RESISTANCE and signal.resistance:
        return float(signal.resistance)
    risk = max(entry_price - signal.stop_hint, 1e-9)
    return entry_price + 2.0 * risk


def can_open_sector(sector: str, exposure: Dict[str, int], cfg: GFSConfig) -> bool:
    if cfg.max_per_sector <= 0:
        return True
    return exposure.get(sector, 0) < cfg.max_per_sector


def is_finite(value) -> bool:
    return value is not None and not pd.isna(value) and math.isfinite(float(value))
