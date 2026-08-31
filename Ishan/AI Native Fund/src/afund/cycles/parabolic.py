"""Parabolic Return Compression Rule (cycle_framework.yaml `parabolic_rule`;
source doc section 3, generalized from the gold example).

Pure function — no I/O. Callers supply the trailing window return and (when
known) the asset's own long-run average annual return; the rule fires on
EITHER trigger independently (compression-factor OR the flat
min_abs_return_pct secondary trigger).
"""
from __future__ import annotations

from dataclasses import dataclass

from afund.cycles.framework import CycleFramework


@dataclass
class ParabolicCheck:
    triggered: bool
    trailing_return_pct: float
    window_months: int
    reason: str
    action: str | None  # framework.parabolic_rule.action if triggered, else None


def check_parabolic(
    framework: CycleFramework,
    trailing_window_return_pct: float,
    long_run_annual_mean_return_pct: float | None = None,
    compression_factor: float = 20.0,
) -> ParabolicCheck:
    """Evaluate the Parabolic Return Compression Rule against a trailing
    `window_months`-month return.

    Two independent triggers (either fires the flag):
      1. Compression trigger: trailing_window_return_pct >=
         long_run_annual_mean_return_pct * compression_factor, approximating
         the doc's "20-30 years of typical return inside ~24 months"
         illustration. Only evaluated when long_run_annual_mean_return_pct
         is known (never fabricated when missing).
      2. Secondary flat trigger: trailing_window_return_pct >=
         framework.parabolic_rule.min_abs_return_pct (100%, DRAFT) fires
         regardless of whether the long-run mean is known — this is the
         floor the plan spec calls out explicitly so the rule still has
         teeth for assets without a well-established long-run average.

    `compression_factor` defaults to 20 (the low end of the doc's "20-30
    years... inside ~24 months" illustration) — a DRAFT judgment call for
    the default; callers may override per-asset.
    """
    rule = framework.parabolic_rule
    window_months = rule.window_months

    reasons: list[str] = []
    triggered = False

    if long_run_annual_mean_return_pct is not None and long_run_annual_mean_return_pct > 0:
        compression_threshold = long_run_annual_mean_return_pct * compression_factor
        if trailing_window_return_pct >= compression_threshold:
            triggered = True
            reasons.append(
                f"compression trigger: {trailing_window_return_pct:.1f}% over "
                f"{window_months}m >= {compression_factor:.0f}x long-run annual mean "
                f"({long_run_annual_mean_return_pct:.1f}%) = {compression_threshold:.1f}%"
            )

    if trailing_window_return_pct >= rule.min_abs_return_pct:
        triggered = True
        reasons.append(
            f"secondary trigger: {trailing_window_return_pct:.1f}% over "
            f"{window_months}m >= min_abs_return_pct ({rule.min_abs_return_pct:.0f}%)"
        )

    if not reasons:
        reasons.append(
            f"no trigger: {trailing_window_return_pct:.1f}% over {window_months}m "
            f"below both thresholds"
        )

    return ParabolicCheck(
        triggered=triggered,
        trailing_return_pct=trailing_window_return_pct,
        window_months=window_months,
        reason="; ".join(reasons),
        action=rule.action if triggered else None,
    )
