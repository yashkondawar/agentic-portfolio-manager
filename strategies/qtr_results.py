"""Quarterly-results momentum strategy.

Wraps the ``qtr_results`` engine — a hybrid system that discovers companies
which have just declared quarterly results (Copilot CLI web-grounding),
verifies their QoQ/YoY numbers on screener.in, picks strong results with
10-20% PE-rerating upside, assigns a trailing stop (target/2), and tracks every
pick to exit via a persistent ledger and long-term memory.
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)
from qtr_results import config


@register
class QuarterlyResultsStrategy(BaseStrategy):
    id = "qtr_results"
    name = "Quarterly Results Momentum"
    description = (
        "Buy stocks that just posted strong QoQ/YoY results for a short-term "
        "10-20% move, with a trailing stop and full pick-to-exit tracking."
    )
    long_description = (
        "Each run it discovers NSE companies that have just declared quarterly "
        "results (GitHub Copilot CLI + web grounding), verifies the numbers on "
        "screener.in (QoQ/YoY sales, net profit, EPS, margins), and selects the "
        "strong results. Targets are set by PE re-rating (fair price = P/E × new "
        "TTM EPS) capped to the 10-20% band, with a static fallback and a dynamic "
        "trailing stop at target/2 over a ~3-week window. A persistent ledger "
        "tracks each pick to its exit and a long-term memory accumulates realized "
        "outcomes and learnings across the year."
    )
    category = StrategyCategory.SWING

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        return [
            ParamSpec(
                name="use_llm",
                label="Web-grounded discovery",
                type=ParamType.BOOL,
                required=False,
                default=True,
                help="On = Copilot CLI finds the day's result-declarers; Off = use the watchlist as declarers.",
            ),
            ParamSpec(
                name="use_nse",
                label="NSE assured discovery",
                type=ParamType.BOOL,
                required=False,
                default=True,
                help="Use the NSE corporate-filings feed (authoritative just-declared results) alongside web search.",
            ),
            ParamSpec(
                name="nse_delta",
                label="NSE delta mode",
                type=ParamType.BOOL,
                required=False,
                default=True,
                help="On = fetch the full NSE results table once/day and act only on newly-filed results (via a persistent seen-cache). Off = use a fixed lookback_days window.",
            ),
            ParamSpec(
                name="upcoming_days",
                label="Upcoming NSE window (days)",
                type=ParamType.INT,
                required=False,
                default=14,
                min=0,
                help="Show companies scheduled to declare results in the next N days (NSE events calendar). 0 = off.",
            ),
            ParamSpec(
                name="watchlist",
                label="Watchlist symbols",
                type=ParamType.SYMBOLS,
                required=False,
                default=[],
                help="Optional NSE tickers to seed/limit discovery (or use directly when web-grounding is off).",
            ),
            ParamSpec(
                name="lookback_days",
                label="Result lookback (days)",
                type=ParamType.INT,
                required=False,
                default=config.DEFAULT_LOOKBACK_DAYS,
                min=1,
                help="Treat results declared within this many days (incl. today) as 'just declared'.",
            ),
            ParamSpec(
                name="max_new",
                label="Max new buys per run",
                type=ParamType.INT,
                required=False,
                default=10,
                min=1,
            ),
            ParamSpec(
                name="max_analyze",
                label="Max symbols to verify",
                type=ParamType.INT,
                required=False,
                default=40,
                min=1,
                help="Cap on how many discovered names to scrape/verify on screener.in.",
            ),
            ParamSpec(
                name="min_yoy_profit_growth",
                label="Min YoY net-profit growth (%)",
                type=ParamType.FLOAT,
                required=False,
                default=config.MIN_YOY_PROFIT_GROWTH,
                min=0,
            ),
            ParamSpec(
                name="target_min_pct",
                label="Target floor (%)",
                type=ParamType.FLOAT,
                required=False,
                default=config.TARGET_MIN_PCT,
                min=0,
            ),
            ParamSpec(
                name="target_max_pct",
                label="Target cap (%)",
                type=ParamType.FLOAT,
                required=False,
                default=config.TARGET_MAX_PCT,
                min=0,
            ),
            ParamSpec(
                name="model",
                label="Copilot model",
                type=ParamType.STRING,
                required=False,
                default=None,
                help="Optional model id for the discovery LLM run.",
            ),
            ParamSpec(
                name="dry_run",
                label="Dry run (don't persist)",
                type=ParamType.BOOL,
                required=False,
                default=False,
                help="Compute and report without writing to the ledger or memory.",
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        from qtr_results import engine

        out = engine.run(params)
        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=out["report"],
            data=out["data"],
        )
