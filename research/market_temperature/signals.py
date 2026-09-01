"""Clean-room implementations of the countercyclical price rules.

These are rewritten from the rules' stated definitions, not ported from the
original source, which contained several bugs that inverted its own intent:

* The 3-year "accumulation" band was one-sided (``ret <= +10%``), so a 65%
  crash was classified as a quiet sideways market and scored bullish. Here the
  band is two-sided.
* The correction rule used the *maximum* drawdown observed anywhere inside a
  trailing window, so it still fired after the market had fully recovered.
  Here it measures the drawdown that is live *right now*.
* Window arithmetic used ``pd.DateOffset(years=<float>)``, which raises on any
  non-integer year. Here all windows are day offsets.
* Unevaluable rules were dropped from the weighted average's denominator, so the
  composite silently changed meaning as history accumulated. Here they score
  zero but stay in the denominator, keeping the score comparable across decades.

Every function returns ``None`` when there is not enough history to answer
honestly. Nothing here fabricates or substitutes data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

from .config import RULE_SPECS

DAYS_PER_YEAR = 365.25
DAYS_PER_MONTH = 30.44


# --------------------------------------------------------------------------- #
# Window primitives
# --------------------------------------------------------------------------- #


def trailing_return_pct(
    series: pd.Series, asof: pd.Timestamp, years: float
) -> Optional[float]:
    """Cumulative percentage return over the trailing `years` ending at `asof`."""
    start = asof - pd.Timedelta(days=int(round(DAYS_PER_YEAR * years)))
    history = series[series.index <= asof]
    if history.empty or history.index[0] > start:
        return None
    prior = history[history.index <= start]
    if prior.empty or prior.iloc[-1] <= 0:
        return None
    return float(history.iloc[-1] / prior.iloc[-1] - 1.0) * 100.0


def trailing_cagr_pct(
    series: pd.Series, asof: pd.Timestamp, years: float
) -> Optional[float]:
    """Annualised percentage return over the trailing `years` ending at `asof`."""
    total = trailing_return_pct(series, asof, years)
    if total is None or (1.0 + total / 100.0) <= 0:
        return None
    return ((1.0 + total / 100.0) ** (1.0 / years) - 1.0) * 100.0


def current_drawdown_pct(
    series: pd.Series, asof: pd.Timestamp, months: int = 12
) -> Optional[float]:
    """How far below its trailing peak the market sits *right now*, as a positive %.

    This deliberately compares the latest price to the window peak. Using the
    maximum drawdown seen anywhere within the window would keep reporting a
    crash long after the recovery, which is what the original implementation did.
    """
    start = asof - pd.Timedelta(days=int(round(DAYS_PER_MONTH * months)))
    window = series[(series.index <= asof) & (series.index >= start)]
    if len(window) < 3:
        return None
    peak = float(window.max())
    if peak <= 0:
        return None
    return float((window.iloc[-1] / peak - 1.0) * -100.0)


# --------------------------------------------------------------------------- #
# Rule evaluation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RuleReading:
    """One rule's verdict at a point in time, with the number behind it."""

    key: str
    label: str
    weight: float
    score: Optional[float]
    observed: Optional[float]
    observed_label: str
    verdict: str
    detail: str

    @property
    def evaluable(self) -> bool:
        return self.score is not None

    @property
    def contribution(self) -> float:
        return 0.0 if self.score is None else self.weight * self.score


def _reading(
    key: str,
    score: Optional[float],
    observed: Optional[float],
    observed_label: str,
    detail: str,
) -> RuleReading:
    spec = RULE_SPECS[key]
    if score is None:
        verdict = "Not enough history"
    elif score > 0:
        verdict = "Bullish"
    elif score < 0:
        verdict = "Bearish"
    else:
        verdict = "Quiet"
    return RuleReading(
        key=key,
        label=spec.label,
        weight=spec.weight,
        score=score,
        observed=observed,
        observed_label=observed_label,
        verdict=verdict,
        detail=detail,
    )


def rule_12y_flat(series: pd.Series, asof: pd.Timestamp) -> RuleReading:
    ret = trailing_return_pct(series, asof, 12)
    if ret is None:
        return _reading("12y_flat", None, None, "12y total return", "Needs 12y of data.")
    fired = abs(ret) <= 15.0
    return _reading(
        "12y_flat",
        2.0 if fired else 0.0,
        ret,
        "12y total return",
        (
            f"Up {ret:.0f}% over 12 years — effectively a lost decade."
            if fired
            else f"Up {ret:.0f}% over 12 years; not a stagnant market."
        ),
    )


def rule_10y_hot(series: pd.Series, asof: pd.Timestamp) -> RuleReading:
    cagr = trailing_cagr_pct(series, asof, 10)
    if cagr is None:
        return _reading("10y_hot", None, None, "10y CAGR", "Needs 10y of data.")
    score = -2.0 if cagr >= 28.0 else (-1.0 if cagr >= 20.0 else 0.0)
    return _reading(
        "10y_hot",
        score,
        cagr,
        "10y CAGR",
        (
            f"Compounded {cagr:.1f}%/yr for a decade — a hot base to extrapolate from."
            if score < 0
            else f"Compounded {cagr:.1f}%/yr for a decade; unremarkable."
        ),
    )


def rule_8y_flat(series: pd.Series, asof: pd.Timestamp) -> RuleReading:
    ret = trailing_return_pct(series, asof, 8)
    if ret is None:
        return _reading("8y_flat", None, None, "8y total return", "Needs 8y of data.")
    fired = abs(ret) <= 15.0
    return _reading(
        "8y_flat",
        1.0 if fired else 0.0,
        ret,
        "8y total return",
        (
            f"Up {ret:.0f}% over 8 years — prolonged stagnation."
            if fired
            else f"Up {ret:.0f}% over 8 years; not stagnant."
        ),
    )


def rule_5y_vs_cash(series: pd.Series, asof: pd.Timestamp) -> RuleReading:
    cagr = trailing_cagr_pct(series, asof, 5)
    if cagr is None:
        return _reading("5y_vs_cash", None, None, "5y CAGR", "Needs 5y of data.")
    fired = cagr < 6.5
    return _reading(
        "5y_vs_cash",
        1.0 if fired else 0.0,
        cagr,
        "5y CAGR",
        (
            f"{cagr:.1f}%/yr over 5 years — equity has not beaten a savings account."
            if fired
            else f"{cagr:.1f}%/yr over 5 years, comfortably ahead of cash."
        ),
    )


def rule_3y_flat(series: pd.Series, asof: pd.Timestamp) -> RuleReading:
    """Two-sided band. A crash is not a sideways market."""
    ret = trailing_return_pct(series, asof, 3)
    if ret is None:
        return _reading("3y_flat", None, None, "3y total return", "Needs 3y of data.")
    fired = -10.0 <= ret <= 10.0
    if fired:
        detail = f"{ret:+.0f}% over 3 years — genuinely sideways."
    elif ret < -10.0:
        detail = f"{ret:+.0f}% over 3 years — this is a decline, not a drift."
    else:
        detail = f"{ret:+.0f}% over 3 years — trending, not consolidating."
    return _reading("3y_flat", 1.0 if fired else 0.0, ret, "3y total return", detail)


def rule_bubble(series: pd.Series, asof: pd.Timestamp) -> RuleReading:
    one = trailing_return_pct(series, asof, 1)
    two = trailing_return_pct(series, asof, 2)
    candidates = [value for value in (one, two) if value is not None]
    if not candidates:
        return _reading("bubble", None, None, "best of 1y / 2y return", "Needs 1y of data.")
    peak = max(candidates)
    fired = peak >= 200.0
    return _reading(
        "bubble",
        -2.0 if fired else 0.0,
        peak,
        "best of 1y / 2y return",
        (
            f"Up {peak:.0f}% in under two years — a parabolic move."
            if fired
            else f"Best 1-2y gain is {peak:+.0f}%; nowhere near parabolic."
        ),
    )


def rule_drawdown(series: pd.Series, asof: pd.Timestamp) -> RuleReading:
    drawdown = current_drawdown_pct(series, asof, months=12)
    if drawdown is None:
        return _reading("drawdown", None, None, "drawdown from 1y peak", "Needs 1y of data.")
    fired = 30.0 <= drawdown <= 55.0
    if fired:
        detail = f"Currently {drawdown:.0f}% below the 1-year peak — a live deep correction."
    elif drawdown > 55.0:
        detail = (
            f"Currently {drawdown:.0f}% below peak — beyond the band. A decline this "
            "severe may signal something structural rather than a buying opportunity."
        )
    else:
        detail = f"Currently {drawdown:.0f}% below the 1-year peak."
    return _reading("drawdown", 2.0 if fired else 0.0, drawdown, "drawdown from 1y peak", detail)


RULE_FUNCS: dict[str, Callable[[pd.Series, pd.Timestamp], RuleReading]] = {
    "12y_flat": rule_12y_flat,
    "10y_hot": rule_10y_hot,
    "8y_flat": rule_8y_flat,
    "5y_vs_cash": rule_5y_vs_cash,
    "3y_flat": rule_3y_flat,
    "bubble": rule_bubble,
    "drawdown": rule_drawdown,
}

TOTAL_WEIGHT = sum(spec.weight for spec in RULE_SPECS.values())


def evaluate_rules(series: pd.Series, asof: pd.Timestamp) -> list[RuleReading]:
    """Run every rule at `asof`, in declared order."""
    return [RULE_FUNCS[key](series, asof) for key in RULE_SPECS]


def composite_score(readings: list[RuleReading]) -> float:
    """Weighted average vote on a -2..+2 scale, positive meaning cheap.

    The denominator is the *full* weight of all rules, including those that could
    not be evaluated. That keeps a score from 2005 comparable to one from 2026.
    """
    return sum(reading.contribution for reading in readings) / TOTAL_WEIGHT


def score_series(series: pd.Series, dates) -> pd.Series:
    """Composite score at each date in `dates`."""
    return pd.Series(
        {date: composite_score(evaluate_rules(series, date)) for date in dates},
        dtype=float,
    )
