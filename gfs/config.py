"""
config.py
=========

Translation layer: UI/CLI parameters -> the *backtest's* :class:`GFSConfig`.

There is deliberately no second copy of the strategy's defaults here. Every knob
below either (a) forwards a user parameter into ``GFSConfig``, or (b) pins a
field to the value the research settled on. Pinned fields are pinned in one
place with a one-line reason, so "why is the live strategy doing that?" always
has an answer that points back at ``backtesting/gfs/EXPLORATIONS.md``.

The adopted configuration (EXPLORATIONS.md, "Scoreboard")
--------------------------------------------------------
========================  =========  ==================================================
field                     live       why
========================  =========  ==================================================
``s_rsi_entry``           43         Ch.6 - 40 is arbitrary; 43 adds signals without
                                     degrading the edge.
``min_headroom_pct``      10         Ch.4 - the only entry filter that survived a
                                     train/test split.
``atr_stop_mult``         3.5        Ch.5 - the taught 3-5% fixed stop liquidates half
                                     the winners inside noise. Plateau is 3.0-4.5.
``max_holding_days``      0          User instruction: no time-based exit, ever.
``exit_rsi``              70         Ch.8 - +21.5% vs +18.5% CAGR, payoff 0.82 -> 1.37.
``regime_mode``           breadth    Ch.9 - the index 200-DMA leg adds nothing the
                                     breadth leg has not already said.
``min_breadth_pct``       40         Ch.9.
``max_positions``         4          Ch.5 - concentration is where the payoff comes
``max_position_pct``      30         from; 8 x 15% dilutes the winners.
``htf_mode``              closed     The leak-free mode, and the one every published
                                     number was produced under.
``cash_yield_pct``        6.5        Ch.5 - this book is ~40-60% deployed; pretending
                                     the idle balance earns nothing is a silent penalty
                                     the always-invested benchmark never pays.
========================  =========  ==================================================
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from backtesting.gfs.config import (
    EXIT_RSI,
    HTF_CLOSED,
    RANK_COMPOSITE,
    REGIME_BREADTH,
    REGIME_BREADTH_SMA,
    SIZING_EQUAL,
    STOP_ATR,
    GFSConfig,
)

# Namespace used for every document this strategy persists.
DOC_NAMESPACE = "gfs"
STRATEGY_ID = "gfs_live"

REGIME_MODES = (REGIME_BREADTH, REGIME_BREADTH_SMA)

#: Live defaults. These are the *research-adopted* values, not the backtest
#: dataclass defaults - ``GFSConfig`` keeps neutral defaults so that ablations
#: stay honest, while the live strategy ships the configuration that won.
LIVE_DEFAULTS: Dict[str, Any] = {
    "starting_capital": 500_000.0,
    "universe_index": "nifty500",
    "benchmark": "^NSEI",
    "g_rsi_min": 60.0,
    "f_rsi_min": 60.0,
    "s_rsi_entry": 43.0,
    "min_headroom_pct": 10.0,
    "exit_rsi": 70.0,
    "shadow_exit_rsi": 60.0,
    "atr_stop_mult": 3.5,
    "regime_mode": REGIME_BREADTH,
    "min_breadth_pct": 40.0,
    "sector_top_n": 5,
    "max_per_sector": 2,
    "max_positions": 4,
    "max_position_pct": 30.0,
    "cash_yield_pct": 6.5,
    "commission_pct": 0.05,
    "slippage_bps": 15.0,
}

#: Fields the live runner pins. Exposing these would let a user silently produce
#: a book that no backtest ever validated, so they are not parameters.
PINNED: Dict[str, Any] = {
    "htf_mode": HTF_CLOSED,
    "entry_trigger": "dip",
    "exit_mode": EXIT_RSI,
    "stop_mode": STOP_ATR,
    "sizing_mode": SIZING_EQUAL,
    "rank_by": RANK_COMPOSITE,
    "max_holding_days": 0,
    "move_stop_to_breakeven_at_r": 0.0,
    "exit_f_rsi": 0.0,
    "indicator_exit_delay": True,
    "use_regime_filter": True,
    "use_sector_filter": True,
    "rsi_period_daily": 14,
    "rsi_period_weekly": 14,
    "rsi_period_monthly": 14,
}

# History pulled before the first simulated session. Monthly RSI(14) with Wilder
# smoothing needs a few dozen closed monthly candles before it means anything.
WARMUP_DAYS = 2600


def _as_date(value: Any) -> Optional[date]:
    """Accept the ISO strings ``coerce_params`` produces, plus real dates."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def build_config(params: Dict[str, Any], *, start: date, end: date) -> GFSConfig:
    """Build the backtest config the live engine will run.

    ``start``/``end`` bound the sessions to simulate on *this* run - normally
    "the day after the last run" through "today". Everything before ``start`` is
    already reflected in the persisted book.
    """
    get = lambda key: params.get(key, LIVE_DEFAULTS.get(key))  # noqa: E731

    cfg = GFSConfig(
        start_date=start,
        end_date=end,
        warmup_days=WARMUP_DAYS,
        universe_index=str(get("universe_index")),
        benchmark=str(get("benchmark")),
        g_rsi_min=float(get("g_rsi_min")),
        f_rsi_min=float(get("f_rsi_min")),
        s_rsi_entry=float(get("s_rsi_entry")),
        min_headroom_pct=float(get("min_headroom_pct")),
        exit_rsi=float(get("exit_rsi")),
        atr_stop_mult=float(get("atr_stop_mult")),
        regime_mode=str(get("regime_mode")),
        min_breadth_pct=float(get("min_breadth_pct")),
        sector_top_n=int(get("sector_top_n")),
        max_per_sector=int(get("max_per_sector")),
        max_positions=int(get("max_positions")),
        max_position_pct=float(get("max_position_pct")),
        starting_capital=float(get("starting_capital")),
        cash_yield_pct=float(get("cash_yield_pct")),
        commission_pct=float(get("commission_pct")),
        slippage_bps=float(get("slippage_bps")),
        label="gfs_live",
    )
    for field, value in PINNED.items():
        setattr(cfg, field, value)
    cfg.validate()
    return cfg


def shadow_exit_rsi(params: Dict[str, Any]) -> Optional[float]:
    """The alternate exit threshold to report but never act on.

    The research could not separate exit-60 from exit-70 with confidence, so the
    live book trades one of them and *shows* what the other would have done.
    Returns ``None`` when the shadow is disabled or identical to the live rule.
    """
    value = params.get("shadow_exit_rsi", LIVE_DEFAULTS["shadow_exit_rsi"])
    if value is None or float(value) <= 0:
        return None
    shadow = float(value)
    live = float(params.get("exit_rsi", LIVE_DEFAULTS["exit_rsi"]))
    return None if abs(shadow - live) < 1e-9 else shadow


def default_bootstrap_start(today: date) -> date:
    """Where a cold-start book begins when the user does not say.

    One session: the book opens today, flat, with no invented history.
    """
    return today - timedelta(days=1)
