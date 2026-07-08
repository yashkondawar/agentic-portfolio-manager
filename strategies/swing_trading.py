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
            ),
            ParamSpec(
                name="watchlist",
                label="Watchlist symbols",
                type=ParamType.SYMBOLS,
                required=False,
                default=[],
                help="Candidate NSE tickers to evaluate for new entries.",
            ),
            ParamSpec(
                name="prompt",
                label="Extra directive",
                type=ParamType.TEXT,
                required=False,
                default="",
                help="Optional free-form instruction; defaults to the mode's directive.",
            ),
            ParamSpec(
                name="total_capital",
                label="Total swing capital (₹)",
                type=ParamType.FLOAT,
                required=False,
                default=None,
                help="Capital allocated to swing trading.",
                min=0,
            ),
            ParamSpec(
                name="target_profit_pct",
                label="Target profit per trade (%)",
                type=ParamType.FLOAT,
                required=False,
                default=DEFAULT_TARGET_PROFIT_PCT,
                min=0,
            ),
            ParamSpec(
                name="max_holding_days",
                label="Max holding window (days)",
                type=ParamType.INT,
                required=False,
                default=DEFAULT_MAX_HOLDING_DAYS,
                min=1,
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
            target_profit_pct=float(
                params.get("target_profit_pct") or DEFAULT_TARGET_PROFIT_PCT
            ),
            max_holding_days=int(
                params.get("max_holding_days") or DEFAULT_MAX_HOLDING_DAYS
            ),
        )

        report = swing.run_analysis(
            positions=positions,
            watchlist=watchlist,
            user_prompt=user_prompt,
            cfg=cfg,
            template=template,
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
