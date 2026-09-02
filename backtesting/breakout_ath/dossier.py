"""The nine-sheet Excel dossier for the ATH breakout sleeve.

This reuses the shared reporting machinery in :mod:`backtesting.qtr_results.dossier`
— the metric maths, the Indian capital-gains ledger and the workbook writer are
strategy-agnostic — and layers on the two things this sleeve reports differently:

* the Summary carries the sleeve's own headline and configuration block, with
  metrics as fractions rather than percentages;
* the Positions sheet lists positions that are *still open* on the final
  session alongside the closed ones, so the workbook accounts for all capital
  rather than only the realised part.
"""

from __future__ import annotations

import logging
from dataclasses import fields
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from backtesting.breakout_ath.config import AthBreakoutConfig
from backtesting.gfs.taxes import TaxConfig
from backtesting.qtr_results import dossier as shared

logger = logging.getLogger(__name__)

#: Config keys reported in the Summary, in the order the sleeve describes them.
CONFIG_KEYS = (
    "max_positions",
    "sl_pct",
    "ath_band",
    "selection_rule",
    "lookback",
    "slot_reset_freq",
    "cost_bps",
    "stcg_rate",
    "ltcg_rate",
    "start_capital",
    "signal_price",
)

SHEET_ORDER = (
    "Summary",
    "Equity_Curve",
    "Positions",
    "Trades",
    "Yearly_Returns",
    "Rolling_3Y",
    "Rolling_5Y",
    "Daily_Returns_Portfolio",
    "Tax_Ledger",
)

#: Banner shown above the header row on the sheets that carry one.
TITLES = {
    "Positions": "Every position: what was bought, when, and when it was sold",
    "Yearly_Returns": "Calendar-year returns",
    "Rolling_3Y": "Rolling 3-year CAGR (monthly windows)",
    "Rolling_5Y": "Rolling 5-year CAGR (monthly windows)",
}

_METRICS = (
    "CAGR",
    "Absolute return",
    "Final value",
    "Max drawdown",
    "Volatility (annual)",
    "Sharpe",
    "Sortino",
    "Alpha (annual)",
    "Beta",
    "Correlation",
    "Tracking error",
    "Excess CAGR",
)

#: Shared-writer metric labels, mapped onto this sleeve's labels. The shared
#: helper reports percentages; the sleeve reports fractions.
_FROM_SHARED = {
    "CAGR": ("CAGR (%)", 100.0),
    "Absolute return": ("Absolute return (%)", 100.0),
    "Final value": ("Final value", 1.0),
    "Max drawdown": ("Max drawdown (%)", 100.0),
    "Volatility (annual)": ("Volatility, annual (%)", 100.0),
    "Sharpe": ("Sharpe", 1.0),
    "Sortino": ("Sortino", 1.0),
    "Alpha (annual)": ("Alpha, annual (%)", 100.0),
    "Beta": ("Beta", 1.0),
    "Correlation": ("Correlation", 1.0),
    "Tracking error": ("Tracking error (%)", 100.0),
    "Excess CAGR": ("Excess CAGR (%)", 100.0),
}


def tax_config(cfg: AthBreakoutConfig) -> TaxConfig:
    """The tax regime the sleeve is reported under.

    A single short-term rate across the whole history, and no long-term annual
    exemption: the sleeve is one part of a larger book, so the exemption is
    assumed to have been consumed elsewhere rather than credited here.
    """
    return TaxConfig(
        stcg_rate_pct=cfg.stcg_rate * 100.0,
        stcg_rate_pct_legacy=cfg.stcg_rate * 100.0,
        ltcg_rate_pct=cfg.ltcg_rate * 100.0,
        ltcg_exempt_per_year=0.0,
    )


def headline(cfg: AthBreakoutConfig) -> str:
    return (
        f"52-week-high breakout | trail-only | {cfg.selection_rule} ranking | "
        f"N={cfg.max_positions}, stop={cfg.sl_pct:.0%}, "
        f"within {cfg.ath_band:.0%} of lifetime high, "
        f"{cfg.cost_bps:.0f} bps + tax"
    )


def _config_rows(cfg: AthBreakoutConfig, calendar: Sequence[date]) -> List[List[Any]]:
    known = {f.name for f in fields(cfg)}
    rows: List[List[Any]] = [["Configuration", None, None, None, None]]
    for key in CONFIG_KEYS:
        if key in known:
            rows.append([key, getattr(cfg, key), None, None, None])
    span = shared._years_between(calendar[0], calendar[-1])
    rows.append(
        [
            "period",
            f"{calendar[0].isoformat()} to {calendar[-1].isoformat()}"
            f"  ({span:.2f} years)",
            None,
            None,
            None,
        ]
    )
    return rows


def _summary_sheet(
    cfg: AthBreakoutConfig,
    shared_summary: pd.DataFrame,
    calendar: Sequence[date],
) -> pd.DataFrame:
    """Rebuild the Summary in this sleeve's own layout."""
    lookup: Dict[str, List[Any]] = {}
    for row in shared_summary.itertuples(index=False):
        values = list(row)
        if values and isinstance(values[0], str):
            lookup[values[0]] = values[1:]

    order = [
        "Portfolio (net of cost+tax)",
        "Before tax",
        "Before cost & tax",
        "NIFTY 50",
    ]
    rows: List[List[Any]] = [
        [headline(cfg), None, None, None, None],
        [
            "Portfolio figures are NET of brokerage and capital-gains tax. "
            "Index figures are raw index levels.",
            None,
            None,
            None,
            None,
        ],
        [None, None, None, None, None],
        ["Metric", *order],
    ]
    for label in _METRICS:
        source, scale = _FROM_SHARED[label]
        values = lookup.get(source, [None] * 4)
        rows.append(
            [label] + [None if v is None else _scale(v, scale) for v in values[:4]]
        )

    rows.append([None, None, None, None, None])
    rows.append(["Costs and tax actually paid", None, None, None, None])
    for label in (
        "Brokerage + impact paid",
        "Capital-gains tax paid",
        "Total frictions",
    ):
        rows.append([label, *lookup.get(label, [None] * 4)[:4]])
    friction = lookup.get("CAGR given up to frictions (pp)", [None] * 4)
    rows.append(
        ["CAGR given up to frictions", _scale(friction[0], 100.0), None, None, None]
    )

    for label, scale in (
        ("Total fills", 1.0),
        ("Round trips", 1.0),
        ("Win rate (%)", 100.0),
        ("Avg holding days", 1.0),
        ("Mean positions open", 1.0),
        ("Mean cash (%)", 100.0),
    ):
        values = lookup.get(label, [None] * 4)
        rows.append(
            [
                label.replace(" (%)", "").replace("Mean cash", "Mean cash %"),
                _scale(values[0], scale),
                None,
                None,
                None,
            ]
        )

    rows.append([None, None, None, None, None])
    rows += _config_rows(cfg, calendar)
    return pd.DataFrame(rows)


def _scale(value: Any, scale: float) -> Any:
    if value is None or not isinstance(value, (int, float)):
        return value
    return float(value) / scale


def build(
    cfg: AthBreakoutConfig,
    engine: Any,
    *,
    metrics: Optional[Dict[str, Any]] = None,
    nifty500: Optional[pd.DataFrame] = None,
    notes: Sequence[str] = (),
) -> Dict[str, pd.DataFrame]:
    """The nine dossier sheets for a finished run."""
    tax_cfg = tax_config(cfg)
    sheets = shared.build_dossier(
        cfg,
        engine,
        engine.prices,
        metrics=metrics,
        tax_cfg=tax_cfg,
        nifty500=nifty500,
        notes=notes,
    )

    calendar = [date.fromisoformat(r["date"]) for r in engine.daily_log]
    sheets["Summary"] = _summary_sheet(cfg, sheets["Summary"], calendar)

    open_rows = engine.open_positions
    if open_rows:
        positions = sheets["Positions"]
        if "status" not in positions.columns:
            positions = positions.assign(status="closed")
        extra = pd.DataFrame(open_rows)[list(positions.columns)]
        sheets["Positions"] = pd.concat([positions, extra], ignore_index=True)

    return {name: sheets[name] for name in SHEET_ORDER if name in sheets}


def write(sheets: Dict[str, pd.DataFrame], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    shared.write_workbook(path, sheets, titles=TITLES)
    logger.info("Wrote dossier to %s", path)
    return path
