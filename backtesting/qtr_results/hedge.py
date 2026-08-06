"""
hedge.py
========

Beta-hedge overlay for the quarterly-results (PEAD) strategy.

The single honest out-of-sample test in the README — the real Nifty-500 year — lost
money in a −6% tape *by design*, because the book is naked long earnings-momentum:
its returns are dominated by market direction, not by the earnings-surprise alpha we
actually want to test. A finance desk isolates the alpha by **hedging the book's net
beta** with a short index overlay. What's left is (approximately) the PEAD alpha —
and if that alpha is not positive out-of-sample, no amount of filter-stacking will
save the strategy. The hedge is therefore both a risk control *and* the honest test.

This module is a thin, **post-hoc overlay** on the realized equity curve: given the
daily long-book equity and the benchmark, it applies a short index position sized to
a target fraction of the book's beta and returns a hedged equity curve. Modelling it
as an overlay (rather than threading futures P&L through the portfolio accounting)
keeps the change additive and the existing long-only path byte-for-byte unchanged.

Two modes:

* **beta_hedge** — short ``hedge_ratio`` × (book beta) of index exposure. With
  ``hedge_ratio = 1.0`` and an assumed book beta of ``beta`` this neutralizes market
  direction while preserving the stock-selection spread.
* **market_neutral** helper — the same machinery with ``hedge_ratio = 1.0`` and a
  full-notional short, the cleanest expression of "long good surprises, short the
  market" for research.

Costs: a per-side commission and a simple daily carry (borrow/roll) are charged on
the short notional so the hedge is not free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import math


@dataclass
class HedgeConfig:
    enabled: bool = False
    # Fraction of the book's beta exposure to short (1.0 = fully neutralize beta).
    hedge_ratio: float = 1.0
    # Assumed portfolio beta to the benchmark. 1.0 is a conservative default for a
    # long equity book; a measured beta can be passed from the engine later.
    book_beta: float = 1.0
    # Per-side transaction cost on hedge rebalancing (%). Futures are cheap.
    commission_pct: float = 0.02
    # Annualized carry (roll/borrow) on the short notional, charged daily (%).
    annual_carry_pct: float = 1.0


def _benchmark_daily_returns(benchmark) -> Dict[str, float]:
    """``{iso date -> daily close-to-close return}`` for the benchmark frame."""
    if benchmark is None or len(benchmark) < 2:
        return {}
    close = benchmark["Close"].astype(float)
    out: Dict[str, float] = {}
    prev = None
    for ts, px in close.items():
        d = ts.date().isoformat() if hasattr(ts, "date") else str(ts)
        if prev is not None and prev > 0:
            out[d] = float(px) / prev - 1.0
        prev = float(px)
    return out


def apply_beta_hedge(
    equity_curve: List[dict],
    benchmark,
    cfg: HedgeConfig,
) -> List[dict]:
    """Return a NEW equity curve with a short-index beta hedge overlaid.

    For each day the hedge notional is ``hedge_ratio × book_beta ×`` the *deployed*
    long exposure (only the invested portion carries market beta; idle cash does
    not). The hedge P&L for the day is ``−hedge_notional_{t-1} × benchmark_return_t``
    (short: profits when the index falls), minus a daily carry on the short notional
    and a commission on the change in hedge notional (rebalancing turnover).

    Each snapshot gains three keys — ``hedge_pnl`` (that day's overlay P&L),
    ``hedged_equity`` (cumulative long+hedge equity) and ``hedge_notional`` — while
    the original ``equity`` field is left untouched, so downstream code that ignores
    the hedge sees the unchanged long-only curve.
    """
    out = [dict(s) for s in equity_curve]
    if not cfg.enabled or not out:
        for s in out:
            s["hedge_pnl"] = 0.0
            s["hedged_equity"] = s["equity"]
            s["hedge_notional"] = 0.0
        return out

    bench_ret = _benchmark_daily_returns(benchmark)
    daily_carry = cfg.annual_carry_pct / 100.0 / 252.0

    cum_hedge = 0.0
    prev_notional = 0.0
    for i, s in enumerate(out):
        deployed = float(s.get("deployed", 0.0))
        notional = cfg.hedge_ratio * cfg.book_beta * deployed

        pnl = 0.0
        if i > 0:
            r = bench_ret.get(s["date"], 0.0)
            # Short index: gain when the benchmark falls.
            pnl -= prev_notional * r
            # Carry on the short notional held into the day.
            pnl -= prev_notional * daily_carry
            # Rebalancing commission on the change in hedge size.
            pnl -= abs(notional - prev_notional) * cfg.commission_pct / 100.0

        cum_hedge += pnl
        s["hedge_notional"] = round(notional, 2)
        s["hedge_pnl"] = round(pnl, 2)
        s["hedged_equity"] = round(float(s["equity"]) + cum_hedge, 2)
        prev_notional = notional

    return out


def hedged_equity_series(equity_curve: List[dict]) -> List[dict]:
    """Project a hedged curve to the ``{date, equity}`` shape ``compute_metrics``
    expects, so the SAME metric code can score the hedged book. Falls back to the
    unhedged equity when the overlay wasn't applied."""
    return [
        {
            "date": s["date"],
            "equity": s.get("hedged_equity", s["equity"]),
            "cash": s.get("cash", 0.0),
            "deployed": s.get("deployed", 0.0),
            "open_positions": s.get("open_positions", 0),
        }
        for s in equity_curve
    ]


def realized_book_beta(
    equity_curve: List[dict], benchmark, *, min_obs: int = 40
) -> Optional[float]:
    """OLS beta of the long book's daily returns vs the benchmark's.

    Lets the engine replace the assumed ``book_beta`` with a measured one for a
    tighter hedge. Returns ``None`` when there is too little overlapping history or
    the benchmark has no variance (can't estimate).
    """
    bench_ret = _benchmark_daily_returns(benchmark)
    xs: List[float] = []
    ys: List[float] = []
    prev_eq = None
    for s in equity_curve:
        eq = float(s["equity"])
        if prev_eq is not None and prev_eq > 0 and s["date"] in bench_ret:
            ys.append(eq / prev_eq - 1.0)
            xs.append(bench_ret[s["date"]])
        prev_eq = eq
    if len(xs) < min_obs:
        return None
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n - 1)
    var = sum((x - mx) ** 2 for x in xs) / (n - 1)
    if var <= 0 or not math.isfinite(var):
        return None
    return cov / var
