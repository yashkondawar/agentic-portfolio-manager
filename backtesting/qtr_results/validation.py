"""
validation.py
=============

Out-of-sample validation scaffolding for the quarterly-results strategy.

The core methodological flaw in the legacy work is that its headline numbers were
tuned *to a return target* on ~30–50 trades, then reported in-sample. This module
provides the two tools that turn that into an honest process:

* :func:`walk_forward_windows` — a rolling **train → test** splitter with a **purge +
  embargo** gap between the two, so a trade whose holding window straddles the split
  cannot leak future information into the training fold (López de Prado, *Advances in
  Financial Machine Learning*, ch. 7). You tune on ``train`` and report only on
  ``test``; a final locked hold-out is just the last window you touch once.

* :func:`deflated_sharpe_ratio` — the **Deflated Sharpe Ratio** (Bailey & López de
  Prado 2014). A raw Sharpe computed after trying *N* configurations is upward-biased
  by selection; the DSR discounts it for the number of trials, the sample length, and
  the skew/kurtosis of returns. It answers the only question that matters here: *is
  this edge distinguishable from the luckiest of the configs we tried?*

Pure/stdlib (uses ``statistics`` + ``math``); no pandas dependency so it is cheap to
unit-test in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Sequence

import math
import statistics


@dataclass
class WFWindow:
    train_start: date
    train_end: date
    test_start: date
    test_end: date


def walk_forward_windows(
    start: date,
    end: date,
    *,
    train_months: int = 24,
    test_months: int = 6,
    step_months: Optional[int] = None,
    embargo_days: int = 60,
) -> List[WFWindow]:
    """Rolling walk-forward splits over ``[start, end]``.

    Each window trains on ``train_months``, then leaves an ``embargo_days`` gap
    (defaulting to one holding window, ~60 calendar days, so no overlapping trade
    bridges the split) before a ``test_months`` out-of-sample block. The window then
    advances by ``step_months`` (defaults to ``test_months`` = non-overlapping test
    blocks). Returns an empty list if the range can't fit even one full window.
    """
    if step_months is None:
        step_months = test_months
    if step_months <= 0:
        raise ValueError("step_months must be positive")

    windows: List[WFWindow] = []
    train_start = start
    while True:
        train_end = _add_months(train_start, train_months)
        test_start = train_end + timedelta(days=embargo_days)
        test_end = _add_months(test_start, test_months)
        if test_end > end:
            break
        windows.append(WFWindow(train_start, train_end, test_start, test_end))
        train_start = _add_months(train_start, step_months)
    return windows


def _add_months(d: date, months: int) -> date:
    """``d`` shifted by ``months`` (calendar-safe, clamps to month length)."""
    m0 = d.month - 1 + months
    year = d.year + m0 // 12
    month = m0 % 12 + 1
    # Clamp the day to the target month's length.
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = (next_month_first - timedelta(days=1)).day
    return date(year, month, min(d.day, last_day))


def _sharpe(returns: Sequence[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = statistics.fmean(returns)
    std = statistics.stdev(returns)
    return mean / std if std > 0 else 0.0


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def deflated_sharpe_ratio(
    returns: Sequence[float],
    *,
    num_trials: int = 1,
    annualization: int = 252,
) -> Optional[float]:
    """Deflated Sharpe Ratio (probability the true Sharpe > 0 after selection bias).

    ``returns`` is the per-period (e.g. daily) return series of the chosen config.
    ``num_trials`` is how many configurations were tried to find it — this is the
    penalty that a plain Sharpe ignores. Returns a probability in ``[0, 1]``; a value
    below ~0.95 means the result is not convincingly better than the best of
    ``num_trials`` random configs. ``None`` if the series is too short.

    Steps: estimate the non-annualized Sharpe and its standard error (adjusted for
    the return distribution's skew and excess kurtosis), derive the *expected maximum*
    Sharpe under ``num_trials`` null configs, and evaluate the probability the
    observed Sharpe exceeds that benchmark.
    """
    n = len(returns)
    if n < 8:
        return None
    sr = _sharpe(returns)  # per-period Sharpe
    # Higher moments of the return series.
    mean = statistics.fmean(returns)
    std = statistics.stdev(returns)
    if std <= 0:
        return None
    m3 = sum((r - mean) ** 3 for r in returns) / n
    m4 = sum((r - mean) ** 4 for r in returns) / n
    skew = m3 / std**3
    kurt = m4 / std**4  # non-excess kurtosis

    # Expected maximum Sharpe of `num_trials` independent null strategies (SR ~ N(0,1)
    # in "trials" space): E[max] ≈ sqrt(2 ln T) approx via the Gumbel expectation.
    T = max(int(num_trials), 1)
    if T > 1:
        euler = 0.5772156649
        e_max = (1 - euler) * _inv_norm(1 - 1.0 / T) + euler * _inv_norm(
            1 - 1.0 / (T * math.e)
        )
    else:
        e_max = 0.0

    # Standard error of the Sharpe estimator (Lo 2002, moment-adjusted).
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    if denom <= 0:
        return None
    se = math.sqrt(denom / (n - 1))
    if se <= 0:
        return None
    dsr = _norm_cdf((sr - e_max) / se)
    return dsr


def _inv_norm(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation)."""
    p = min(max(p, 1e-9), 1 - 1e-9)
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    dcoef = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
             3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((dcoef[0] * q + dcoef[1]) * q + dcoef[2]) * q + dcoef[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((dcoef[0] * q + dcoef[1]) * q + dcoef[2]) * q + dcoef[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
