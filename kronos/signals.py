"""Turn Kronos candlestick forecasts into a trading *signal*.

Kronos forecasts future OHLCV candles; it does **not** emit buy/sell calls. This
module is the (pure, dependency-light) layer that converts one or more sampled
forecast paths into an actionable, risk-aware signal.

Design principle (see the report): trust the forecast **distribution and
direction**, not the exact predicted price. So we derive:

* ``expected_return``  – mean terminal return across sampled paths.
* ``prob_up``          – fraction of paths finishing above the last close.
* a **volatility cone** (predicted high/low) → forward-looking stop & target.
* a discrete ``direction`` (BUY / HOLD / AVOID) gated by conviction + reward:risk.

Everything here is deterministic given its inputs, so it is unit-testable
offline with hand-built forecast frames — no torch, no network, no GPU.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import fmean, pstdev
from typing import Any, Dict, List, Sequence

import pandas as pd


@dataclass
class KronosSignal:
    """Actionable, risk-aware summary derived from Kronos forecasts."""

    symbol: str
    last_close: float
    horizon: int

    expected_return: float  # mean terminal return (fraction, e.g. 0.03 = +3%)
    prob_up: float  # P(terminal close > last close), in [0, 1]
    expected_close: float  # mean predicted terminal close price

    predicted_high: float  # mean of per-path max highs (upper cone)
    predicted_low: float  # mean of per-path min lows (lower cone)
    forecast_volatility: float  # stdev of terminal returns across paths

    suggested_stop: float
    suggested_target: float
    reward_risk: float

    direction: str  # "BUY" | "HOLD" | "AVOID"
    confidence: str  # "LOW" | "MEDIUM" | "HIGH"
    n_paths: int
    rationale: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Tunable thresholds for turning a probabilistic forecast into a discrete call.
# Deliberately conservative: Kronos edges are small, so we only act on
# reasonably confident, favourably-skewed setups.
BUY_PROB_UP = 0.58
AVOID_PROB_UP = 0.42
BUY_MIN_EXPECTED_RETURN = 0.005  # +0.5% expected over the horizon
BUY_MIN_REWARD_RISK = 1.5

HIGH_CONF_PROB = 0.66
MED_CONF_PROB = 0.58


def _terminal_close(path: pd.DataFrame) -> float:
    return float(path["close"].iloc[-1])


def _path_high(path: pd.DataFrame) -> float:
    col = "high" if "high" in path.columns else "close"
    return float(path[col].max())


def _path_low(path: pd.DataFrame) -> float:
    col = "low" if "low" in path.columns else "close"
    return float(path[col].min())


def _confidence(prob_up: float) -> str:
    directional = max(prob_up, 1.0 - prob_up)
    if directional >= HIGH_CONF_PROB:
        return "HIGH"
    if directional >= MED_CONF_PROB:
        return "MEDIUM"
    return "LOW"


def derive_signal(
    symbol: str,
    last_close: float,
    forecast_paths: Sequence[pd.DataFrame],
    *,
    horizon: int | None = None,
) -> KronosSignal:
    """Convert sampled Kronos forecast paths into a :class:`KronosSignal`.

    Parameters
    ----------
    symbol:
        Ticker the forecast is for (for labelling only).
    last_close:
        The most recent actual close — the reference point for returns and the
        assumed entry price.
    forecast_paths:
        One or more forecast DataFrames, each with a ``close`` column (``high`` /
        ``low`` optional but recommended for the volatility cone). Each frame is
        one stochastic path of length ``pred_len``.
    horizon:
        Forecast length in bars; inferred from the first path when omitted.
    """
    if last_close <= 0:
        raise ValueError("last_close must be positive")
    paths = [p for p in forecast_paths if p is not None and len(p) > 0]
    if not paths:
        raise ValueError("forecast_paths must contain at least one non-empty path")

    if horizon is None:
        horizon = int(len(paths[0]))

    terminals = [_terminal_close(p) for p in paths]
    returns = [(tc / last_close) - 1.0 for tc in terminals]

    expected_return = fmean(returns)
    expected_close = fmean(terminals)
    prob_up = sum(1 for r in returns if r > 0) / len(returns)
    forecast_volatility = pstdev(returns) if len(returns) > 1 else 0.0

    predicted_high = fmean([_path_high(p) for p in paths])
    predicted_low = fmean([_path_low(p) for p in paths])

    # Volatility cone → risk levels. Stop below the expected downside, target at
    # the expected upside. Falls back to a volatility band if the cone is degenerate.
    band = max(forecast_volatility, 1e-9) * last_close
    suggested_stop = min(predicted_low, last_close - band)
    suggested_target = max(predicted_high, expected_close)

    risk = max(last_close - suggested_stop, 1e-9)
    reward = max(suggested_target - last_close, 0.0)
    reward_risk = reward / risk

    direction, rationale = _decide(
        prob_up=prob_up,
        expected_return=expected_return,
        reward_risk=reward_risk,
    )
    confidence = _confidence(prob_up)

    return KronosSignal(
        symbol=symbol,
        last_close=round(last_close, 4),
        horizon=horizon,
        expected_return=round(expected_return, 6),
        prob_up=round(prob_up, 4),
        expected_close=round(expected_close, 4),
        predicted_high=round(predicted_high, 4),
        predicted_low=round(predicted_low, 4),
        forecast_volatility=round(forecast_volatility, 6),
        suggested_stop=round(suggested_stop, 4),
        suggested_target=round(suggested_target, 4),
        reward_risk=round(reward_risk, 3),
        direction=direction,
        confidence=confidence,
        n_paths=len(paths),
        rationale=rationale,
    )


def _decide(*, prob_up: float, expected_return: float, reward_risk: float) -> tuple[str, str]:
    if (
        prob_up >= BUY_PROB_UP
        and expected_return >= BUY_MIN_EXPECTED_RETURN
        and reward_risk >= BUY_MIN_REWARD_RISK
    ):
        return (
            "BUY",
            f"P(up)={prob_up:.0%} with +{expected_return:.1%} expected and "
            f"{reward_risk:.1f}:1 reward:risk clears the entry bar.",
        )
    if prob_up <= AVOID_PROB_UP or expected_return <= -BUY_MIN_EXPECTED_RETURN:
        return (
            "AVOID",
            f"Downward skew: P(up)={prob_up:.0%}, expected {expected_return:+.1%} "
            "— stay out / consider exit.",
        )
    return (
        "HOLD",
        f"Inconclusive: P(up)={prob_up:.0%}, expected {expected_return:+.1%}, "
        f"reward:risk {reward_risk:.1f}:1 — no strong edge.",
    )


def signals_to_frame(signals: List[KronosSignal]) -> pd.DataFrame:
    """Tabulate signals for reporting / ranking (best BUY conviction first)."""
    if not signals:
        return pd.DataFrame()
    df = pd.DataFrame([s.to_dict() for s in signals])
    order = {"BUY": 0, "HOLD": 1, "AVOID": 2}
    df["_rank"] = df["direction"].map(order).fillna(3)
    df = df.sort_values(
        ["_rank", "prob_up", "expected_return"], ascending=[True, False, False]
    ).drop(columns="_rank")
    return df.reset_index(drop=True)


__all__ = ["KronosSignal", "derive_signal", "signals_to_frame"]
