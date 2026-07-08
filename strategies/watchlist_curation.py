"""Watchlist curation strategy.

Wraps ``watchlist_curator`` — a two-stage funnel that mechanically screens a
large universe (Nifty 500 by default) for swing-suitable momentum/trend/
liquidity, then (optionally) uses the GitHub Copilot CLI + scraper MCP to
deeply vet the shortlist and emit a final, ranked watchlist.
"""

from __future__ import annotations

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
        "financials and technicals via the Copilot CLI + scraper MCP and emits "
        "the final ranked watchlist."
    )
    category = StrategyCategory.WATCHLIST

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        return [
            ParamSpec(
                name="index",
                label="Universe index",
                type=ParamType.STRING,
                required=False,
                default=DEFAULT_WATCHLIST_INDEX,
                help="NSE index to screen, e.g. nifty500, nifty200, nifty50.",
            ),
            ParamSpec(
                name="final_size",
                label="Final watchlist size",
                type=ParamType.INT,
                required=False,
                default=DEFAULT_WATCHLIST_FINAL_SIZE,
                min=1,
            ),
            ParamSpec(
                name="shortlist_size",
                label="Stage-1 shortlist size",
                type=ParamType.INT,
                required=False,
                default=40,
                min=1,
            ),
            ParamSpec(
                name="period",
                label="History period",
                type=ParamType.STRING,
                required=False,
                default="1y",
                help="yfinance period for metrics, e.g. 6mo, 1y, 2y.",
            ),
            ParamSpec(
                name="use_llm",
                label="Run Stage-2 LLM curation",
                type=ParamType.BOOL,
                required=False,
                default=False,
                help="Off = fast mechanical shortlist only; On = deep LLM vetting.",
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        import watchlist_curator as wc

        index = params.get("index") or DEFAULT_WATCHLIST_INDEX
        period = params.get("period") or "1y"
        final_size = int(params.get("final_size") or DEFAULT_WATCHLIST_FINAL_SIZE)
        shortlist_size = int(params.get("shortlist_size") or 40)

        universe = wc.load_universe_from_index(index)
        metrics = wc.download_and_compute(universe, period=period)
        if not metrics:
            raise RuntimeError("No metrics computed (check connectivity / symbols).")

        screen_cfg = wc.ScreenConfig(shortlist_size=shortlist_size)
        shortlist = wc.score_and_rank(metrics, screen_cfg)
        if not shortlist:
            raise RuntimeError("No symbols passed the Stage-1 filters.")

        table = wc.render_shortlist_table(shortlist)

        if not params.get("use_llm"):
            report = (
                f"# Mechanical Swing Watchlist — {index}\n\n"
                f"{len(shortlist)} names passed Stage-1 screening.\n\n{table}\n"
            )
            picks = [{"symbol": m.symbol} for m in shortlist]
            return StrategyResult(
                strategy_id=self.id,
                status="completed",
                report=report,
                data={"index": index, "stage": 1, "picks": picks},
            )

        prompt = wc.build_curation_prompt(
            shortlist,
            final_size=final_size,
            target_profit=20.0,
            max_holding_days=30,
            web_grounding=True,
            scraper_tools=True,
        )
        llm_output = wc.invoke_copilot(
            prompt,
            model=None,
            web_grounding=True,
            scraper_tools=True,
            copilot_log=None,
            log_level="debug",
        )
        picks = wc.parse_curated_watchlist(llm_output)

        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=llm_output,
            data={"index": index, "stage": 2, "picks": picks},
        )
