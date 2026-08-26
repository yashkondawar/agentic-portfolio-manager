"""
metrics.py
==========

Performance measurement and the diagnostics that make a result *interpretable*
rather than merely impressive.

Beyond the usual CAGR / drawdown / Sharpe block, three sections exist because
they answer questions this specific strategy raises:

``payoff``
    A pullback-into-strength system should produce a *high win rate with small
    winners*. If a run shows the opposite, the exit rule is not doing what the
    strategy claims. Expectancy is reported in R so it is comparable across
    configurations with different stop widths.

``excursions``
    MAE / MFE. The share of eventual **winners** that first traded through
    -3% and -5% directly answers "is a tight stop harvesting noise?" If most
    winners dip below a candidate stop before working, that stop converts
    winners into losers and the strategy's own risk rule is wrong. Note the
    deliberate absence of a "-1R" version of this statistic - see
    :func:`_excursion_stats` for why it would be vacuous.

``exit_attribution``
    P&L grouped by exit reason. If nearly all profit arrives via ``rsi_target``
    the exit is fine; if the trailing stop quietly carries the strategy, the
    stated exit rule is not the source of the edge.
"""

import math
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from .portfolio import ClosedTrade

TRADING_DAYS = 252


def _drawdown_stats(equity_curve: List[dict]) -> Dict[str, Any]:
    peak = -math.inf
    max_dd = 0.0
    peak_date: Optional[str] = None
    trough_date: Optional[str] = None
    cur_peak_date: Optional[str] = None
    longest = 0
    since_peak = 0
    for snap in equity_curve:
        eq = snap["equity"]
        if eq >= peak:
            peak = eq
            cur_peak_date = snap["date"]
            since_peak = 0
        else:
            since_peak += 1
            longest = max(longest, since_peak)
        if peak > 0:
            dd = (eq - peak) / peak * 100.0
            if dd < max_dd:
                max_dd = dd
                peak_date = cur_peak_date
                trough_date = snap["date"]
    return {
        "max_drawdown_pct": round(max_dd, 2),
        "max_drawdown_peak": peak_date,
        "max_drawdown_trough": trough_date,
        "longest_drawdown_days": longest,
    }


def daily_returns(equity_curve: List[dict]) -> List[float]:
    out = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]["equity"]
        cur = equity_curve[i]["equity"]
        if prev > 0:
            out.append(cur / prev - 1.0)
    return out


def _risk_stats(rets: List[float]) -> Dict[str, float]:
    if len(rets) < 2:
        return {"sharpe": 0.0, "sortino": 0.0, "annual_vol_pct": 0.0}
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    std = math.sqrt(var)
    downs = [r for r in rets if r < 0]
    downside = math.sqrt(sum(r * r for r in downs) / len(rets)) if downs else 0.0
    return {
        "sharpe": round(mean / std * math.sqrt(TRADING_DAYS), 2) if std > 0 else 0.0,
        "sortino": round(mean / downside * math.sqrt(TRADING_DAYS), 2) if downside > 0 else 0.0,
        "annual_vol_pct": round(std * math.sqrt(TRADING_DAYS) * 100.0, 2),
    }


def _payoff_stats(closed: List[ClosedTrade]) -> Dict[str, Any]:
    n = len(closed)
    if n == 0:
        return {"num_trades": 0}
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    avg_win_pct = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0.0
    avg_loss_pct = sum(t.pnl_pct for t in losses) / len(losses) if losses else 0.0
    r_values = [t.r_multiple for t in closed]
    win_rate = len(wins) / n
    return {
        "num_trades": n,
        "win_rate_pct": round(win_rate * 100.0, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "payoff_ratio": round(abs(avg_win_pct / avg_loss_pct), 2) if avg_loss_pct else None,
        "expectancy_r": round(sum(r_values) / n, 3),
        "expectancy_pct": round(sum(t.pnl_pct for t in closed) / n, 2),
        "best_trade_pct": round(max(t.pnl_pct for t in closed), 2),
        "worst_trade_pct": round(min(t.pnl_pct for t in closed), 2),
        "avg_holding_days": round(sum(t.holding_days for t in closed) / n, 1),
        "median_holding_days": round(_median([t.holding_days for t in closed]), 1),
    }


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _excursion_stats(closed: List[ClosedTrade]) -> Dict[str, Any]:
    """Does a tight stop sit inside the noise of trades that eventually work?

    The point of this block is the user's stated risk rule: a fixed 3-5% stop.
    ``winners_that_dipped_below_3pct`` answers it directly - those are trades
    that made money but would have been stopped out first by a 3% stop.

    A caution on what is *not* here. "Share of winners whose MAE reached -1R"
    is a natural-sounding statistic and a worthless one: a trade that reaches
    -1R has touched its stop and been closed as a loser, so the answer is 0.0%
    no matter what the market did. It measures the harness, not the strategy.
    The honest near-miss version is ``winners_that_came_within_80pct_of_stop``,
    which counts winners that got most of the way to the stop without touching
    it - the trades a slightly tighter stop would have destroyed.
    """
    winners = [t for t in closed if t.pnl > 0]
    losers = [t for t in closed if t.pnl <= 0]
    if not closed:
        return {}

    def share_below(trades: List[ClosedTrade], threshold_pct: float) -> Optional[float]:
        if not trades:
            return None
        hit = sum(1 for t in trades if t.mae_pct <= threshold_pct)
        return round(hit / len(trades) * 100.0, 1)

    return {
        "median_mae_pct_all": round(_median([t.mae_pct for t in closed]), 2),
        "median_mae_pct_winners": round(_median([t.mae_pct for t in winners]), 2) if winners else None,
        "median_mfe_pct_winners": round(_median([t.mfe_pct for t in winners]), 2) if winners else None,
        "median_mfe_pct_losers": round(_median([t.mfe_pct for t in losers]), 2) if losers else None,
        "winners_that_dipped_below_3pct": share_below(winners, -3.0),
        "winners_that_dipped_below_5pct": share_below(winners, -5.0),
        "winners_that_came_within_80pct_of_stop": (
            round(sum(1 for t in winners if t.mae_r <= -0.8) / len(winners) * 100.0, 1)
            if winners
            else None
        ),
        "median_mae_r_winners": round(_median([t.mae_r for t in winners]), 2) if winners else None,
    }


def _exit_attribution(closed: List[ClosedTrade]) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[ClosedTrade]] = defaultdict(list)
    for trade in closed:
        buckets[trade.exit_reason].append(trade)
    rows = []
    total_pnl = sum(t.pnl for t in closed) or 1.0
    for reason, trades in buckets.items():
        pnl = sum(t.pnl for t in trades)
        rows.append(
            {
                "exit_reason": reason,
                "count": len(trades),
                "share_pct": round(len(trades) / len(closed) * 100.0, 1),
                "total_pnl": round(pnl, 2),
                "pnl_share_pct": round(pnl / total_pnl * 100.0, 1),
                "avg_pnl_pct": round(sum(t.pnl_pct for t in trades) / len(trades), 2),
                "avg_holding_days": round(
                    sum(t.holding_days for t in trades) / len(trades), 1
                ),
            }
        )
    return sorted(rows, key=lambda r: r["count"], reverse=True)


def _yearly_returns(equity_curve: List[dict]) -> List[Dict[str, Any]]:
    by_year: Dict[int, List[dict]] = defaultdict(list)
    for snap in equity_curve:
        by_year[date.fromisoformat(snap["date"]).year].append(snap)
    rows = []
    prev_close: Optional[float] = None
    for year in sorted(by_year):
        snaps = by_year[year]
        start_eq = prev_close if prev_close is not None else snaps[0]["equity"]
        end_eq = snaps[-1]["equity"]
        rows.append(
            {
                "year": year,
                "return_pct": round((end_eq / start_eq - 1.0) * 100.0, 2)
                if start_eq
                else 0.0,
                "end_equity": round(end_eq, 2),
                "avg_exposure_pct": round(
                    sum(s["deployed"] / s["equity"] * 100.0 for s in snaps if s["equity"] > 0)
                    / max(len(snaps), 1),
                    1,
                ),
            }
        )
        prev_close = end_eq
    return rows


def compute_metrics(
    equity_curve: List[dict],
    closed: List[ClosedTrade],
    starting_capital: float,
    benchmark_curve: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    if not equity_curve:
        return {}

    end_eq = equity_curve[-1]["equity"]
    d0 = date.fromisoformat(equity_curve[0]["date"])
    d1 = date.fromisoformat(equity_curve[-1]["date"])
    years = max((d1 - d0).days / 365.25, 1e-9)
    rets = daily_returns(equity_curve)

    exposure = [s["deployed"] / s["equity"] for s in equity_curve if s["equity"] > 0]
    metrics: Dict[str, Any] = {
        "start_date": d0.isoformat(),
        "end_date": d1.isoformat(),
        "years": round(years, 2),
        "start_equity": round(starting_capital, 2),
        "end_equity": round(end_eq, 2),
        "total_return_pct": round((end_eq / starting_capital - 1.0) * 100.0, 2),
        "cagr_pct": round(((end_eq / starting_capital) ** (1 / years) - 1.0) * 100.0, 2),
        "avg_exposure_pct": round(sum(exposure) / len(exposure) * 100.0, 1) if exposure else 0.0,
    }
    metrics.update(_drawdown_stats(equity_curve))
    metrics.update(_risk_stats(rets))
    metrics.update(_payoff_stats(closed))
    if metrics.get("max_drawdown_pct"):
        metrics["calmar"] = round(
            metrics["cagr_pct"] / abs(metrics["max_drawdown_pct"]), 2
        )

    metrics["excursions"] = _excursion_stats(closed)
    metrics["exit_attribution"] = _exit_attribution(closed)
    metrics["yearly"] = _yearly_returns(equity_curve)

    if benchmark_curve:
        bench_end = benchmark_curve[-1]["equity"]
        bench_cagr = ((bench_end / starting_capital) ** (1 / years) - 1.0) * 100.0
        bench_dd = _drawdown_stats(benchmark_curve)["max_drawdown_pct"]
        metrics["benchmark"] = {
            "cagr_pct": round(bench_cagr, 2),
            "total_return_pct": round((bench_end / starting_capital - 1.0) * 100.0, 2),
            "max_drawdown_pct": bench_dd,
            "excess_cagr_pct": round(metrics["cagr_pct"] - bench_cagr, 2),
        }
    return metrics


# ── Rendering ────────────────────────────────────────────────────────────────


def render_summary(
    metrics: Dict[str, Any],
    cfg_summary: str = "",
    signal_stats: Optional[Dict[str, Any]] = None,
    rejections: Optional[Dict[str, int]] = None,
) -> str:
    if not metrics:
        return "No results - the run produced no equity curve."

    line = "-" * 68
    out: List[str] = [
        "=" * 68,
        " GFS BACKTEST - SUMMARY",
        "=" * 68,
    ]
    if cfg_summary:
        out += [cfg_summary, line]

    pf = metrics.get("profit_factor")
    payoff = metrics.get("payoff_ratio")
    out += [
        f" Window              : {metrics['start_date']} -> {metrics['end_date']}"
        f"  ({metrics['years']}y)",
        f" Start / end equity  : Rs {metrics['start_equity']:,.0f} -> Rs {metrics['end_equity']:,.0f}",
        f" Total return        : {metrics['total_return_pct']:+.2f}%",
        f" CAGR                : {metrics['cagr_pct']:+.2f}%",
        f" Max drawdown        : {metrics['max_drawdown_pct']:.2f}%"
        f"   (longest {metrics['longest_drawdown_days']} sessions under water)",
        f" Sharpe / Sortino    : {metrics['sharpe']:.2f} / {metrics['sortino']:.2f}",
        f" Calmar              : {metrics.get('calmar', 'n/a')}",
        f" Avg exposure        : {metrics['avg_exposure_pct']:.1f}%",
    ]

    if "benchmark" in metrics:
        b = metrics["benchmark"]
        out += [
            line,
            " BASELINE - buy & hold the benchmark",
            f" Benchmark CAGR      : {b['cagr_pct']:+.2f}%"
            f"   (max DD {b['max_drawdown_pct']:.2f}%)",
            f" Excess CAGR         : {b['excess_cagr_pct']:+.2f}%"
            f"   {'<-- strategy adds nothing' if b['excess_cagr_pct'] <= 0 else ''}",
        ]

    out += [
        line,
        " TRADES",
        f" Closed trades       : {metrics.get('num_trades', 0)}",
        f" Win rate            : {metrics.get('win_rate_pct', 0):.2f}%",
        f" Profit factor       : {pf if pf is not None else 'inf'}",
        f" Avg win / avg loss  : {metrics.get('avg_win_pct', 0):+.2f}% / "
        f"{metrics.get('avg_loss_pct', 0):+.2f}%   (payoff {payoff if payoff else 'n/a'})",
        f" Expectancy          : {metrics.get('expectancy_r', 0):+.3f} R  "
        f"({metrics.get('expectancy_pct', 0):+.2f}% per trade)",
        f" Holding (avg/med)   : {metrics.get('avg_holding_days', 0)} / "
        f"{metrics.get('median_holding_days', 0)} days",
    ]

    exc = metrics.get("excursions") or {}
    if exc:
        out += [
            line,
            " EXCURSIONS - is a tight stop inside the noise?",
            f" Median MAE (all)          : {exc.get('median_mae_pct_all')}%",
            f" Median MAE (winners)      : {exc.get('median_mae_pct_winners')}%",
            f" Winners that first fell >3% : {exc.get('winners_that_dipped_below_3pct')}%",
            f" Winners that first fell >5% : {exc.get('winners_that_dipped_below_5pct')}%",
            f" Winners that came within 80% of stop : "
            f"{exc.get('winners_that_came_within_80pct_of_stop')}%",
            f" Median MAE of winners, in R : {exc.get('median_mae_r_winners')}",
        ]

    attribution = metrics.get("exit_attribution") or []
    if attribution:
        out += [line, " EXIT ATTRIBUTION"]
        for row in attribution:
            out.append(
                f"  {row['exit_reason']:<16} n={row['count']:<5} "
                f"{row['share_pct']:>5.1f}% of trades  "
                f"{row['pnl_share_pct']:>7.1f}% of P&L  "
                f"avg {row['avg_pnl_pct']:+.2f}%"
            )

    yearly = metrics.get("yearly") or []
    if yearly:
        out += [line, " YEAR BY YEAR"]
        for row in yearly:
            out.append(
                f"  {row['year']}   {row['return_pct']:+7.2f}%   "
                f"equity Rs {row['end_equity']:>12,.0f}   "
                f"exposure {row['avg_exposure_pct']:>5.1f}%"
            )

    if signal_stats:
        out += [
            line,
            " SIGNAL FREQUENCY - does the setup even appear?",
            f" Avg qualifying names/day : {signal_stats.get('avg_qualifying_per_day')}",
            f" Peak in a single day     : {signal_stats.get('max_qualifying_in_a_day')}",
            f" Days with zero signals   : {signal_stats.get('days_with_zero_signals')}"
            f" / {signal_stats.get('sessions')}",
            f" Days regime gate open    : {signal_stats.get('pct_days_regime_open')}%",
        ]

    if rejections:
        top = sorted(rejections.items(), key=lambda kv: kv[1], reverse=True)[:8]
        out += [line, " WHY CANDIDATES WERE DROPPED"]
        for reason, count in top:
            out.append(f"  {reason:<20} {count:,}")

    out.append("=" * 68)
    return "\n".join(out)
