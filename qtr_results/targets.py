"""Target / exit-plan computation.

Primary method is a **PE re-rating** target: holding the market's assigned
multiple constant against the freshly-grown TTM EPS gives a fair price; the
implied upside is floored/capped into the configured 10-20% band. When PE / EPS
data is unavailable we fall back to a **static tier** keyed on result strength.
The trailing stop is an **ATR-based** volatility distance (``ATR_STOP_MULTIPLIER
x ATR``), decoupled from the target; with ride-the-wave (``DISABLE_PROFIT_TARGET``)
the target is a reference only and the exit is the ATR trail or the time-stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from qtr_results import config
from qtr_results.analysis import AnalysisResult
from qtr_results.util import clamp


@dataclass
class TargetPlan:
    method: str  # "pe_rerating" | "static"
    entry_price: float
    target_pct: float
    target_price: float
    trailing_stop_pct: float
    stop_distance_abs: Optional[float] = None  # ₹ per-share risk (ATR-based)
    stop_basis: str = "atr"                     # "atr" | "fallback_pct" | "ratio"
    raw_upside_pct: Optional[float] = None
    justified_pe: Optional[float] = None
    ttm_eps: Optional[float] = None
    fair_price: Optional[float] = None
    max_holding_days: Optional[int] = None
    notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _resolve_stop(entry_price: float, atr: Optional[float]) -> Tuple[float, float, str]:
    """Return ``(stop_distance_abs, trailing_stop_pct, basis)`` for an entry.

    Prefers an ATR-based distance (``ATR_STOP_MULTIPLIER x ATR``) measured in the
    stock's own volatility, matching the backtest; falls back to
    ``FALLBACK_STOP_PCT`` of entry when ATR is unavailable (thin history). The
    percent form is derived for display / the legacy percent-based ledger path.
    """
    if atr and atr > 0:
        dist = config.ATR_STOP_MULTIPLIER * atr
        basis = "atr"
    else:
        dist = entry_price * config.FALLBACK_STOP_PCT / 100.0
        basis = "fallback_pct"
    pct = round(dist / entry_price * 100.0, 2) if entry_price > 0 else 0.0
    return round(dist, 2), pct, basis


def _static_target_pct(strength_score: float) -> float:
    for threshold, pct in config.STATIC_TARGET_TIERS:
        if strength_score >= threshold:
            return pct
    return config.TARGET_MIN_PCT


def _conviction_band(conviction: Optional[float]) -> Tuple[float, Optional[int]]:
    """Map conviction (0-1) to ``(target_cap_pct, max_holding_days)``.

    High conviction lets a winner ride toward TARGET_MAX_PCT with a longer hold;
    low conviction caps the target nearer TARGET_MIN_PCT and cuts the hold sooner.
    Returns the full band / no override when conviction is unavailable or exit
    shaping is disabled, so behaviour is unchanged in the mechanical-only path.
    """
    if conviction is None or not config.CONVICTION_SHAPES_EXIT:
        return config.TARGET_MAX_PCT, None
    c = max(0.0, min(1.0, conviction))
    cap = config.TARGET_MIN_PCT + c * (config.TARGET_MAX_PCT - config.TARGET_MIN_PCT)
    factor = config.HOLD_DAYS_MIN_FACTOR + c * (
        config.HOLD_DAYS_MAX_FACTOR - config.HOLD_DAYS_MIN_FACTOR
    )
    hold_days = max(1, round(config.MAX_HOLDING_DAYS * factor))
    return cap, hold_days


def build_target_plan(
    analysis: AnalysisResult,
    entry_price: float,
    conviction: Optional[float] = None,
    atr: Optional[float] = None,
) -> Optional[TargetPlan]:
    """Compute the target/exit plan for a qualifying pick.

    ``entry_price`` is the intended entry (current market price). ``conviction``
    (0-1, from the Tier-2 LLM layer) shapes the exit: it lowers the target cap and
    shortens the hold for low-conviction names and lets high-conviction names ride
    toward the full band. ``atr`` (in ₹, from the trailing OHLC window) sets the
    volatility-based trailing-stop distance; when absent the stop falls back to a
    fixed percent of entry. With ``config.DISABLE_PROFIT_TARGET`` the target price
    is a REFERENCE only (ride-the-wave) -- the ledger exits on the ATR trail or the
    time-stop, not the target. Returns ``None`` only when no usable entry price is
    available.
    """
    if not entry_price or entry_price <= 0:
        return None

    target_cap, max_hold = _conviction_band(conviction)
    stop_abs, stop_pct, stop_basis = _resolve_stop(entry_price, atr)

    pe = analysis.current_pe
    ttm_eps = analysis.ttm_eps

    # ── Primary: PE re-rating ──────────────────────────────────────────────
    if pe and pe > 0 and ttm_eps and ttm_eps > 0:
        justified_pe = pe  # hold the market's multiple constant against new EPS
        fair_price = justified_pe * ttm_eps
        raw_upside = (fair_price - entry_price) / entry_price * 100.0
        target_pct = clamp(raw_upside, config.TARGET_MIN_PCT, target_cap)
        target_price = entry_price * (1 + target_pct / 100.0)
        note = (
            f"PE re-rating: fair Rs {fair_price:,.2f} = P/E {justified_pe:g} x TTM EPS "
            f"{ttm_eps:g}; raw upside {raw_upside:+.1f}% clamped to {target_pct:.1f}%."
        )
        return TargetPlan(
            method="pe_rerating",
            entry_price=round(entry_price, 2),
            target_pct=round(target_pct, 2),
            target_price=round(target_price, 2),
            trailing_stop_pct=stop_pct,
            stop_distance_abs=stop_abs,
            stop_basis=stop_basis,
            raw_upside_pct=round(raw_upside, 2),
            justified_pe=round(justified_pe, 2),
            ttm_eps=round(ttm_eps, 2),
            fair_price=round(fair_price, 2),
            max_holding_days=max_hold,
            notes=note,
        )

    # ── Fallback: static tier by strength ──────────────────────────────────
    target_pct = min(_static_target_pct(analysis.strength_score), target_cap)
    target_price = entry_price * (1 + target_pct / 100.0)
    return TargetPlan(
        method="static",
        entry_price=round(entry_price, 2),
        target_pct=round(target_pct, 2),
        target_price=round(target_price, 2),
        trailing_stop_pct=stop_pct,
        stop_distance_abs=stop_abs,
        stop_basis=stop_basis,
        max_holding_days=max_hold,
        notes=(
            f"Static tier: strength {analysis.strength_score:.0f} → {target_pct:.0f}% "
            "(PE/EPS unavailable for re-rating)."
        ),
    )
