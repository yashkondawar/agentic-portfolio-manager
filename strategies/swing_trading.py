"""Swing-trading strategy.

Wraps ``swing_trading_copilot`` — a daily swing-trading copilot that reviews
open positions, screens a watchlist for new entries and gives capital-rotation
guidance by shelling out to the GitHub Copilot CLI with the scraper MCP tools.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.config import DEFAULT_MAX_HOLDING_DAYS, DEFAULT_TARGET_PROFIT_PCT
from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)


@register
class SwingTradingStrategy(BaseStrategy):
    id = "swing_trading"
    name = "Swing Trading Copilot"
    description = (
        "Daily swing-trade review: manage open positions, screen the "
        "watchlist for new entries, and plan capital rotation."
    )
    long_description = (
        "Purpose-built for short-term swing trading. Triages every open "
        "position (exit / trim / hold / trail / add) with concrete levels, "
        "screens a watchlist for fresh 20%-in-a-month setups, and gives "
        "portfolio-level risk and capital-rotation guidance. Runs through the "
        "GitHub Copilot CLI + scraper MCP (no API keys required)."
    )
    category = StrategyCategory.SWING

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        return [
            ParamSpec(
                name="template",
                label="Review mode",
                type=ParamType.ENUM,
                required=False,
                default="daily",
                choices=["daily", "manage", "discover"],
                help="daily=full review, manage=positions only, discover=new entries only.",
            ),
            ParamSpec(
                name="positions",
                label="Open positions (JSON)",
                type=ParamType.JSON,
                required=False,
                default=[],
                help='List of {"symbol","quantity","buy_price",...} open swing positions.',
                group="Positions",
            ),
            ParamSpec(
                name="watchlist",
                label="Watchlist symbols",
                type=ParamType.SYMBOLS,
                required=False,
                default=[],
                help="Candidate NSE tickers to evaluate for new entries.",
                group="Watchlist",
            ),
            ParamSpec(
                name="prompt",
                label="Extra directive",
                type=ParamType.TEXT,
                required=False,
                default="",
                help="Optional free-form instruction; defaults to the mode's directive.",
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="total_capital",
                label="Total swing capital (₹)",
                type=ParamType.FLOAT,
                required=False,
                default=None,
                help="Capital allocated to swing trading.",
                min=0,
                group="Capital & risk",
            ),
            ParamSpec(
                name="cash_available",
                label="Cash available (₹)",
                type=ParamType.FLOAT,
                required=False,
                default=None,
                min=0,
                group="Capital & risk",
            ),
            ParamSpec(
                name="target_profit_pct",
                label="Target profit per trade (%)",
                type=ParamType.FLOAT,
                required=False,
                default=DEFAULT_TARGET_PROFIT_PCT,
                min=0,
                group="Capital & risk",
            ),
            ParamSpec(
                name="max_holding_days",
                label="Max holding window (days)",
                type=ParamType.INT,
                required=False,
                default=DEFAULT_MAX_HOLDING_DAYS,
                min=1,
                group="Capital & risk",
            ),
            ParamSpec(
                name="risk_per_trade_pct",
                label="Risk per trade (%)",
                type=ParamType.FLOAT,
                required=False,
                default=2.0,
                min=0,
                max=100,
                group="Capital & risk",
            ),
            ParamSpec(
                name="min_rr",
                label="Minimum reward:risk",
                type=ParamType.FLOAT,
                required=False,
                default=2.0,
                min=0,
                group="Capital & risk",
            ),
            ParamSpec(
                name="max_positions",
                label="Maximum open positions",
                type=ParamType.INT,
                required=False,
                default=None,
                min=1,
                group="Capital & risk",
            ),
            ParamSpec(
                name="risk_appetite",
                label="Risk appetite",
                type=ParamType.ENUM,
                required=False,
                default=None,
                choices=["Low", "Moderate", "High"],
                group="Capital & risk",
            ),
            ParamSpec(
                name="model",
                label="Copilot model",
                type=ParamType.STRING,
                required=False,
                default=None,
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="web_grounding",
                label="Use live web grounding",
                type=ParamType.BOOL,
                required=False,
                default=True,
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="scraper_tools",
                label="Use local market-data tools",
                type=ParamType.BOOL,
                required=False,
                default=True,
                group="Advanced",
                advanced=True,
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        import swing_trading_copilot as swing

        positions = swing.load_positions_from_json(params.get("positions") or [])
        watchlist: List[str] = params.get("watchlist") or []

        template = swing.resolve_template(params.get("template") or "daily")
        user_prompt = (params.get("prompt") or "").strip() or template.default_directive

        cfg = swing.SwingConfig(
            total_capital=_opt_float(params.get("total_capital")),
            cash_available=_opt_float(params.get("cash_available")),
            target_profit_pct=float(
                params.get("target_profit_pct", DEFAULT_TARGET_PROFIT_PCT)
            ),
            max_holding_days=int(
                params.get("max_holding_days") or DEFAULT_MAX_HOLDING_DAYS
            ),
            risk_per_trade_pct=float(params.get("risk_per_trade_pct", 2.0)),
            min_rr=float(params.get("min_rr", 2.0)),
            max_positions=_opt_int(params.get("max_positions")),
            risk_appetite=params.get("risk_appetite") or None,
        )

        report = swing.run_analysis(
            positions=positions,
            watchlist=watchlist,
            user_prompt=user_prompt,
            cfg=cfg,
            template=template,
            model=params.get("model") or None,
            web_grounding=bool(params.get("web_grounding", True)),
            scraper_tools=bool(params.get("scraper_tools", True)),
        )

        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=report,
            data={
                "template": template.name,
                "num_positions": len(positions),
                "watchlist_size": len(watchlist),
            },
        )


def _opt_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def _opt_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)
