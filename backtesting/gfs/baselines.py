"""
baselines.py
============

A backtest result means nothing on its own. "+18% CAGR" is only interesting
relative to what an *uninformative* rule would have earned in the same universe,
over the same window, with the same exposure. This module supplies those
reference points.

Four independent challenges, from cheapest to most complete:

1. :func:`buy_and_hold_curve` - could you have done as well doing nothing?

2. :func:`forward_return_study` - a pure, portfolio-free effect size. It asks
   whether the *condition itself* (monthly & weekly RSI > 60 with a daily dip)
   is followed by better returns than a random day in the same tradable
   universe. No sizing, no exits, no ranking - so it cannot be rescued or ruined
   by portfolio construction. Significance is computed on **day-averaged**
   returns, because signals fired on the same day are heavily correlated and
   treating them as independent observations inflates a t-statistic enormously.

3. :func:`random_entry_null` - a Monte Carlo that keeps the strategy's trade
   count and holding-period distribution but randomises *which* name is bought
   and *when*. If the real strategy does not land in the top tail of that
   distribution, its entries carry no information and the returns came from
   being long a rising market.

4. :func:`ablation_variants` - turn one leg off at a time to see which part of
   the strategy is actually load-bearing. It is entirely possible for the
   monthly/weekly filter to contribute nothing while the sector gate does all
   the work, or vice versa; without this you would never know.

Note on look-ahead: the forward-return study deliberately looks forward. That is
legitimate *measurement* after the fact, not a trading decision - no simulated
order is ever placed with it.
"""

import logging
import math
import random
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import (
    AblationVariant,
    EXIT_SCALE_OUT,
    EXIT_TRAIL,
    GFSConfig,
    HTF_LIVE,
    RANK_RANDOM,
    SIZING_RISK,
    STOP_PCT,
)
from .portfolio import ClosedTrade

logger = logging.getLogger("gfs.baselines")


# ── 1. Buy and hold ──────────────────────────────────────────────────────────


def buy_and_hold_curve(
    benchmark: Optional[pd.DataFrame],
    equity_curve: List[dict],
    starting_capital: float,
) -> List[dict]:
    """Benchmark buy-and-hold scaled to the same starting capital and dates."""
    if benchmark is None or benchmark.empty or not equity_curve:
        return []
    dates = [pd.Timestamp(snap["date"]) for snap in equity_curve]
    close = benchmark["Close"].reindex(pd.DatetimeIndex(dates), method="ffill")
    if close.isna().all():
        return []
    base = float(close.dropna().iloc[0])
    if base <= 0:
        return []
    out = []
    for ts, price in zip(dates, close):
        if pd.isna(price):
            continue
        out.append(
            {
                "date": ts.date().isoformat(),
                "equity": round(starting_capital * float(price) / base, 2),
                "deployed": round(starting_capital * float(price) / base, 2),
                "cash": 0.0,
            }
        )
    return out


# ── 2. Forward-return effect size ────────────────────────────────────────────


def _welch_t(a_mean, a_var, a_n, b_mean, b_var, b_n) -> Optional[float]:
    if a_n < 2 or b_n < 2:
        return None
    se = math.sqrt(a_var / a_n + b_var / b_n)
    if se <= 0:
        return None
    return (a_mean - b_mean) / se


def forward_return_study(
    panels: Dict[str, Any],
    qualify: pd.DataFrame,
    horizons: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Mean forward return after a GFS signal vs after any tradable day.

    Returns one block per horizon containing the signal mean, the baseline mean,
    the edge, and a t-statistic computed across **days** (not across individual
    signals) so cross-sectional correlation does not manufacture significance.
    """
    horizons = horizons or [5, 10, 21, 63]
    if not panels or qualify.empty:
        return {}

    results: Dict[str, Any] = {}
    for h in horizons:
        sig_by_day: Dict[pd.Timestamp, List[float]] = {}
        base_by_day: Dict[pd.Timestamp, List[float]] = {}

        for sym, panel in panels.items():
            frame = panel.frame
            close = frame["Close"]
            fwd = (close.shift(-h) / close - 1.0) * 100.0
            tradable = frame["tradable"].to_numpy()
            if sym not in qualify.columns:
                continue
            sig_mask = (
                qualify[sym].reindex(frame.index, fill_value=False).astype(bool).to_numpy()
            )
            fwd_vals = fwd.to_numpy()
            idx = frame.index

            valid = ~np.isnan(fwd_vals)
            base_sel = valid & tradable
            sig_sel = valid & sig_mask

            for ts, val in zip(idx[base_sel], fwd_vals[base_sel]):
                base_by_day.setdefault(ts, []).append(float(val))
            for ts, val in zip(idx[sig_sel], fwd_vals[sig_sel]):
                sig_by_day.setdefault(ts, []).append(float(val))

        if not sig_by_day or not base_by_day:
            continue

        # Day-level averages: one observation per trading day.
        sig_days = np.array([np.mean(v) for v in sig_by_day.values()])
        base_days = np.array([np.mean(v) for v in base_by_day.values()])
        n_signals = sum(len(v) for v in sig_by_day.values())

        results[f"h{h}"] = {
            "horizon_sessions": h,
            "num_signals": int(n_signals),
            "num_signal_days": int(len(sig_days)),
            "signal_mean_pct": round(float(sig_days.mean()), 3),
            "baseline_mean_pct": round(float(base_days.mean()), 3),
            "edge_pct": round(float(sig_days.mean() - base_days.mean()), 3),
            "signal_median_pct": round(float(np.median(sig_days)), 3),
            "t_stat_day_level": (
                round(
                    _welch_t(
                        sig_days.mean(), sig_days.var(ddof=1), len(sig_days),
                        base_days.mean(), base_days.var(ddof=1), len(base_days),
                    )
                    or 0.0,
                    2,
                )
                if len(sig_days) > 2 and len(base_days) > 2
                else None
            ),
            "signal_win_rate_pct": round(
                float((np.concatenate([np.array(v) for v in sig_by_day.values()]) > 0).mean() * 100.0),
                1,
            ),
        }
    return results


# ── 3. Random-entry Monte Carlo ──────────────────────────────────────────────


def random_entry_null(
    panels: Dict[str, Any],
    closed: List[ClosedTrade],
    cfg: GFSConfig,
    num_runs: int = 500,
) -> Dict[str, Any]:
    """Percentile rank of the strategy's average trade against random entries.

    Each simulated run buys the same number of trades as the strategy did, with
    holding periods drawn from the strategy's own realised distribution, but at
    uniformly random (symbol, tradable session) pairs. Round-trip costs are
    applied identically so the comparison is like for like.
    """
    if not closed or not panels:
        return {}

    rng = random.Random(cfg.seed + 1)
    holding = [max(t.holding_days, 1) for t in closed]
    actual_mean = sum(t.pnl_pct for t in closed) / len(closed)
    cost_pct = 2.0 * (cfg.commission_pct + cfg.slippage_bps / 100.0)

    # Pre-extract a flat pool of tradable entry points per symbol.
    pool: List[tuple] = []
    closes: Dict[str, np.ndarray] = {}
    dates: Dict[str, pd.DatetimeIndex] = {}
    for sym, panel in panels.items():
        frame = panel.frame
        mask = frame["tradable"].to_numpy()
        if not mask.any():
            continue
        closes[sym] = frame["Close"].to_numpy(dtype="float64")
        dates[sym] = frame.index
        positions = np.flatnonzero(mask)
        # Leave room for the longest holding period so exits are never clipped.
        cutoff = len(frame) - 1
        positions = positions[positions < cutoff]
        for p in positions:
            pool.append((sym, int(p)))

    if len(pool) < 50:
        return {}

    run_means: List[float] = []
    for _ in range(num_runs):
        total = 0.0
        for hold_days in holding:
            sym, start = pool[rng.randrange(len(pool))]
            index = dates[sym]
            entry_ts = index[start]
            target = entry_ts + pd.Timedelta(days=hold_days)
            exit_pos = int(index.searchsorted(target, side="left"))
            exit_pos = min(exit_pos, len(index) - 1)
            if exit_pos <= start:
                exit_pos = min(start + 1, len(index) - 1)
            entry_px = closes[sym][start]
            exit_px = closes[sym][exit_pos]
            if entry_px <= 0:
                continue
            total += (exit_px / entry_px - 1.0) * 100.0 - cost_pct
        run_means.append(total / len(holding))

    arr = np.array(run_means)
    percentile = float((arr < actual_mean).mean() * 100.0)
    return {
        "num_runs": num_runs,
        "trades_per_run": len(holding),
        "strategy_avg_trade_pct": round(actual_mean, 3),
        "random_avg_trade_pct_mean": round(float(arr.mean()), 3),
        "random_avg_trade_pct_p5": round(float(np.percentile(arr, 5)), 3),
        "random_avg_trade_pct_p95": round(float(np.percentile(arr, 95)), 3),
        "strategy_percentile_vs_random": round(percentile, 1),
        "beats_random_at_95pct": bool(percentile >= 95.0),
    }


# ── 4. Ablations ─────────────────────────────────────────────────────────────


def ablation_variants() -> List[AblationVariant]:
    """Named single-change variants that isolate each leg of the strategy."""
    return [
        AblationVariant(
            name="baseline",
            question="The strategy exactly as stated (60/60/40, RSI exit).",
            overrides={},
        ),
        AblationVariant(
            name="no_grandfather_father",
            question="Does the monthly+weekly RSI filter add anything, or is the "
            "daily dip doing all the work?",
            overrides={"g_rsi_min": 0.0, "f_rsi_min": 0.0},
        ),
        AblationVariant(
            name="no_son_dip",
            question="Does waiting for the daily dip add anything, or would "
            "buying strong stocks on any day do as well?",
            overrides={"s_rsi_entry": 100.0},
        ),
        AblationVariant(
            name="no_sector_gate",
            question="Is the aerial (sector relative strength) view load-bearing?",
            overrides={"use_sector_filter": False},
        ),
        AblationVariant(
            name="no_regime_gate",
            question="Is the helicopter (market regime) view load-bearing, or "
            "does it just cost you the recovery?",
            overrides={"use_regime_filter": False},
        ),
        AblationVariant(
            name="random_ranking",
            question="Does the composite ranking beat picking at random from the "
            "same qualifying pool?",
            overrides={"rank_by": RANK_RANDOM},
        ),
        AblationVariant(
            name="tight_pct_stop",
            question="What does the stated 3-5% stop actually do to the edge?",
            overrides={"stop_mode": STOP_PCT, "fixed_stop_pct": 4.0},
        ),
        AblationVariant(
            name="scale_out_and_trail",
            question="Does booking half at the RSI target and trailing the rest "
            "fix the payoff ratio?",
            overrides={"exit_mode": EXIT_SCALE_OUT},
        ),
        AblationVariant(
            name="pure_trail_exit",
            question="Is the RSI exit better or worse than simply trailing?",
            overrides={"exit_mode": EXIT_TRAIL},
        ),
        AblationVariant(
            name="risk_based_sizing",
            question="Equal allocation (as the strategy states) vs sizing by "
            "distance-to-stop.",
            overrides={"sizing_mode": SIZING_RISK},
        ),
        AblationVariant(
            name="live_htf_candles",
            question="How much does reading the in-progress monthly/weekly candle "
            "change the result versus waiting for it to close?",
            overrides={"htf_mode": HTF_LIVE},
        ),
    ]


def render_forward_study(study: Dict[str, Any]) -> str:
    if not study:
        return ""
    lines = [
        "-" * 68,
        " FORWARD-RETURN STUDY - the condition on its own (no portfolio)",
        f" {'horizon':<9}{'signals':>9}{'signal':>10}{'baseline':>10}{'edge':>9}{'t(day)':>9}",
    ]
    for key in sorted(study, key=lambda k: study[k]["horizon_sessions"]):
        row = study[key]
        t = row["t_stat_day_level"]
        lines.append(
            f" {row['horizon_sessions']:>3}d     {row['num_signals']:>9,}"
            f"{row['signal_mean_pct']:>9.2f}%{row['baseline_mean_pct']:>9.2f}%"
            f"{row['edge_pct']:>+8.2f}%{(t if t is not None else 0):>9.2f}"
        )
    lines.append(
        " (|t| < 2 at day level means the edge is not distinguishable from noise)"
    )
    return "\n".join(lines)


def render_random_null(null: Dict[str, Any]) -> str:
    if not null:
        return ""
    verdict = (
        "PASSES - entries carry information"
        if null["beats_random_at_95pct"]
        else "FAILS - indistinguishable from random entry in the same universe"
    )
    return "\n".join(
        [
            "-" * 68,
            " RANDOM-ENTRY MONTE CARLO",
            f" Strategy avg trade      : {null['strategy_avg_trade_pct']:+.2f}%",
            f" Random avg trade (mean) : {null['random_avg_trade_pct_mean']:+.2f}%"
            f"   [p5 {null['random_avg_trade_pct_p5']:+.2f}%,"
            f" p95 {null['random_avg_trade_pct_p95']:+.2f}%]",
            f" Strategy percentile     : {null['strategy_percentile_vs_random']:.1f}"
            f"   ({null['num_runs']} runs)",
            f" Verdict                 : {verdict}",
        ]
    )
