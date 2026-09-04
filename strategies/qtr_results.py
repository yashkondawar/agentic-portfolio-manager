"""Quarterly-results momentum strategy.

Wraps the ``qtr_results`` engine — a hybrid system that discovers companies
which have just declared quarterly results (AI web-grounding),
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
        "Buy stocks that just posted strong QoQ/YoY results, size each position by "
        "ATR risk against a fixed capital base, ride the winners with an ATR "
        "trailing stop, and track every pick to exit."
    )
    long_description = (
        "Each run it discovers NSE companies that have just declared quarterly "
        "results (needs an AI provider that can search the web), verifies the "
        "numbers on "
        "screener.in (QoQ/YoY sales, net profit, EPS, margins), and selects the "
        "strong results. Positions are sized by the backtest's risk rule (risk % "
        "of equity / ATR-stop distance) against a persisted cash book, capped by a "
        "per-name concentration limit and a max open-position count. Targets are "
        "set by PE re-rating (fair price = P/E x new TTM EPS) but, with "
        "ride-the-wave enabled, act only as a reference — winners exit on a 6x-ATR "
        "trailing stop or the 90-day time-stop. A persistent ledger tracks each "
        "pick to its exit and a long-term memory accumulates realized outcomes."
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
                help=(
                    "On = the AI finds the day's result-declarers (needs a "
                    "provider that can search the web); "
                    "Off = use the watchlist as declarers."
                ),
                group="Discovery",
            ),
            ParamSpec(
                name="use_nse",
                label="NSE assured discovery",
                type=ParamType.BOOL,
                required=False,
                default=True,
                help=(
                    "Use the NSE corporate-filings feed (authoritative just-declared "
                    "results) alongside web search."
                ),
                group="Discovery",
            ),
            ParamSpec(
                name="nse_delta",
                label="NSE delta mode",
                type=ParamType.BOOL,
                required=False,
                default=True,
                help=(
                    "On = fetch the full NSE results table once/day and act only on "
                    "newly-filed results (via a persistent seen-cache). Off = use a "
                    "fixed lookback_days window."
                ),
                group="Discovery",
            ),
            ParamSpec(
                name="upcoming_days",
                label="Upcoming NSE window (days)",
                type=ParamType.INT,
                required=False,
                default=14,
                min=0,
                help=(
                    "Show companies scheduled to declare results in the next N days "
                    "(NSE events calendar). 0 = off."
                ),
                group="Discovery",
            ),
            ParamSpec(
                name="watchlist",
                label="Watchlist symbols",
                type=ParamType.SYMBOLS,
                required=False,
                default=[],
                help=(
                    "Optional NSE tickers to seed/limit discovery (or use directly "
                    "when web-grounding is off)."
                ),
                group="Discovery",
            ),
            ParamSpec(
                name="lookback_days",
                label="Result lookback (days)",
                type=ParamType.INT,
                required=False,
                default=config.DEFAULT_LOOKBACK_DAYS,
                min=1,
                help=(
                    "Treat results declared within this many days (incl. today) as "
                    "'just declared'."
                ),
                group="Discovery",
            ),
            ParamSpec(
                name="max_new",
                label="Max new buys per run",
                type=ParamType.INT,
                required=False,
                default=10,
                min=1,
                group="Selection",
            ),
            ParamSpec(
                name="max_analyze",
                label="Max symbols to verify",
                type=ParamType.INT,
                required=False,
                default=0,
                min=0,
                help=(
                    "Cap on how many discovered names to scrape/verify on "
                    "screener.in. 0 = verify ALL declarers (no index bias; "
                    "~2.5s each). Set a number only for a faster, capped run -- "
                    "watchlist and liquid names are then verified first."
                ),
                group="Selection",
            ),
            ParamSpec(
                name="use_conviction",
                label="Tier-2 LLM conviction",
                type=ParamType.BOOL,
                required=False,
                default=config.USE_CONVICTION_LLM,
                help="On = an LLM reads each shortlisted name's actual filing (results PDF / concall / investor deck) plus recent news, order-book and sector sentiment, then gates/ranks the picks and shapes their exit (high conviction rides toward the target cap with a longer hold).",
            ),
            ParamSpec(
                name="min_yoy_profit_growth",
                label="Min YoY net-profit growth (%)",
                type=ParamType.FLOAT,
                required=False,
                default=config.MIN_YOY_PROFIT_GROWTH,
                min=0,
                group="Selection",
            ),
            ParamSpec(
                name="target_min_pct",
                label="Target floor (%)",
                type=ParamType.FLOAT,
                required=False,
                default=config.TARGET_MIN_PCT,
                min=0,
                group="Risk & exits",
            ),
            ParamSpec(
                name="target_max_pct",
                label="Target cap (%)",
                type=ParamType.FLOAT,
                required=False,
                default=config.TARGET_MAX_PCT,
                min=0,
                group="Risk & exits",
            ),
            ParamSpec(
                name="trailing_stop_ratio",
                label="Trailing-stop ratio (legacy)",
                type=ParamType.FLOAT,
                default=config.TRAILING_STOP_RATIO,
                min=0,
                max=1,
                help=(
                    "Legacy percent-based stop (target x ratio), used only for "
                    "positions opened before ATR sizing / when ATR is unavailable."
                ),
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="max_holding_days",
                label="Maximum holding period (days)",
                type=ParamType.INT,
                default=config.MAX_HOLDING_DAYS,
                min=1,
                help=(
                    "Time-stop: exit any position still open after this many days. "
                    "PEAD drift typically plays out over 30-90 days."
                ),
                group="Risk & exits",
            ),
            ParamSpec(
                name="capital",
                label="Capital base (Rs)",
                type=ParamType.FLOAT,
                required=False,
                default=config.STARTING_CAPITAL,
                min=0,
                help=(
                    "Starting cash for the position-sizing book. Seeds a fresh "
                    "state/portfolio.json; an existing book keeps its own balance "
                    "across runs."
                ),
                group="Risk & exits",
            ),
            ParamSpec(
                name="risk_per_trade_pct",
                label="Risk per trade (%)",
                type=ParamType.FLOAT,
                required=False,
                default=config.RISK_PER_TRADE_PCT,
                min=0,
                max=100,
                help=(
                    "Fraction of equity risked to the stop on each trade; shares = "
                    "(equity x risk%) / ATR-stop distance. 4% is the validated "
                    "free-lunch sweet spot from the sizing sweep."
                ),
                group="Risk & exits",
            ),
            ParamSpec(
                name="max_positions",
                label="Max open positions",
                type=ParamType.INT,
                required=False,
                default=config.MAX_POSITIONS,
                min=1,
                help="Portfolio cap on concurrent open positions.",
                group="Risk & exits",
            ),
            ParamSpec(
                name="max_position_pct",
                label="Per-name concentration cap (%)",
                type=ParamType.FLOAT,
                required=False,
                default=config.MAX_POSITION_PCT,
                min=0,
                max=100,
                help="Ceiling on any single position as a % of equity.",
                group="Risk & exits",
            ),
            ParamSpec(
                name="atr_stop_multiplier",
                label="ATR stop multiplier",
                type=ParamType.FLOAT,
                required=False,
                default=config.ATR_STOP_MULTIPLIER,
                min=0,
                help=(
                    "Trailing-stop distance = multiplier x ATR(14). 6x was the most "
                    "regime-stable setting in the backtest split-half test."
                ),
                group="Risk & exits",
            ),
            ParamSpec(
                name="disable_profit_target",
                label="Ride the wave (no profit cap)",
                type=ParamType.BOOL,
                required=False,
                default=config.DISABLE_PROFIT_TARGET,
                help=(
                    "On = ignore the PE-rerating target as a hard exit and let "
                    "winners run until the ATR trailing stop or time-stop. The "
                    "+20% cap bound only 11/70 winners in the backtest."
                ),
                group="Risk & exits",
            ),
            ParamSpec(
                name="require_uptrend",
                label="Require intact uptrend",
                type=ParamType.BOOL,
                required=False,
                default=config.REQUIRE_UPTREND,
                help=(
                    "On = only buy when the close is above SMA(20) with a "
                    "non-declining slope. Data-gap-safe: names with no price "
                    "history are never rejected on this filter."
                ),
                group="Risk & exits",
            ),
            ParamSpec(
                name="min_liquidity",
                label="Min 20d median turnover (Rs)",
                type=ParamType.FLOAT,
                required=False,
                default=config.MIN_LIQUIDITY_MEDIAN_20D,
                min=0,
                help=(
                    "Liquidity floor on median 20-day rupee turnover (price x "
                    "volume). Data-gap-safe: unknown turnover never rejects a name."
                ),
                group="Risk & exits",
            ),
            ParamSpec(
                name="model",
                label="Copilot model",
                type=ParamType.STRING,
                required=False,
                default=None,
                help="Optional model id for the discovery LLM run.",
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="dry_run",
                label="Dry run (don't persist)",
                type=ParamType.BOOL,
                required=False,
                default=False,
                help="Compute and report without writing to the ledger or memory.",
                group="Advanced",
                advanced=True,
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
