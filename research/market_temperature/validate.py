"""Reproducible validation of the Market Temperature signal.

Regenerates the numbers quoted in VALIDATION.md and README.md. Unlike the
throwaway probe used during the original review, this exercises the **shipped**
rules in `signals.py`, so the published evidence cannot drift away from the code
that renders the dashboard.

    python -m research.market_temperature.validate
    python -m research.market_temperature.validate --markets sensex --rebalance 3

The question it answers is narrow and deliberately hostile to the strategy:

    Held to the honest benchmark - a FIXED stock/cash mix at the strategy's own
    average weight - does tilting the allocation by this signal add anything
    out-of-sample, after costs?

If the answer were yes, this module would be a strategy. It is not.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import CASH_YIELD, MARKETS, MIN_HISTORY_YEARS, Market
from .data import MarketDataUnavailable, load_market
from .signals import score_series

# One-way trading friction on turnover, in basis points.
COST_BPS = 20.0
# Extra drag applied to sells as a transparent stand-in for capital-gains tax.
# Deliberately crude: lot-level accounting would add false precision.
TAX_BPS_ON_SELL = 100.0

WEIGHT_FLOOR, WEIGHT_CAP = 0.05, 0.97
SHUFFLE_TRIALS = 300
RNG = np.random.default_rng(20260823)


@dataclass
class Outcome:
    label: str
    cagr: float
    vol: float
    sharpe: float
    max_drawdown: float
    avg_weight: float
    turnover: float
    edge_vs_constant: float
    p_value: float


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #


def simulate(weights: pd.Series, market_returns: pd.Series, *, costs: bool = True) -> pd.Series:
    """Equity curve for a weight path. `weights[t]` earns `market_returns[t]`."""
    cash_period = (1.0 + CASH_YIELD) ** (1 / 12) - 1.0
    w = weights.to_numpy()
    r = market_returns.to_numpy()
    curve = np.empty(len(w))
    previous, nav = w[0], 1.0
    for i in range(len(w)):
        if costs:
            turnover = abs(w[i] - previous)
            bps = COST_BPS + (TAX_BPS_ON_SELL if w[i] < previous else 0.0)
            nav *= 1.0 - turnover * bps / 10_000.0
        nav *= 1.0 + w[i] * r[i] + (1.0 - w[i]) * cash_period
        curve[i] = nav
        previous = w[i]
    return pd.Series(curve, index=weights.index)


def summarise(curve: pd.Series) -> dict[str, float]:
    returns = curve.pct_change().dropna()
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    cagr = (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1.0
    vol = float(returns.std() * np.sqrt(12))
    return {
        "cagr": cagr * 100.0,
        "vol": vol * 100.0,
        "sharpe": (cagr - CASH_YIELD) / vol if vol else float("nan"),
        "max_drawdown": float(((curve / curve.cummax()) - 1.0).min()) * 100.0,
    }


def shuffle_p_value(weights: pd.Series, market_returns: pd.Series, observed: float) -> float:
    """Keep the weight distribution, destroy its timing. How often does luck win?"""
    shuffled = weights.to_numpy().copy()
    wins = 0
    for _ in range(SHUFFLE_TRIALS):
        RNG.shuffle(shuffled)
        candidate = simulate(pd.Series(shuffled, index=weights.index), market_returns)
        if summarise(candidate)["cagr"] >= observed:
            wins += 1
    return (wins + 1) / (SHUFFLE_TRIALS + 1)


# --------------------------------------------------------------------------- #
# Allocation mappings
# --------------------------------------------------------------------------- #


def _expanding_z(scores: pd.Series, min_obs: int = 36) -> pd.Series:
    mean = scores.expanding(min_obs).mean()
    sd = scores.expanding(min_obs).std()
    return ((scores - mean) / sd.replace(0, np.nan)).fillna(0.0).clip(-3, 3)


def build_mappings(scores: pd.Series) -> dict[str, pd.Series]:
    """Candidate ways of turning a score into an equity weight."""
    z = _expanding_z(scores)
    raw = {
        "original_dial (+/-10pp)": 0.60 + scores * 0.05,
        "linear_k0.15": 0.60 + scores * 0.15,
        "linear_k0.30": 0.60 + scores * 0.30,
        "linear_k0.60": 0.60 + scores * 0.60,
        "linear_k1.00": 0.60 + scores * 1.00,
        "zscore_x0.10": 0.60 + z * 0.10,
        "zscore_x0.20": 0.60 + z * 0.20,
        "zscore_x0.35": 0.60 + z * 0.35,
        "ternary_30_60_90": scores.apply(
            lambda v: 0.90 if v > 0.02 else (0.30 if v < -0.02 else 0.60)
        ),
        "binary_30_90": scores.apply(lambda v: 0.90 if v > 0 else 0.30),
    }
    return {name: series.clip(WEIGHT_FLOOR, WEIGHT_CAP) for name, series in raw.items()}


def walk_forward(
    scores: pd.Series,
    market_returns: pd.Series,
    mappings: dict[str, pd.Series],
    *,
    rebalance_every: int,
) -> pd.Series:
    """Re-pick the mapping annually using only prior data, then apply it forward."""
    index = scores.index
    chosen = pd.Series(0.60, index=index)
    step = max(1, 12 // rebalance_every)
    start = max(step, int(60 / rebalance_every))
    for i in range(start, len(index), step):
        best_name, best_cagr = next(iter(mappings)), -1e9
        for name, weights in mappings.items():
            past = weights.iloc[:i]
            if len(past) < 24:
                continue
            cagr = summarise(simulate(past, market_returns.iloc[:i]))["cagr"]
            if cagr > best_cagr:
                best_cagr, best_name = cagr, name
        forward = slice(i, min(i + step, len(index)))
        chosen.iloc[forward] = mappings[best_name].iloc[forward].to_numpy()
    return chosen


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def evaluate_market(market: Market, *, rebalance_every: int = 1) -> None:
    _, total_return = load_market(market)

    dates = list(total_return.index)
    if rebalance_every > 1:
        dates = dates[::rebalance_every]

    scores = score_series(total_return, dates)
    prices = total_return.reindex(scores.index)
    market_returns = prices.pct_change().shift(-1)
    usable = market_returns.notna()
    scores, market_returns = scores[usable], market_returns[usable]

    burn_in = int(MIN_HISTORY_YEARS * 12 / rebalance_every)
    scores, market_returns = scores.iloc[burn_in:], market_returns.iloc[burn_in:]
    if len(scores) < 40:
        print(f"  {market.label}: not enough history after burn-in. Skipped.\n")
        return

    print("=" * 104)
    print(
        f"{market.label}  ({scores.index[0].date()} to {scores.index[-1].date()}, "
        f"{len(scores)} periods, rebalanced every {rebalance_every}m)"
    )
    print("=" * 104)
    print(
        f"  composite score: mean {scores.mean():+.3f}  sd {scores.std():.3f}  "
        f"range {scores.min():+.2f} to {scores.max():+.2f}  "
        f"silent {float((scores.abs() < 1e-9).mean()):.0%} of the time"
    )

    hold = summarise(simulate(pd.Series(1.0, index=scores.index), market_returns, costs=False))
    print(
        f"\n  Buy and hold 100%:  CAGR {hold['cagr']:6.2f}%  vol {hold['vol']:6.2f}%  "
        f"Sharpe {hold['sharpe']:5.2f}  maxDD {hold['max_drawdown']:7.2f}%"
    )

    mappings = build_mappings(scores)
    print(
        f"\n  {'MAPPING':<24s} {'CAGR':>7s} {'vol':>7s} {'Sharpe':>7s} {'maxDD':>8s} "
        f"{'avgW':>6s} {'turn/y':>7s} {'vs fixed mix':>13s} {'p':>6s}"
    )
    print("  " + "-" * 100)

    for name, weights in mappings.items():
        result = summarise(simulate(weights, market_returns))
        average = float(weights.mean())
        fixed = summarise(simulate(pd.Series(average, index=weights.index), market_returns))
        edge = result["cagr"] - fixed["cagr"]
        turnover = float(weights.diff().abs().sum()) / (len(weights) * rebalance_every / 12)
        p_value = shuffle_p_value(weights, market_returns, result["cagr"]) if abs(edge) > 0.05 else 1.0
        marker = "  <<<" if edge > 0.30 and p_value < 0.05 else ""
        print(
            f"  {name:<24s} {result['cagr']:6.2f}% {result['vol']:6.2f}% "
            f"{result['sharpe']:7.2f} {result['max_drawdown']:7.2f}% {average * 100:5.1f}% "
            f"{turnover * 100:6.0f}% {edge:+12.2f}pp {p_value:6.3f}{marker}"
        )

    oos_weights = walk_forward(scores, market_returns, mappings, rebalance_every=rebalance_every)
    oos = summarise(simulate(oos_weights, market_returns))
    oos_fixed = summarise(
        simulate(pd.Series(float(oos_weights.mean()), index=oos_weights.index), market_returns)
    )
    edge = oos["cagr"] - oos_fixed["cagr"]
    p_value = shuffle_p_value(oos_weights, market_returns, oos["cagr"])
    print("  " + "-" * 100)
    print(
        f"  {'WALK-FORWARD (OOS)':<24s} {oos['cagr']:6.2f}% {oos['vol']:6.2f}% "
        f"{oos['sharpe']:7.2f} {oos['max_drawdown']:7.2f}% "
        f"{oos_weights.mean() * 100:5.1f}% {'':6s}  {edge:+12.2f}pp {p_value:6.3f}"
    )

    verdict = "PASS" if edge > 0.30 and p_value < 0.05 else "FAIL"
    print(
        f"\n  VERDICT for {market.label}: {verdict}  "
        f"(requires OOS edge > +0.30pp CAGR over a fixed mix AND p < 0.05)\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markets", nargs="*", default=list(MARKETS), choices=list(MARKETS))
    parser.add_argument("--rebalance", type=int, default=1, help="Months between rebalances.")
    args = parser.parse_args()

    print("\nMarket Temperature - signal validation")
    print(
        f"Costs: {COST_BPS:.0f}bps per unit of turnover, plus {TAX_BPS_ON_SELL:.0f}bps "
        f"on sells as a tax allowance. Cash yields {CASH_YIELD:.1%}. "
        "Dividends accrued to approximate total return.\n"
    )
    for key in args.markets:
        try:
            evaluate_market(MARKETS[key], rebalance_every=args.rebalance)
        except MarketDataUnavailable as exc:
            print(f"  {MARKETS[key].label}: data unavailable - {exc}\n")


if __name__ == "__main__":
    main()
