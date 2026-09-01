"""
watchlist.py
============

Monthly watchlist generation for the backtest — point-in-time.

This REUSES the live monthly curator's Stage-1 mechanical screen
(``watchlist_curator.py``): the same SMA-stack / RSI / ATR% / returns /
relative-strength / liquidity / volume-surge filters and the same composite
score + industry diversification. The only differences vs the live run:

  * It is evaluated on AS-OF price slices (rows dated <= the rebalance day), so
    the watchlist for, say, 2026-01-01 is built only from data available then.
  * Stage-2 LLM curation is SKIPPED — an LLM with live web/screener tools cannot
    be made point-in-time, so the deterministic mechanical shortlist is used as
    the month's watchlist. (See README for the rationale.)
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

# Make the repo root importable so we can reuse the live curator logic.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from watchlist_curator import (  # noqa: E402  (after sys.path tweak)
    ScreenConfig,
    StockMetrics,
    UniverseStock,
    _compute_metrics_for,
    _ret,
    load_universe_from_file,
    load_universe_from_index,
    score_and_rank,
)

from .config import BacktestConfig
from .data import PointInTimeData

logger = logging.getLogger("backtest.watchlist")


def load_universe(cfg: BacktestConfig) -> List[UniverseStock]:
    if cfg.universe_file is not None:
        return load_universe_from_file(Path(cfg.universe_file))
    # Support a comma-separated union of indices, e.g. "nifty500,niftysmallcap250",
    # so the earnings-drift scan can reach the mid/small-cap zone where PEAD alpha
    # concentrates. Symbols are de-duplicated, first occurrence (with its industry)
    # winning.
    keys = [k.strip() for k in str(cfg.universe_index).split(",") if k.strip()]
    if len(keys) <= 1:
        return load_universe_from_index(cfg.universe_index)
    seen: set[str] = set()
    merged: List[UniverseStock] = []
    for key in keys:
        for u in load_universe_from_index(key):
            if u.symbol not in seen:
                seen.add(u.symbol)
                merged.append(u)
    logger.info("Merged universe %s → %d unique symbols", keys, len(merged))
    return merged


def _benchmark_ret_3m(data: PointInTimeData, day: date) -> Optional[float]:
    bench = data.benchmark_as_of(day)
    if bench is None or bench.empty:
        return None
    return _ret(bench["Close"], 63)


def build_watchlist_for(
    data: PointInTimeData,
    universe: List[UniverseStock],
    day: date,
    cfg: BacktestConfig,
) -> List[StockMetrics]:
    """Mechanical Stage-1 shortlist as-of `day`. Returns ranked StockMetrics."""
    industry_by_sym = {u.symbol: u.industry for u in universe}
    nifty_ret_3m = _benchmark_ret_3m(data, day)

    metrics: List[StockMetrics] = []
    for u in universe:
        # Slice to data available on `day`; cap rows for speed (need <=252 + buffer).
        sub = data.as_of(u.symbol, day, lookback_rows=400)
        if sub is None or len(sub) < 60:
            continue
        m = _compute_metrics_for(
            u.symbol, industry_by_sym.get(u.symbol, "Unknown"), sub, nifty_ret_3m
        )
        if m is not None:
            metrics.append(m)

    screen = ScreenConfig(
        min_price=cfg.min_price,
        min_liquidity_cr=cfg.min_liquidity_cr,
        rsi_min=45.0,                      # Stage-1 uses a wider band than entry
        rsi_max=80.0,
        max_atr_pct=cfg.max_atr_pct,
        shortlist_size=cfg.shortlist_size,
        max_per_industry=cfg.max_per_industry,
    )
    ranked = score_and_rank(metrics, screen)
    return ranked[: cfg.watchlist_size]


def watchlist_symbols(ranked: List[StockMetrics]) -> List[str]:
    return [m.symbol for m in ranked]
