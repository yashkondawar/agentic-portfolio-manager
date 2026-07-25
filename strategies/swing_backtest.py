"""Point-in-time swing strategy backtest."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from backtesting.swing_trading.config import BacktestConfig
from backtesting.swing_trading.service import run_backtest
from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)


@register
class SwingBacktestStrategy(BaseStrategy):
    id = "swing_backtest"
    name = "Swing Strategy Backtest"
    description = (
        "Validate the deterministic swing playbook on point-in-time historical "
        "data with next-session fills and trading costs."
    )
    long_description = (
        "Rebuilds the mechanical watchlist at each historical month using only "
        "data available at that date, applies the live swing entry/exit rules, "
        "and reports risk, return, trade, and exposure metrics."
    )
    category = StrategyCategory.BACKTEST

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        today = date.today()
        return [
            ParamSpec(
                "start",
                "Start date",
                ParamType.DATE,
                default=(today - timedelta(days=365)).isoformat(),
                group="Window",
            ),
            ParamSpec(
                "end",
                "End date",
                ParamType.DATE,
                default=today.isoformat(),
                group="Window",
            ),
            ParamSpec(
                "capital",
                "Starting capital (₹)",
                ParamType.FLOAT,
                default=500_000.0,
                min=1,
                group="Capital & goal",
            ),
            ParamSpec(
                "goal_pct",
                "Goal return (%)",
                ParamType.FLOAT,
                default=20.0,
                group="Capital & goal",
            ),
            ParamSpec(
                "universe_index",
                "Universe index",
                ParamType.ENUM,
                default="nifty200",
                choices=[
                    "nifty50",
                    "niftynext50",
                    "nifty100",
                    "nifty200",
                    "nifty500",
                    "niftymidcap100",
                    "niftymidcap150",
                    "niftysmallcap250",
                ],
                group="Universe",
            ),
            ParamSpec(
                "symbols",
                "Custom universe symbols",
                ParamType.SYMBOLS,
                default=[],
                help="Optional symbols that replace the selected index.",
                group="Universe",
            ),
            ParamSpec(
                "watchlist_size",
                "Monthly watchlist size",
                ParamType.INT,
                default=20,
                min=1,
                group="Portfolio rules",
            ),
            ParamSpec(
                "max_positions",
                "Maximum concurrent positions",
                ParamType.INT,
                default=8,
                min=1,
                group="Portfolio rules",
            ),
            ParamSpec(
                "target_pct",
                "Target return per trade (%)",
                ParamType.FLOAT,
                default=20.0,
                min=0,
                group="Trade rules",
            ),
            ParamSpec(
                "max_holding_days",
                "Maximum holding period (days)",
                ParamType.INT,
                default=30,
                min=1,
                group="Trade rules",
            ),
            ParamSpec(
                "risk_per_trade",
                "Risk per trade (%)",
                ParamType.FLOAT,
                default=2.0,
                min=0,
                max=100,
                group="Trade rules",
            ),
            ParamSpec(
                "min_rr",
                "Minimum reward:risk",
                ParamType.FLOAT,
                default=2.0,
                min=0,
                group="Trade rules",
            ),
            ParamSpec(
                "use_cache",
                "Reuse downloaded prices",
                ParamType.BOOL,
                default=True,
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                "commission_pct",
                "Commission per side (%)",
                ParamType.FLOAT,
                default=0.05,
                min=0,
                group="Advanced",
                advanced=True,
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        cfg = BacktestConfig(
            starting_capital=float(params["capital"]),
            goal_return_pct=float(params["goal_pct"]),
            start_date=date.fromisoformat(params["start"]),
            end_date=date.fromisoformat(params["end"]),
            universe_index=params["universe_index"],
            watchlist_size=int(params["watchlist_size"]),
            max_positions=int(params["max_positions"]),
            target_profit_pct=float(params["target_pct"]),
            max_holding_days=int(params["max_holding_days"]),
            risk_per_trade_pct=float(params["risk_per_trade"]),
            min_rr=float(params["min_rr"]),
            use_cache=bool(params["use_cache"]),
            commission_pct=float(params["commission_pct"]),
        )
        output = run_backtest(cfg, symbols=params.get("symbols") or [])
        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=output["summary"],
            data={key: value for key, value in output.items() if key != "summary"},
        )
