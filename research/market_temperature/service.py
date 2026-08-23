"""Assembly of the Market Temperature reading and its supporting evidence.

The headline number is not the point. The point is the evidence table: given the
market has looked like this before, what actually happened over the following
one, three, and five years — including the worst case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .config import (
    CASH_YIELD,
    DEPLOYMENT_PLANS,
    DORMANT_RULES,
    FORWARD_HORIZONS_MONTHS,
    MIN_HISTORY_YEARS,
    NEUTRAL_TOLERANCE,
    Market,
    TemperatureBand,
    classify_score,
)
from .data import MarketDataUnavailable, load_market
from .signals import RuleReading, composite_score, evaluate_rules, score_series


@dataclass
class BandEvidence:
    """What happened after the market previously sat in one temperature band."""

    band_key: str
    band_label: str
    months_observed: int
    independent_windows: float
    forward: dict[int, dict[str, float]] = field(default_factory=dict)

    @property
    def is_thin(self) -> bool:
        """True when there is too little independent evidence to lean on."""
        return self.independent_windows < 3.0


@dataclass
class MarketTemperature:
    market: Market
    asof: pd.Timestamp
    score: float
    rank_within_sign: float
    neutral_share: float
    band: TemperatureBand
    readings: list[RuleReading]
    history: pd.DataFrame
    evidence: list[BandEvidence]
    data_start: pd.Timestamp
    data_end: pd.Timestamp
    latest_price: float
    drawdown_from_alltime: float
    warnings: list[str] = field(default_factory=list)

    @property
    def deployment(self):
        return DEPLOYMENT_PLANS[self.band.key]

    @property
    def is_neutral(self) -> bool:
        return self.band.key == "neutral"

    @property
    def active_rules(self) -> list[RuleReading]:
        """Rules actually casting a non-zero vote right now."""
        return [r for r in self.readings if r.score not in (None, 0.0)]

    @property
    def years_of_history(self) -> float:
        return (self.data_end - self.data_start).days / 365.25


def _rank_within_sign(score: float, scores: pd.Series) -> float:
    """Rank `score` among historical scores of the same sign, in 0-1.

    Returns 0.0 for a neutral score, where the concept does not apply.
    """
    if abs(score) <= NEUTRAL_TOLERANCE:
        return 0.0
    if score > 0:
        peers = scores[scores > NEUTRAL_TOLERANCE]
        if peers.empty:
            return 1.0
        return float((peers <= score).sum()) / len(peers)
    peers = scores[scores < -NEUTRAL_TOLERANCE]
    if peers.empty:
        return 1.0
    return float((peers >= score).sum()) / len(peers)


def _expanding_bands(scores: pd.Series) -> list[TemperatureBand]:
    """Band at each point in time, ranked only against prior history."""
    values = scores.to_numpy()
    bands: list[TemperatureBand] = []
    for i, value in enumerate(values):
        past = pd.Series(values[: i + 1])
        bands.append(classify_score(float(value), _rank_within_sign(float(value), past)))
    return bands


def _forward_return_pct(
    total_return: pd.Series, start: pd.Timestamp, months: int
) -> Optional[float]:
    """Annualised forward return from `start` over `months`, or None if unavailable."""
    end = start + pd.Timedelta(days=int(round(30.44 * months)))
    if end > total_return.index[-1]:
        return None
    window = total_return[(total_return.index >= start) & (total_return.index <= end)]
    if len(window) < 2 or window.iloc[0] <= 0:
        return None
    growth = float(window.iloc[-1] / window.iloc[0])
    if growth <= 0:
        return None
    years = months / 12.0
    return (growth ** (1.0 / years) - 1.0) * 100.0


def _build_evidence(
    history: pd.DataFrame, total_return: pd.Series
) -> list[BandEvidence]:
    """Forward-return distribution conditioned on the temperature band."""
    evidence: list[BandEvidence] = []
    for band_key, group in history.groupby("band_key", sort=False):
        label = str(group["band_label"].iloc[0])
        record = BandEvidence(
            band_key=str(band_key),
            band_label=label,
            months_observed=len(group),
            # Overlapping windows massively overstate the sample. Divide by the
            # longest horizon to get a rough count of genuinely independent looks.
            independent_windows=len(group) / max(FORWARD_HORIZONS_MONTHS),
        )
        for months in FORWARD_HORIZONS_MONTHS:
            values = [
                v
                for v in (
                    _forward_return_pct(total_return, date, months)
                    for date in group.index
                )
                if v is not None
            ]
            if not values:
                continue
            arr = np.asarray(values, dtype=float)
            record.forward[months] = {
                "count": float(len(arr)),
                "mean": float(arr.mean()),
                "median": float(np.median(arr)),
                "worst": float(arr.min()),
                "best": float(arr.max()),
                "pct_positive": float((arr > 0).mean() * 100.0),
                "pct_beat_cash": float((arr > CASH_YIELD * 100).mean() * 100.0),
            }
        evidence.append(record)

    order = {"cold": 0, "cool": 1, "neutral": 2, "warm": 3, "hot": 4}
    evidence.sort(key=lambda e: order.get(e.band_key, 99))
    return evidence


def compute_market_temperature(
    market: Market, *, refresh: bool = False
) -> MarketTemperature:
    """Full temperature reading for one market."""
    price, total_return = load_market(market, refresh=refresh)

    burn_in = int(MIN_HISTORY_YEARS * 12)
    if len(total_return) <= burn_in + 36:
        raise MarketDataUnavailable(
            f"{market.label} has only {len(total_return)} months of history; "
            f"at least {burn_in + 36} are needed before the score means anything."
        )

    dates = list(total_return.index[burn_in:])
    scores = score_series(total_return, dates)

    frame = pd.DataFrame(
        {
            "score": scores,
            "price": price.reindex(scores.index),
            "total_return": total_return.reindex(scores.index),
        }
    )

    bands = _expanding_bands(scores)
    frame["band_key"] = [b.key for b in bands]
    frame["band_label"] = [b.label for b in bands]

    asof = frame.index[-1]
    readings = evaluate_rules(total_return, asof)
    score = composite_score(readings)

    rank = _rank_within_sign(score, scores)
    band = classify_score(score, rank)

    evidence = _build_evidence(frame, total_return)

    warnings: list[str] = []
    dormant = [r.label for r in readings if r.key in DORMANT_RULES]
    if dormant:
        warnings.append(
            "These rules have never once fired in the available history and "
            "contribute nothing today: " + ", ".join(dormant) + "."
        )
    unevaluable = [r.label for r in readings if r.score is None]
    if unevaluable:
        warnings.append(
            "Not enough history to evaluate: " + ", ".join(unevaluable) + ". "
            "They are counted as neutral, which drags the score toward zero."
        )
    current = next((e for e in evidence if e.band_key == band.key), None)
    if current is not None and current.is_thin:
        warnings.append(
            f"The '{band.label}' band has only ~{current.independent_windows:.1f} "
            "independent historical windows behind it. Treat the forward-return "
            "table below as an anecdote, not a statistic."
        )

    all_time_peak = float(total_return.loc[:asof].max())
    drawdown = float((total_return.loc[asof] / all_time_peak - 1.0) * 100.0)

    return MarketTemperature(
        market=market,
        asof=asof,
        score=score,
        rank_within_sign=rank,
        neutral_share=float((scores.abs() <= NEUTRAL_TOLERANCE).mean()),
        band=band,
        readings=readings,
        history=frame,
        evidence=evidence,
        data_start=total_return.index[0],
        data_end=asof,
        latest_price=float(price.loc[asof]) if asof in price.index else float("nan"),
        drawdown_from_alltime=drawdown,
        warnings=warnings,
    )


def deployment_schedule(
    amount: float, temperature: MarketTemperature
) -> list[dict[str, object]]:
    """Turn the band's guidance into a concrete tranche schedule for new cash."""
    plan = temperature.deployment
    tranches = max(1, plan.lumpsum_tranches)
    per = amount / tranches
    start = temperature.asof
    return [
        {
            "Tranche": f"{i + 1} of {tranches}",
            "When": (start + pd.Timedelta(days=int(30.44 * i))).strftime("%b %Y"),
            "Amount": per,
        }
        for i in range(tranches)
    ]
