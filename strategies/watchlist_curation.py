"""Watchlist curation strategy.

Wraps ``watchlist_curator`` — a two-stage funnel that mechanically screens a
large universe (Nifty 500 by default) for swing-suitable momentum/trend/
liquidity, then (optionally) uses your configured AI provider + scraper MCP to
deeply vet the shortlist and emit a final, ranked watchlist.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from core.config import DEFAULT_WATCHLIST_FINAL_SIZE, DEFAULT_WATCHLIST_INDEX
from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)


@register
class WatchlistCurationStrategy(BaseStrategy):
    id = "watchlist_curation"
    name = "Watchlist Curator"
    description = (
        "Screen a large universe for swing-suitable names, then optionally "
        "vet the shortlist with an LLM to produce a ranked watchlist."
    )
    long_description = (
        "Stage 1 mechanically screens the universe (SMA stack, RSI, ATR%, "
        "returns, relative strength, liquidity) into an industry-diversified "
        "shortlist. Stage 2 (optional, LLM) deeply vets fundamentals, "
        "financials and technicals via your AI provider + scraper MCP and emits "
        "the final ranked watchlist."
    )
    category = StrategyCategory.WATCHLIST

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        return [
            ParamSpec(
                name="index",
                label="Universe index",
                type=ParamType.ENUM,
                required=False,
                default=DEFAULT_WATCHLIST_INDEX,
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
                help="NSE index to screen, e.g. nifty500, nifty200, nifty50.",
                group="Universe",
            ),
            ParamSpec(
                name="universe",
                label="Custom universe symbols",
                type=ParamType.SYMBOLS,
                required=False,
                default=[],
                help="Optional symbols that replace the selected index.",
                group="Universe",
            ),
            ParamSpec(
                name="final_size",
                label="Final watchlist size",
                type=ParamType.INT,
                required=False,
                default=DEFAULT_WATCHLIST_FINAL_SIZE,
                min=1,
                group="Output",
            ),
            ParamSpec(
                name="shortlist_size",
                label="Stage-1 shortlist size",
                type=ParamType.INT,
                required=False,
                default=40,
                min=1,
                group="Screen",
            ),
            ParamSpec(
                name="period",
                label="History period",
                type=ParamType.STRING,
                required=False,
                default="1y",
                help="yfinance period for metrics, e.g. 6mo, 1y, 2y.",
                group="Universe",
            ),
            ParamSpec(
                name="min_price",
                label="Minimum share price (₹)",
                type=ParamType.FLOAT,
                default=50.0,
                min=0,
                group="Screen",
            ),
            ParamSpec(
                name="min_liquidity_cr",
                label="Minimum daily liquidity (₹ crore)",
                type=ParamType.FLOAT,
                default=5.0,
                min=0,
                group="Screen",
            ),
            ParamSpec(
                name="rsi_min",
                label="Minimum RSI(14)",
                type=ParamType.FLOAT,
                default=45.0,
                min=0,
                max=100,
                group="Screen",
            ),
            ParamSpec(
                name="rsi_max",
                label="Maximum RSI(14)",
                type=ParamType.FLOAT,
                default=80.0,
                min=0,
                max=100,
                group="Screen",
            ),
            ParamSpec(
                name="max_atr_pct",
                label="Maximum ATR (%)",
                type=ParamType.FLOAT,
                default=9.0,
                min=0,
                group="Screen",
            ),
            ParamSpec(
                name="require_sma_stack",
                label="Require price > SMA50 > SMA200",
                type=ParamType.BOOL,
                default=True,
                group="Screen",
            ),
            ParamSpec(
                name="require_positive_rel_strength",
                label="Require positive relative strength",
                type=ParamType.BOOL,
                default=False,
                group="Screen",
            ),
            ParamSpec(
                name="max_per_industry",
                label="Maximum names per industry",
                type=ParamType.INT,
                default=3,
                min=0,
                group="Screen",
            ),
            ParamSpec(
                name="use_llm",
                label="Run Stage-2 LLM curation",
                type=ParamType.BOOL,
                required=False,
                default=False,
                help="Off = fast mechanical shortlist only; On = deep LLM vetting.",
                group="Output",
            ),
            ParamSpec(
                name="target_profit_pct",
                label="Target profit per trade (%)",
                type=ParamType.FLOAT,
                default=20.0,
                min=0,
                group="Output",
            ),
            ParamSpec(
                name="max_holding_days",
                label="Maximum holding period (days)",
                type=ParamType.INT,
                default=30,
                min=1,
                group="Output",
            ),
            ParamSpec(
                name="model",
                label="Copilot model",
                type=ParamType.STRING,
                default=None,
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="web_grounding",
                label="Use live web grounding",
                type=ParamType.BOOL,
                default=True,
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="scraper_tools",
                label="Use local market-data tools",
                type=ParamType.BOOL,
                default=True,
                group="Advanced",
                advanced=True,
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        import watchlist_curator as wc

        index = params.get("index") or DEFAULT_WATCHLIST_INDEX
        period = params.get("period") or "1y"
        final_size = int(params.get("final_size") or DEFAULT_WATCHLIST_FINAL_SIZE)
        shortlist_size = int(params.get("shortlist_size") or 40)

        custom_universe = params.get("universe") or []
        universe = (
            [wc.UniverseStock(symbol=symbol) for symbol in custom_universe]
            if custom_universe
            else wc.load_universe_from_index(index)
        )
        metrics = wc.download_and_compute(universe, period=period)
        if not metrics:
            raise RuntimeError("No metrics computed (check connectivity / symbols).")

        screen_cfg = wc.ScreenConfig(
            min_price=float(params.get("min_price", 50.0)),
            min_liquidity_cr=float(params.get("min_liquidity_cr", 5.0)),
            rsi_min=float(params.get("rsi_min", 45.0)),
            rsi_max=float(params.get("rsi_max", 80.0)),
            max_atr_pct=float(params.get("max_atr_pct", 9.0)),
            require_above_200=bool(params.get("require_sma_stack", True)),
            require_sma_stack=bool(params.get("require_sma_stack", True)),
            require_positive_rel_strength=bool(
                params.get("require_positive_rel_strength", False)
            ),
            shortlist_size=shortlist_size,
            max_per_industry=int(params.get("max_per_industry") or 0),
        )
        shortlist = wc.score_and_rank(metrics, screen_cfg)
        if not shortlist:
            raise RuntimeError("No symbols passed the Stage-1 filters.")

        table = wc.render_shortlist_table(shortlist)

        if not params.get("use_llm"):
            report = (
                f"# Mechanical Swing Watchlist — {index}\n\n"
                f"{len(shortlist)} names passed Stage-1 screening.\n\n{table}\n"
            )
            picks = [asdict(m) for m in shortlist]
            artifact_group_id = wc.persist_watchlist(
                picks,
                index=index,
                report=report,
                shortlist=table,
            )
            return StrategyResult(
                strategy_id=self.id,
                status="completed",
                report=report,
                data={
                    "index": index,
                    "stage": 1,
                    "picks": picks,
                    "artifact_group_id": artifact_group_id,
                },
            )

        prompt = wc.build_curation_prompt(
            shortlist,
            final_size=final_size,
            target_profit=float(params.get("target_profit_pct", 20.0)),
            max_holding_days=int(params.get("max_holding_days") or 30),
            web_grounding=bool(params.get("web_grounding", True)),
            scraper_tools=bool(params.get("scraper_tools", True)),
        )
        llm_output = wc.invoke_copilot(
            prompt,
            model=params.get("model") or None,
            web_grounding=bool(params.get("web_grounding", True)),
            scraper_tools=bool(params.get("scraper_tools", True)),
            copilot_log=None,
            log_level="debug",
        )
        picks = wc.parse_curated_watchlist(llm_output)
        artifact_group_id = wc.persist_watchlist(
            picks,
            index=index,
            report=llm_output,
            shortlist=table,
        )

        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=llm_output,
            data={
                "index": index,
                "stage": 2,
                "picks": picks,
                "shortlist": [asdict(m) for m in shortlist],
                "artifact_group_id": artifact_group_id,
            },
        )
