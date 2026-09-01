"""Registered daily runner for the all-time-high breakout sleeve."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from backtesting.breakout_ath.config import AthBreakoutConfig
from backtesting.breakout_ath.daily import run_daily
from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)


@register
class BreakoutAthDailyStrategy(BaseStrategy):
    id = "breakout_ath_daily"
    name = "ATH Breakout Daily"
    description = (
        "Scan the Nifty Total Market 750 for stocks closing at a 52-week high "
        "near their lifetime high, and manage the sleeve's book."
    )
    long_description = (
        "A trail-only momentum sleeve. A stock qualifies when it closes above "
        "every close of the prior 252 sessions and is still within 15% of its "
        "lifetime closing high; candidates are ranked by 3-month momentum and "
        "fill whatever of the 28 slots are free, each sized to an equal share "
        "of equity that is re-struck quarterly. There is no profit target and "
        "no time exit: a position is held until its close falls 16% below the "
        "highest close it has made since entry. Entries and exits are computed "
        "with the same functions the backtest uses, so the live sleeve cannot "
        "drift from the validated strategy."
    )
    category = StrategyCategory.SWING

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        return [
            ParamSpec(
                "as_of",
                "Run through date",
                ParamType.DATE,
                default=date.today().isoformat(),
                help="Run after the close. Weekends resolve to the latest session.",
                group="Daily run",
            ),
            ParamSpec(
                "capital",
                "Sleeve capital (₹)",
                ParamType.FLOAT,
                default=10_000_000.0,
                min=1,
                help="Used only when creating or resetting the book.",
                group="Daily run",
            ),
            ParamSpec(
                "max_positions",
                "Maximum concurrent positions",
                ParamType.INT,
                default=28,
                min=1,
                max=100,
                help="Slot count. Each slot gets an equal share of equity.",
                group="Strategy",
            ),
            ParamSpec(
                "sl_pct",
                "Trailing stop (fraction below peak close)",
                ParamType.FLOAT,
                default=0.16,
                min=0.01,
                max=0.99,
                help="0.16 exits when the close is 16% under the highest close since entry.",
                group="Strategy",
            ),
            ParamSpec(
                "ath_band",
                "Maximum distance below lifetime high",
                ParamType.FLOAT,
                default=0.15,
                min=0.0,
                max=0.99,
                help="0.15 requires the close to be within 15% of the lifetime closing high.",
                group="Strategy",
            ),
            ParamSpec(
                "lookback",
                "Breakout lookback (sessions)",
                ParamType.INT,
                default=252,
                min=2,
                help="The close must exceed every close in this many prior sessions.",
                group="Strategy",
            ),
            ParamSpec(
                "selection_rule",
                "Ranking rule",
                ParamType.ENUM,
                default="mom_3m",
                choices=["mom_3m", "mom_6m", "mom_12m"],
                help="How competing candidates are ordered when slots are scarce.",
                group="Strategy",
            ),
            ParamSpec(
                "slot_reset_freq",
                "Position-size reset cadence",
                ParamType.ENUM,
                default="Q",
                choices=["Q", "M", "A", "N"],
                help="How often the per-slot budget is re-struck from equity.",
                group="Strategy",
            ),
            ParamSpec(
                "cost_bps",
                "Round-trip cost (bps per side)",
                ParamType.FLOAT,
                default=25.0,
                min=0.0,
                help="Brokerage plus impact charged on both entry and exit.",
                group="Costs",
            ),
            ParamSpec(
                "download",
                "Refresh prices before scanning",
                ParamType.BOOL,
                default=True,
                help="Turn off to run against the cached bar store.",
                group="Daily run",
            ),
            ParamSpec(
                "persist_state",
                "Save the updated book",
                ParamType.BOOL,
                default=True,
                help="Write the book back to disk after the run.",
                group="Daily run",
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        cfg = AthBreakoutConfig(
            start_capital=float(params["capital"]),
            max_positions=int(params["max_positions"]),
            sl_pct=float(params["sl_pct"]),
            ath_band=float(params["ath_band"]),
            lookback=int(params["lookback"]),
            selection_rule=params["selection_rule"],
            slot_reset_freq=params["slot_reset_freq"],
            cost_bps=float(params["cost_bps"]),
        )
        output = run_daily(
            cfg,
            portfolio_state=params.get("portfolio_state") or None,
            as_of=date.fromisoformat(params["as_of"]),
            download=bool(params["download"]),
            persist=bool(params["persist_state"]),
        )
        report = output.pop("report")
        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=report,
            data=output,
        )
