"""GFS (Grandfather / Father / Son) multi-timeframe RSI strategy — live runner.

Wraps the ``gfs`` engine, which is the ``backtesting/gfs`` research harness
resumed against a persisted book rather than re-implemented. Every default below
is the value the research adopted; ``backtesting/gfs/EXPLORATIONS.md`` records
what each one beat and why.
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
from gfs.config import LIVE_DEFAULTS, REGIME_MODES


@register
class GFSLiveStrategy(BaseStrategy):
    id = "gfs_live"
    name = "GFS Multi-Timeframe (live)"
    description = (
        "Buy short-term weakness inside long-term strength: monthly and weekly RSI "
        "above 60, daily RSI dipping to 43, gated by market breadth and sector "
        "relative strength, exited on daily RSI or a 3.5x-ATR stop."
    )
    long_description = (
        "Grandfather (monthly RSI), Father (weekly RSI) and Son (daily RSI) must "
        "disagree: the two higher timeframes confirm an uptrend while the daily "
        "pulls back, on the premise that the higher timeframes drag the daily back "
        "up. The top-down funnel from the original method is enforced mechanically "
        "— a market-breadth regime gate first, then a sector relative-strength gate "
        "(top 5 sectors), then the stock condition, then a headroom filter that "
        "refuses dips with no room left before the resistance the exit targets.\n\n"
        "The live runner is the backtest engine resumed: it loads the saved book "
        "(cash, positions and the pending order queues), replays every trading "
        "session since the last run using the same daily loop, and reports the "
        "orders to place at the next open. A signal seen at today's close is never "
        "filled at today's close — that timing is what the backtested numbers were "
        "produced under.\n\n"
        "Expect low exposure (roughly 40-60% deployed) and long flat stretches. "
        "That is the strategy working as designed, not a bug; see gfs/USAGE.md."
    )
    category = StrategyCategory.SWING

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        d = LIVE_DEFAULTS
        return [
            # ── Book ─────────────────────────────────────────────────────────
            ParamSpec(
                name="starting_capital",
                label="Starting capital (Rs)",
                type=ParamType.FLOAT,
                default=d["starting_capital"],
                help=(
                    "Used once, when the book is first created. Changing it later "
                    "does not re-capitalise an existing book."
                ),
                min=10_000.0,
                group="Book",
            ),
            ParamSpec(
                name="bootstrap_from",
                label="Backfill the book from",
                type=ParamType.DATE,
                default=None,
                help=(
                    "Only used when no book exists yet. Replays the strategy from "
                    "this date so the live book starts with a track record and any "
                    "positions it would already be holding. Leave blank to start "
                    "flat from today."
                ),
                group="Book",
            ),
            ParamSpec(
                name="universe_index",
                label="Universe",
                type=ParamType.STRING,
                default=d["universe_index"],
                help=(
                    "Comma-separated NSE index keys. nifty500 is the only universe "
                    "the research validated — nse_all has no industry labels, which "
                    "silently disables the sector gate and the per-sector cap."
                ),
                group="Book",
            ),
            # ── Entry ────────────────────────────────────────────────────────
            ParamSpec(
                name="g_rsi_min",
                label="Grandfather: monthly RSI at least",
                type=ParamType.FLOAT,
                default=d["g_rsi_min"],
                min=40.0,
                max=90.0,
                group="Entry",
            ),
            ParamSpec(
                name="f_rsi_min",
                label="Father: weekly RSI at least",
                type=ParamType.FLOAT,
                default=d["f_rsi_min"],
                min=40.0,
                max=90.0,
                group="Entry",
            ),
            ParamSpec(
                name="s_rsi_entry",
                label="Son: daily RSI at most",
                type=ParamType.FLOAT,
                default=d["s_rsi_entry"],
                help=(
                    "43, not the taught 40: the threshold is arbitrary and 43 buys "
                    "meaningfully more signals without degrading the edge."
                ),
                min=25.0,
                max=55.0,
                group="Entry",
            ),
            ParamSpec(
                name="min_headroom_pct",
                label="Minimum headroom to resistance (%)",
                type=ParamType.FLOAT,
                default=d["min_headroom_pct"],
                help=(
                    "Refuse a dip that has less than this much room before the "
                    "resistance the exit targets. The only entry filter that "
                    "survived an out-of-sample test. 0 disables it."
                ),
                min=0.0,
                max=40.0,
                group="Entry",
            ),
            # ── Exits ────────────────────────────────────────────────────────
            ParamSpec(
                name="exit_rsi",
                label="Exit when daily RSI reaches",
                type=ParamType.FLOAT,
                default=d["exit_rsi"],
                help=(
                    "70 beat 60 by ~3pp CAGR over 13.6 years and nearly doubled the "
                    "payoff ratio, but held twice as long and lost YTD 2026. The "
                    "research could not settle it; 68-72 is defensible."
                ),
                min=55.0,
                max=85.0,
                group="Exits",
            ),
            ParamSpec(
                name="shadow_exit_rsi",
                label="Shadow exit threshold (reported only)",
                type=ParamType.FLOAT,
                default=d["shadow_exit_rsi"],
                help=(
                    "Never traded. Each run flags which open positions the "
                    "alternative threshold would already be exiting, so the "
                    "unsettled question stays visible. 0 disables the report."
                ),
                min=0.0,
                max=85.0,
                group="Exits",
            ),
            ParamSpec(
                name="atr_stop_mult",
                label="Stop distance (x ATR)",
                type=ParamType.FLOAT,
                default=d["atr_stop_mult"],
                help=(
                    "3.5x ATR, not the taught fixed 3-5%: a percentage stop that "
                    "tight sits inside normal noise and liquidated roughly half the "
                    "eventual winners. The plateau runs 3.0-4.5."
                ),
                min=1.0,
                max=8.0,
                group="Exits",
            ),
            # ── Gates ────────────────────────────────────────────────────────
            ParamSpec(
                name="regime_mode",
                label="Market regime gate",
                type=ParamType.ENUM,
                default=d["regime_mode"],
                choices=list(REGIME_MODES),
                help=(
                    "breadth = trade only when enough of the universe is above its "
                    "200-DMA. breadth+sma additionally requires the index itself "
                    "above its 200-DMA — costs signals and added nothing breadth "
                    "had not already said."
                ),
                group="Gates",
            ),
            ParamSpec(
                name="min_breadth_pct",
                label="Minimum breadth (%)",
                type=ParamType.FLOAT,
                default=d["min_breadth_pct"],
                help="Share of the universe above its 200-DMA. 0 disables the gate.",
                min=0.0,
                max=90.0,
                group="Gates",
            ),
            ParamSpec(
                name="sector_top_n",
                label="Trade only the strongest N sectors",
                type=ParamType.INT,
                default=d["sector_top_n"],
                min=1,
                max=20,
                group="Gates",
            ),
            ParamSpec(
                name="max_per_sector",
                label="Max open positions per sector",
                type=ParamType.INT,
                default=d["max_per_sector"],
                help="0 removes the cap. Unlabelled sectors are never capped.",
                min=0,
                max=8,
                group="Gates",
            ),
            # ── Sizing ───────────────────────────────────────────────────────
            ParamSpec(
                name="max_positions",
                label="Max open positions",
                type=ParamType.INT,
                default=d["max_positions"],
                help=(
                    "4, not 8. Concentration is where the payoff comes from; "
                    "spreading the same capital over 8 names diluted the winners."
                ),
                min=1,
                max=20,
                group="Sizing",
            ),
            ParamSpec(
                name="max_position_pct",
                label="Max per position (% of equity)",
                type=ParamType.FLOAT,
                default=d["max_position_pct"],
                min=5.0,
                max=100.0,
                group="Sizing",
            ),
            ParamSpec(
                name="cash_yield_pct",
                label="Idle cash yield (% p.a.)",
                type=ParamType.FLOAT,
                default=d["cash_yield_pct"],
                help=(
                    "This book is only ~40-60% deployed. Assuming the idle balance "
                    "earns nothing is a silent penalty the always-invested "
                    "benchmark never pays; a liquid fund is the realistic case."
                ),
                min=0.0,
                max=15.0,
                group="Sizing",
            ),
            # ── Advanced ─────────────────────────────────────────────────────
            ParamSpec(
                name="commission_pct",
                label="Commission per side (%)",
                type=ParamType.FLOAT,
                default=d["commission_pct"],
                min=0.0,
                max=1.0,
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="slippage_bps",
                label="Slippage per side (bps)",
                type=ParamType.FLOAT,
                default=d["slippage_bps"],
                min=0.0,
                max=200.0,
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="as_of",
                label="Run as of date",
                type=ParamType.DATE,
                default=None,
                help="Pretend today is this date. Leave blank for today.",
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="dry_run",
                label="Dry run (don't persist)",
                type=ParamType.BOOL,
                default=False,
                help="Compute and report without writing the book.",
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                name="reset_book",
                label="Reset the book first (destructive)",
                type=ParamType.BOOL,
                default=False,
                help=(
                    "Deletes the saved cash, positions and tradebook before "
                    "running. There is no undo."
                ),
                group="Advanced",
                advanced=True,
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        from gfs import engine

        out = engine.run(params)
        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=out["report"],
            data=out["data"],
        )
