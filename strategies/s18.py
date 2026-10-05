"""Registry adapters for S18's fixed research books and paper-only daily runner."""

from __future__ import annotations

from math import isfinite
from datetime import date
from typing import Any

from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)

COMBOS = ("P5", "P10", "P15", "P20", "A20")
METAL_MODES = ("none", "both", "both_priority")

_SAFETY = (
    "Always two independent A/B tranches with 50:50 initial capital. "
    "Paper-only: close decisions fill at the next available open under the "
    "model; armed trailing stops use the intraday low and gap-aware fill. "
    "No broker orders or manual fill confirmations. Contract-note charges "
    "are shadow-only; never import real stop fills into the model. Slippage "
    "has not been tested."
)


def _book_specs() -> list[ParamSpec]:
    return [
        ParamSpec(
            "combo",
            "Fixed S18 combo",
            ParamType.ENUM,
            default="P15",
            choices=list(COMBOS),
            help="P15 is the selected book; A20 is the n=20 backup. No tuning grid.",
            group="Book",
        ),
        ParamSpec(
            "metal_mode",
            "Metal mode",
            ParamType.ENUM,
            default="both_priority",
            choices=list(METAL_MODES),
            help=(
                "none: stocks only; both: ranked gold/silver; both_priority: "
                "eligible metals first. Metals enter S1 only, never S2."
            ),
            group="Book",
        ),
        ParamSpec(
            "capital",
            "Initial capital (₹, both tranches combined)",
            ParamType.FLOAT,
            default=100_000.0,
            min=1.0,
            help=(
                "Split 50:50 across A and B. Used only when a paper book is "
                "created; changing it does not recapitalise an existing book."
            ),
            group="Book",
        ),
    ]


def _result(strategy_id: str, output: dict[str, Any]) -> StrategyResult:
    data = dict(output)
    report = data.pop("report", "")
    return StrategyResult(strategy_id, "completed", report=report, data=data)


def _shadow_charges(value: Any) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("shadow_charges must map model fill IDs to charge breakdowns")
    allowed = {
        "stt",
        "stamp_duty",
        "exchange_fees",
        "gst",
        "dp_charges",
        "brokerage",
        "other",
    }
    for fill_id, breakdown in value.items():
        if not isinstance(fill_id, str) or not fill_id.strip():
            raise ValueError("shadow_charges requires nonempty model fill IDs")
        if not isinstance(breakdown, dict) or set(breakdown) - allowed:
            raise ValueError(f"Invalid charge breakdown for model fill {fill_id}")
        for amount in breakdown.values():
            if (
                isinstance(amount, bool)
                or not isinstance(amount, (int, float))
                or not isfinite(amount)
                or amount < 0
            ):
                raise ValueError("Shadow charges must be finite nonnegative numbers")
    return value


@register
class S18BacktestStrategy(BaseStrategy):
    id = "s18_backtest"
    name = "S18 Backtest"
    description = (
        "Backtest one fixed S18 stacked S1/S2 combo with both A/B tranches, "
        "modeled tax and costs, and an optional stored dossier."
    )
    long_description = (
        "Choose P5/P10/P15/P20/A20 and none/both/both_priority metals, a period "
        "and total capital. The SMA100 overlay gates S1 entries, monthly "
        "momentum reviews arm/disarm stops, and S2 uses idle cash. A period "
        "backtest is not a golden certificate: use S18 Golden Replay to "
        "validate all 15 combo/mode combinations before paper operation. "
        "Historical inputs and golden references come from the app's SQLite "
        "dataset; no external reference folder is needed. " + _SAFETY
    )
    category = StrategyCategory.BACKTEST

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec(
                "start",
                "Start date",
                ParamType.DATE,
                default="2014-01-01",
                group="Window",
            ),
            ParamSpec(
                "end",
                "End date",
                ParamType.DATE,
                default="2026-08-31",
                group="Window",
            ),
            *_book_specs(),
            ParamSpec(
                "write_dossier",
                "Store backtest dossier",
                ParamType.BOOL,
                default=True,
                help="Persist downloadable artifacts in the local SQLite store.",
                group="Output",
            ),
        ]

    def run(self, params: dict[str, Any]) -> StrategyResult:
        from backtesting.s18.service import run_backtest

        output = run_backtest(
            combo=params["combo"],
            metal_mode=params["metal_mode"],
            start=params["start"],
            end=params["end"],
            capital=params["capital"],
            write_dossier=params["write_dossier"],
        )
        return _result(self.id, output)


@register
class S18ReplayStrategy(BaseStrategy):
    id = "s18_replay"
    name = "S18 Golden Replay"
    description = (
        "Validate all 15 combo/metal modes × two tranches against DB-owned "
        "trade logs, open books, daily NAVs and Sharpe before paper use."
    )
    long_description = (
        "Runs the fixed reference window, not a parameter search. Symbols, "
        "dates and reasons must match exactly; prices, basis and gains allow "
        "reference rounding; daily NAV and Sharpe are checked too (Sharpe "
        "difference below 0.001). Only the replay service can issue a golden "
        "certificate for the current engine and data; there is no bypass. "
        "Inputs and golden references are read from the app's SQLite dataset. "
        "Preserves the reference's unshifted terminal B month-end and suppressed "
        "last-row decisions, unlike the explicitly complete daily calendar. "
        "A historical match is not evidence of future profitability. " + _SAFETY
    )
    category = StrategyCategory.BACKTEST

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return []

    def run(self, params: dict[str, Any]) -> StrategyResult:
        from backtesting.s18.service import run_replay

        return _result(self.id, run_replay())


@register
class S18DailyStrategy(BaseStrategy):
    id = "s18_daily"
    name = "S18 Daily"
    description = (
        "Update the saved S18 portfolio after the close and prepare next-session "
        "instructions. Holdings, cash and trade history persist between runs."
    )
    long_description = (
        "Requires a passing golden certificate for the current engine/data. "
        "Uses DB-owned history and warm-up, and collects official NSE inputs "
        "automatically. No external reference or forward folder is needed. "
        "Pre-inception prices warm up signals without inventing old "
        "constituent snapshots or paper trades. Missing expected data blocks the run. "
        "Starts from cash on the first requested available session, never "
        "seeds reference positions, and catches up every subsequent session. "
        "S2 starts with five zero capacity-history entries for a genuine "
        "five-session wait, unlike legacy reference initialization. "
        "A reviews at month-end; B reviews ten sessions earlier. Use a "
        "separate portfolio ID for an independent book. No scheduler "
        "is enabled automatically. " + _SAFETY
    )
    category = StrategyCategory.SWING

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec(
                "book_id",
                "Portfolio ID",
                ParamType.STRING,
                default="default",
                help=(
                    "Stable identity for the saved portfolio. A new ID creates "
                    "a separate portfolio from cash; it never resets this one."
                ),
                group="Portfolio",
            ),
            ParamSpec(
                "as_of",
                "As of (after close)",
                ParamType.DATE,
                default=date.today().isoformat(),
                tracks_today=True,
                help=(
                    "Process available sessions through this date. A new book "
                    "starts from cash, not from the reference open positions."
                ),
                group="Daily update",
            ),
            ParamSpec(
                "persist",
                "Save portfolio updates",
                ParamType.BOOL,
                default=True,
                help=(
                    "Off previews the same model without changing the saved "
                    "portfolio. The workbench still records the run report."
                ),
                group="Daily update",
            ),
            *_book_specs(),
            ParamSpec(
                "shadow_charges",
                "Contract-note charges by model fill ID (shadow only)",
                ParamType.JSON,
                default={},
                help=(
                    'Map IDs from the model fills table, e.g. {"A-1": {"stt": 2}}. '
                    "Allowed nonnegative numeric amounts: stt, stamp_duty, "
                    "exchange_fees, gst, dp_charges, brokerage, other. Empty {} "
                    "changes nothing. Updates actual_charges/charge_breakdown "
                    "only, never model cash, basis, NAV or stop fills."
                ),
                group="Shadow costs",
                advanced=True,
            ),
        ]

    def run(self, params: dict[str, Any]) -> StrategyResult:
        from backtesting.s18.service import run_daily

        output = run_daily(
            combo=params["combo"],
            metal_mode=params["metal_mode"],
            as_of=params.get("as_of"),
            capital=params["capital"],
            book_id=params["book_id"],
            persist=params["persist"],
            shadow_charges=_shadow_charges(params.get("shadow_charges")),
        )
        return _result(self.id, output)
