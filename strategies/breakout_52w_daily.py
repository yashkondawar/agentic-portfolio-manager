"""Registered daily 52-week breakout scanner and paper portfolio."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from backtesting.breakout_52w.config import BreakoutConfig
from backtesting.breakout_52w.daily import run_daily
from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)


@register
class Breakout52WeekDailyStrategy(BaseStrategy):
    id = "breakout_52w_daily"
    name = "52-Week Breakout Daily"
    description = (
        "Scan the Nifty 500, manage the strategy's paper portfolio, and produce "
        "today's hold, exit, and next-session entry actions."
    )
    long_description = (
        "A deterministic daily state machine. Qualifying close-of-day breakouts "
        "are queued for the next session, validated and sized at that session's "
        "open, then tracked through a 1 ATR hard stop, 4 ATR standing target, "
        "false-breakout exits, trailing exits, and dead-money exits. State persists locally "
        "and can also be supplied or exported as JSON; Zerodha is not used."
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
                help="Run after the market close. Weekends resolve to the latest session.",
                group="Daily run",
            ),
            ParamSpec(
                "capital",
                "Initial strategy capital (₹)",
                ParamType.FLOAT,
                default=500_000.0,
                min=1,
                help="Used only when creating or resetting the paper portfolio.",
                group="Daily run",
            ),
            ParamSpec(
                "universe_index",
                "Scanning universe",
                ParamType.ENUM,
                default="nifty500",
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
                group="Discovery",
            ),
            ParamSpec(
                "symbols",
                "Custom symbols (optional override)",
                ParamType.SYMBOLS,
                default=[],
                help=(
                    "Leave empty to scan the selected index. Supplying symbols "
                    "replaces the index universe for focused runs."
                ),
                group="Discovery",
            ),
            ParamSpec(
                "max_new_entries",
                "Maximum new signals per run",
                ParamType.INT,
                default=5,
                min=1,
                group="Discovery",
            ),
            ParamSpec(
                "portfolio_state",
                "Portfolio state override (JSON)",
                ParamType.JSON,
                default={},
                help=(
                    "Optional state exported by a prior run. Leave empty to use "
                    "the locally persisted strategy portfolio."
                ),
                group="Portfolio state",
                advanced=True,
            ),
            ParamSpec(
                "persist_state",
                "Persist the next portfolio state",
                ParamType.BOOL,
                default=True,
                group="Portfolio state",
            ),
            ParamSpec(
                "reset_state",
                "Reset the strategy portfolio",
                ParamType.BOOL,
                default=False,
                help="Start again with the configured initial capital.",
                group="Portfolio state",
                advanced=True,
            ),
            ParamSpec(
                "adopt_state_override",
                "Replace local portfolio with state override",
                ParamType.BOOL,
                default=False,
                help=(
                    "When enabled, a supplied portfolio_state becomes the new "
                    "locally persisted state. Otherwise overrides are read-only."
                ),
                group="Portfolio state",
                advanced=True,
            ),
            ParamSpec(
                "min_volume_ratio",
                "Minimum relative volume",
                ParamType.FLOAT,
                default=2.0,
                min=1,
                group="Entry filters",
            ),
            ParamSpec(
                "min_breakout_pct",
                "Minimum close above breakout (%)",
                ParamType.FLOAT,
                default=0.5,
                min=0,
                group="Entry filters",
            ),
            ParamSpec(
                "min_relative_strength_3m_pct",
                "Minimum 3-month relative strength (pp)",
                ParamType.FLOAT,
                default=15.0,
                help="Stock return minus Nifty return over 63 trading sessions.",
                group="Entry filters",
            ),
            ParamSpec(
                "min_sma50_slope_pct",
                "Minimum 50-day SMA rise over 20 sessions (%)",
                ParamType.FLOAT,
                default=2.0,
                group="Entry filters",
            ),
            ParamSpec(
                "min_average_volume",
                "Minimum 50-day average shares",
                ParamType.FLOAT,
                default=500_000.0,
                min=0,
                group="Entry filters",
            ),
            ParamSpec(
                "min_turnover_cr",
                "Minimum average turnover (₹ crore)",
                ParamType.FLOAT,
                default=5.0,
                min=0,
                group="Entry filters",
            ),
            ParamSpec(
                "risk_per_trade_pct",
                "Risk per trade (%)",
                ParamType.FLOAT,
                default=1.0,
                min=0,
                max=100,
                group="Portfolio risk",
            ),
            ParamSpec(
                "max_open_risk_pct",
                "Maximum total open risk (%)",
                ParamType.FLOAT,
                default=5.0,
                min=0,
                max=100,
                group="Portfolio risk",
            ),
            ParamSpec(
                "max_positions",
                "Maximum concurrent positions",
                ParamType.INT,
                default=5,
                min=1,
                group="Portfolio risk",
            ),
            ParamSpec(
                "atr_stop_mult",
                "Initial ATR stop multiple",
                ParamType.FLOAT,
                default=1.5,
                min=0.1,
                group="Trade management",
            ),
            ParamSpec(
                "chandelier_atr_mult",
                "Chandelier trail width (ATR)",
                ParamType.FLOAT,
                default=4.0,
                min=0.1,
                group="Trade management",
            ),
            ParamSpec(
                "partial_profit_atr",
                "Partial booking level (ATR)",
                ParamType.FLOAT,
                default=3.5,
                min=0.1,
                group="Trade management",
            ),
            ParamSpec(
                "partial_profit_fraction",
                "Fraction booked at partial target",
                ParamType.FLOAT,
                default=0.20,
                min=0.0,
                max=1.0,
                group="Trade management",
            ),
            ParamSpec(
                "profit_target_atr",
                "Profit target (ATR)",
                ParamType.FLOAT,
                default=4.0,
                min=0.1,
                group="Trade management",
            ),
            ParamSpec(
                "trail_method",
                "Trailing exit",
                ParamType.ENUM,
                default="chandelier",
                choices=["chandelier", "sma20"],
                group="Trade management",
            ),
            ParamSpec(
                "time_exit_sessions",
                "Dead-money exit (trading sessions)",
                ParamType.INT,
                default=10,
                min=1,
                group="Trade management",
            ),
            ParamSpec(
                "earnings_blackout_sessions",
                "Earnings blackout (trading sessions)",
                ParamType.INT,
                default=5,
                min=1,
                group="Guardrails",
            ),
            ParamSpec(
                "enforce_earnings_blackout",
                "Enforce NSE earnings blackout",
                ParamType.BOOL,
                default=True,
                group="Guardrails",
            ),
            ParamSpec(
                "use_cache",
                "Reuse today's downloaded data",
                ParamType.BOOL,
                default=True,
                group="Advanced",
                advanced=True,
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        cfg = BreakoutConfig(
            starting_capital=float(params["capital"]),
            universe_index=params["universe_index"],
            min_volume_ratio=float(params["min_volume_ratio"]),
            min_breakout_pct=float(params["min_breakout_pct"]),
            min_relative_strength_3m_pct=float(params["min_relative_strength_3m_pct"]),
            min_sma50_slope_pct=float(params["min_sma50_slope_pct"]),
            min_average_volume=float(params["min_average_volume"]),
            min_turnover_cr=float(params["min_turnover_cr"]),
            risk_per_trade_pct=float(params["risk_per_trade_pct"]),
            max_open_risk_pct=float(params["max_open_risk_pct"]),
            max_positions=int(params["max_positions"]),
            atr_stop_mult=float(params["atr_stop_mult"]),
            chandelier_atr_mult=float(params["chandelier_atr_mult"]),
            partial_profit_atr=float(params["partial_profit_atr"]),
            partial_profit_fraction=float(params["partial_profit_fraction"]),
            profit_target_atr=float(params["profit_target_atr"]),
            trail_method=params["trail_method"],
            time_exit_sessions=int(params["time_exit_sessions"]),
            earnings_blackout_sessions=int(params["earnings_blackout_sessions"]),
            enforce_earnings_blackout=bool(params["enforce_earnings_blackout"]),
            use_cache=bool(params["use_cache"]),
        )
        output = run_daily(
            cfg,
            portfolio_state=params.get("portfolio_state") or None,
            symbols=params.get("symbols") or [],
            as_of=date.fromisoformat(params["as_of"]),
            max_new_entries=int(params["max_new_entries"]),
            persist_state=bool(params["persist_state"]),
            reset_state=bool(params["reset_state"]),
            adopt_state_override=bool(params["adopt_state_override"]),
        )
        report = output.pop("report")
        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=report,
            data=output,
        )
