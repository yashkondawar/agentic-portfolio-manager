"""Registered 52-week-high breakout backtest strategy."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from backtesting.breakout_52w import BreakoutConfig, run_backtest
from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)


@register
class Breakout52WeekStrategy(BaseStrategy):
    id = "breakout_52w_backtest"
    name = "52-Week High Breakout"
    description = (
        "Backtest quality 52-week-high breakouts with 2x volume, optimized "
        "risk controls, market regime, and earnings blackout."
    )
    long_description = (
        "Scans the selected NSE universe daily using point-in-time yfinance "
        "OHLCV. Signals require a close at least 0.5% above the prior 252-session high, "
        "20/50/200 SMA alignment, relative strength, a rising 50-day average, "
        "relative volume, liquidity, and limited ATR "
        "extension. Entries fill next session and use volatility-aware sizing, "
        "a 1 ATR hard stop, 4 ATR target, false-breakout exits, trailing stops, "
        "and a dead-money exit."
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
                group="Capital",
            ),
            ParamSpec(
                "goal_pct",
                "Goal return (%)",
                ParamType.FLOAT,
                default=20.0,
                group="Capital",
            ),
            ParamSpec(
                "universe_index",
                "Universe index",
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
                group="Universe",
            ),
            ParamSpec(
                "symbols",
                "Custom symbols (optional override)",
                ParamType.SYMBOLS,
                default=[],
                help="Leave empty to scan the selected index.",
                group="Universe",
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
                "max_extension_atr",
                "Maximum breakout extension (ATR)",
                ParamType.FLOAT,
                default=1.0,
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
                "stop_method",
                "Initial stop method",
                ParamType.ENUM,
                default="atr",
                choices=["atr", "breakout_candle", "wider"],
                group="Trade management",
            ),
            ParamSpec(
                "atr_stop_mult",
                "Initial ATR stop multiple",
                ParamType.FLOAT,
                default=1.0,
                min=0.1,
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
                "time_exit_progress_pct",
                "Required favorable progress (%)",
                ParamType.FLOAT,
                default=5.0,
                min=0,
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
                "Reuse downloaded data",
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
        cfg = BreakoutConfig(
            starting_capital=float(params["capital"]),
            goal_return_pct=float(params["goal_pct"]),
            start_date=date.fromisoformat(params["start"]),
            end_date=date.fromisoformat(params["end"]),
            universe_index=params["universe_index"],
            min_volume_ratio=float(params["min_volume_ratio"]),
            min_average_volume=float(params["min_average_volume"]),
            min_turnover_cr=float(params["min_turnover_cr"]),
            min_breakout_pct=float(params["min_breakout_pct"]),
            min_relative_strength_3m_pct=float(params["min_relative_strength_3m_pct"]),
            min_sma50_slope_pct=float(params["min_sma50_slope_pct"]),
            max_extension_atr=float(params["max_extension_atr"]),
            risk_per_trade_pct=float(params["risk_per_trade_pct"]),
            max_open_risk_pct=float(params["max_open_risk_pct"]),
            max_positions=int(params["max_positions"]),
            stop_method=params["stop_method"],
            atr_stop_mult=float(params["atr_stop_mult"]),
            profit_target_atr=float(params["profit_target_atr"]),
            trail_method=params["trail_method"],
            time_exit_sessions=int(params["time_exit_sessions"]),
            time_exit_progress_pct=float(params["time_exit_progress_pct"]),
            earnings_blackout_sessions=int(params["earnings_blackout_sessions"]),
            enforce_earnings_blackout=bool(params["enforce_earnings_blackout"]),
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
