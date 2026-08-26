"""
sweep.py
========

Parameter search done in the only way that is worth anything: **tune on train
folds, report on test folds, and discount the result for the number of things
you tried.**

Why this module exists
----------------------
The GFS thresholds - 60 / 60 / 40 - are folklore. Nobody has published a
derivation. The obvious thing to do is search for better ones, and the obvious
thing is also a trap: with a few hundred combinations you can always find a set
that looks spectacular on ten years of Indian equities, and it will mean
nothing. Two guards are applied:

1. **Walk-forward with purge and embargo.** Each fold picks its winner using
   only its training window, then that winner is run - untouched - on a test
   window separated by an embargo gap wide enough that no open position can
   straddle the boundary (López de Prado, *Advances in Financial Machine
   Learning*, ch. 7). The headline number is the *stitched test-fold* result,
   which no parameter ever saw.

2. **Deflated Sharpe Ratio.** After trying *N* configurations, the best raw
   Sharpe is upward-biased by selection alone. The DSR (Bailey & López de Prado
   2014) discounts for the trial count, the sample length, and the skew and
   kurtosis of the return series. It answers the question a Sharpe cannot:
   *is this better than the luckiest of the things I tried?*

A third diagnostic, :func:`parameter_stability`, is arguably the most useful of
the lot. It asks whether the good region of parameter space is a broad plateau
or a lone spike. A plateau suggests a real effect that is insensitive to exactly
where you draw the line; a spike is almost always curve-fitting, no matter how
impressive its Sharpe.
"""

import itertools
import logging
import math
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence

from ..qtr_results.validation import (
    WFWindow,
    deflated_sharpe_ratio,
    walk_forward_windows,
)
from .config import GFSConfig
from .metrics import daily_returns
from .service import PreparedData, run_single

logger = logging.getLogger("gfs.sweep")

# The grid is deliberately coarse. A fine grid does not find a better strategy;
# it finds a better-fitting one, and inflates the trial count that the DSR then
# has to discount.
DEFAULT_GRID: Dict[str, Sequence] = {
    "g_rsi_min": (55.0, 60.0, 65.0),
    "f_rsi_min": (55.0, 60.0, 65.0),
    "s_rsi_entry": (30.0, 35.0, 40.0, 45.0),
    "exit_rsi": (60.0, 65.0, 70.0),
    "atr_stop_mult": (1.5, 2.0, 3.0),
}

# Selection criterion. Sharpe rather than CAGR: a raw return ranking will always
# hand the crown to the most leveraged, most concentrated, luckiest variant.
DEFAULT_OBJECTIVE = "sharpe"


def grid_combinations(grid: Dict[str, Sequence]) -> List[Dict[str, Any]]:
    keys = sorted(grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(grid[k] for k in keys))]


def _score(metrics: Dict[str, Any], objective: str) -> float:
    value = metrics.get(objective)
    if value is None or not math.isfinite(float(value)):
        return float("-inf")
    # A configuration that trades three times can post any Sharpe you like.
    if metrics.get("num_trades", 0) < 10:
        return float("-inf")
    return float(value)


def _run_window(
    cfg: GFSConfig,
    prepared: PreparedData,
    start,
    end,
    overrides: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    trial = replace(cfg, start_date=start, end_date=end, **overrides)
    try:
        return run_single(trial, prepared, with_forward_study=False)
    except Exception as exc:  # noqa: BLE001 - a bad corner of the grid is data, not a crash
        logger.debug("Trial failed (%s): %s", overrides, exc)
        return None


def walk_forward_sweep(
    cfg: GFSConfig,
    prepared: PreparedData,
    *,
    grid: Optional[Dict[str, Sequence]] = None,
    train_months: int = 36,
    test_months: int = 12,
    embargo_days: int = 90,
    objective: str = DEFAULT_OBJECTIVE,
) -> Dict[str, Any]:
    """Tune per fold on train, evaluate on test, and report only the test folds.

    ``embargo_days`` defaults to 90 - comfortably wider than the 60-day time
    stop - so no position opened in a training window can still be open when the
    test window begins.
    """
    grid = grid or DEFAULT_GRID
    combos = grid_combinations(grid)
    windows: List[WFWindow] = walk_forward_windows(
        cfg.start_date,
        cfg.end_date,
        train_months=train_months,
        test_months=test_months,
        embargo_days=embargo_days,
    )
    if not windows:
        raise ValueError(
            "The date range cannot fit a single walk-forward window. Widen the "
            f"range or shrink train_months ({train_months}) / test_months "
            f"({test_months})."
        )

    logger.info(
        "Walk-forward sweep: %d windows x %d configurations = %d fold-trials",
        len(windows),
        len(combos),
        len(windows) * len(combos),
    )

    folds: List[Dict[str, Any]] = []
    stitched_returns: List[float] = []
    chosen_params: List[Dict[str, Any]] = []

    for i, window in enumerate(windows, start=1):
        best, best_score, best_overrides = None, float("-inf"), None
        for overrides in combos:
            result = _run_window(
                cfg, prepared, window.train_start, window.train_end, overrides
            )
            if result is None:
                continue
            score = _score(result["metrics"], objective)
            if score > best_score:
                best, best_score, best_overrides = result, score, overrides

        if best_overrides is None:
            logger.warning("Window %d: no configuration produced enough trades", i)
            folds.append({"window": i, "status": "no_viable_config"})
            continue

        test = _run_window(
            cfg, prepared, window.test_start, window.test_end, best_overrides
        )
        if test is None:
            folds.append({"window": i, "status": "test_run_failed"})
            continue

        stitched_returns.extend(daily_returns(test["equity_curve"]))
        chosen_params.append(best_overrides)
        folds.append(
            {
                "window": i,
                "train": f"{window.train_start} -> {window.train_end}",
                "test": f"{window.test_start} -> {window.test_end}",
                "chosen": best_overrides,
                "train_objective": round(best_score, 3),
                "train_cagr_pct": best["metrics"].get("cagr_pct"),
                "test_cagr_pct": test["metrics"].get("cagr_pct"),
                "test_sharpe": test["metrics"].get("sharpe"),
                "test_max_dd_pct": test["metrics"].get("max_drawdown_pct"),
                "test_trades": test["metrics"].get("num_trades"),
                "test_win_rate_pct": test["metrics"].get("win_rate_pct"),
            }
        )
        logger.info(
            "Window %d | chose %s | train %s=%.2f -> test CAGR %.2f%%",
            i,
            best_overrides,
            objective,
            best_score,
            test["metrics"].get("cagr_pct", 0.0),
        )

    dsr = deflated_sharpe_ratio(stitched_returns, num_trials=len(combos))
    return {
        "objective": objective,
        "num_configs_tried": len(combos),
        "num_windows": len(windows),
        "folds": folds,
        "out_of_sample_dsr": None if dsr is None else round(dsr, 4),
        "parameter_stability": _stability_of_choices(chosen_params),
        "stitched_test_days": len(stitched_returns),
    }


def _stability_of_choices(chosen: List[Dict[str, Any]]) -> Dict[str, Any]:
    """How much the winning parameters jump around between folds.

    A strategy whose optimal threshold is 55 in one fold and 65 in the next has
    no optimal threshold; it has noise. Reported as the share of folds that
    agreed on the modal value, per parameter.
    """
    if not chosen:
        return {}
    out: Dict[str, Any] = {}
    for key in chosen[0]:
        values = [c[key] for c in chosen]
        modal = max(set(values), key=values.count)
        out[key] = {
            "modal_value": modal,
            "agreement_pct": round(values.count(modal) / len(values) * 100.0, 1),
            "values_by_fold": values,
        }
    return out


def parameter_stability(
    cfg: GFSConfig,
    prepared: PreparedData,
    parameter: str,
    *,
    values: Optional[Sequence] = None,
    objective: str = DEFAULT_OBJECTIVE,
) -> List[Dict[str, Any]]:
    """Sweep ONE parameter across the whole window and report the response curve.

    Read this as a shape, not a maximum. A broad plateau means the effect does
    not depend on the exact number and is plausibly real; an isolated spike -
    good at 60, bad at 55 and 65 - is curve-fitting even if it is the best
    number on the page.
    """
    if not hasattr(cfg, parameter):
        raise ValueError(f"GFSConfig has no parameter {parameter!r}.")
    if values is None:
        values = DEFAULT_GRID.get(parameter)
    if not values:
        raise ValueError(
            f"No default value grid for {parameter!r}. Pass values=[...] "
            f"explicitly. Parameters with a default grid: "
            f"{', '.join(sorted(DEFAULT_GRID))}."
        )
    rows = []
    for value in values:
        result = _run_window(cfg, prepared, cfg.start_date, cfg.end_date, {parameter: value})
        if result is None:
            rows.append({parameter: value, "status": "failed"})
            continue
        m = result["metrics"]
        rows.append(
            {
                parameter: value,
                "objective": _score(m, objective),
                "cagr_pct": m.get("cagr_pct"),
                "sharpe": m.get("sharpe"),
                "max_drawdown_pct": m.get("max_drawdown_pct"),
                "num_trades": m.get("num_trades"),
                "win_rate_pct": m.get("win_rate_pct"),
                "expectancy_r": m.get("expectancy_r"),
            }
        )
    return rows


def render_sweep(report: Dict[str, Any]) -> str:
    lines = [
        "=" * 78,
        " WALK-FORWARD SWEEP (tuned on train folds, reported on test folds)",
        "=" * 78,
        f" Configurations tried : {report['num_configs_tried']}",
        f" Windows              : {report['num_windows']}",
        "-" * 78,
        f" {'#':<3}{'test window':<26}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>9}{'trades':>8}",
    ]
    for fold in report["folds"]:
        if "test" not in fold:
            lines.append(f" {fold['window']:<3}{fold.get('status', 'skipped')}")
            continue
        lines.append(
            f" {fold['window']:<3}{fold['test']:<26}"
            f"{_f(fold['test_cagr_pct']):>8.2f}%{_f(fold['test_sharpe']):>9.2f}"
            f"{_f(fold['test_max_dd_pct']):>8.2f}%{int(_f(fold['test_trades'])):>8}"
        )

    dsr = report.get("out_of_sample_dsr")
    lines += [
        "-" * 78,
        f" Deflated Sharpe (out of sample, {report['num_configs_tried']} trials): "
        f"{dsr if dsr is not None else 'n/a'}",
        " DSR is the probability the true Sharpe is above zero AFTER accounting",
        " for how many configurations were tried. Below ~0.95, the edge is not",
        " distinguishable from the luckiest configuration in the grid.",
    ]

    stability = report.get("parameter_stability") or {}
    if stability:
        lines += ["-" * 78, " PARAMETER STABILITY ACROSS FOLDS"]
        for key, info in stability.items():
            flag = "" if info["agreement_pct"] >= 60 else "   <-- unstable"
            lines.append(
                f"  {key:<18} modal {str(info['modal_value']):<8}"
                f" agreement {info['agreement_pct']:>5.1f}%{flag}"
            )
    lines.append("=" * 78)
    return "\n".join(lines)


def render_stability_curve(rows: List[Dict[str, Any]], parameter: str) -> str:
    if not rows:
        return ""
    lines = [
        "-" * 68,
        f" RESPONSE CURVE FOR {parameter} - look for a plateau, not a peak",
        f" {parameter:<12}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>9}{'trades':>8}{'ExpR':>8}",
    ]
    for row in rows:
        if row.get("status") == "failed":
            lines.append(f" {str(row[parameter]):<12}  failed")
            continue
        lines.append(
            f" {str(row[parameter]):<12}{_f(row['cagr_pct']):>8.2f}%"
            f"{_f(row['sharpe']):>9.2f}{_f(row['max_drawdown_pct']):>8.2f}%"
            f"{int(_f(row['num_trades'])):>8}{_f(row['expectancy_r']):>8.2f}"
        )
    return "\n".join(lines)


def _f(value) -> float:
    return 0.0 if value is None else float(value)
