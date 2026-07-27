"""Kronos gate — separation test strategy.

Answers the *narrow* question the user actually cares about: on the stocks a
strategy already picked (qtr_results / 52-week-high swing), do the trades Kronos
would **keep** win more often than the trades it would **veto**?

This is deliberately cheaper and more decisive than the full portfolio A/B: one
forecast per historical trade, no portfolio simulation. It also fixes the prime
suspect behind the earlier biased forecasts by feeding Kronos **raw (unadjusted)**
candles instead of the strategies' split/dividend-adjusted prices, and defaults to
a short 5-session horizon.

Two trade sources:
  * ``swing``  — runs the mechanical 52-week-high swing screen inline to generate a
                 realistic trade list, then evaluates it (no CSV needed).
  * ``csv``    — evaluates an existing ``trades.csv`` from any backtest
                 (e.g. a qtr_results run).

Kronos is an optional dependency; if it is not installed the strategy returns a
clean ``failed`` result with setup instructions instead of crashing.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)

_MODEL_CHOICES = {
    "Kronos-small (24.7M, faster)": "NeoQuasar/Kronos-small",
    "Kronos-base (102M)": "NeoQuasar/Kronos-base",
}

_CACHE_DIR = Path("data_cache") / "kronos_gate_eval"


@register
class KronosGateEvalStrategy(BaseStrategy):
    id = "kronos_gate_eval"
    name = "Kronos Gate — Separation Test"
    description = (
        "Measure whether a Kronos forecast gate separates winners from losers on "
        "trades an existing strategy already picked — the cheap go/no-go test for "
        "using Kronos to raise win rate."
    )
    long_description = (
        "For every realised trade (from the 52-week-high swing screen or an "
        "imported trades.csv) this computes Kronos' point-in-time opinion as of the "
        "entry date, buckets trades into KEEP vs VETO, and reports the realised "
        "win-rate lift, score quintiles and a rank information coefficient. It "
        "forecasts from RAW (unadjusted) candles over a short horizon to avoid the "
        "calibration bias seen with adjusted prices. Requires the optional Kronos "
        "dependency (torch + model repo)."
    )
    category = StrategyCategory.BACKTEST

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        today = date.today()
        return [
            ParamSpec(
                "source",
                "Trade source",
                ParamType.ENUM,
                default="swing",
                choices=["swing", "csv"],
                help="swing = generate 52-week-high trades inline; csv = import a trades.csv.",
                group="Trades",
            ),
            ParamSpec(
                "trades_csv",
                "trades.csv path (source=csv)",
                ParamType.STRING,
                default="",
                help="Path to a backtest trades.csv with symbol, entry_date, pnl_pct.",
                group="Trades",
            ),
            ParamSpec(
                "start",
                "Start date (source=swing)",
                ParamType.DATE,
                default=(today - timedelta(days=365)).isoformat(),
                group="Trades",
            ),
            ParamSpec(
                "end",
                "End date (source=swing)",
                ParamType.DATE,
                default=today.isoformat(),
                group="Trades",
            ),
            ParamSpec(
                "universe_index",
                "Universe index (source=swing)",
                ParamType.ENUM,
                default="nifty100",
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
                group="Trades",
            ),
            ParamSpec(
                "symbols",
                "Custom universe symbols (source=swing)",
                ParamType.SYMBOLS,
                default=[],
                help="Optional symbols that replace the selected index (faster).",
                group="Trades",
            ),
            ParamSpec(
                "max_positions",
                "Max concurrent positions (source=swing)",
                ParamType.INT,
                default=8,
                min=1,
                group="Trades",
                advanced=True,
            ),
            # ── Kronos knobs ─────────────────────────────────────────────────
            ParamSpec(
                "gate_mode",
                "Gate mode",
                ParamType.ENUM,
                default="rank",
                choices=["rank", "absolute"],
                help="rank = keep top fraction by Kronos score (robust to drift bias); "
                "absolute = keep P(up) above a threshold.",
                group="Kronos",
            ),
            ParamSpec(
                "keep_fraction",
                "Keep fraction (gate_mode=rank)",
                ParamType.FLOAT,
                default=0.5,
                min=0.05,
                max=0.95,
                help="Fraction of picks to KEEP (top by Kronos expected-return rank).",
                group="Kronos",
            ),
            ParamSpec(
                "kronos_model",
                "Kronos model",
                ParamType.ENUM,
                default="Kronos-small (24.7M, faster)",
                choices=list(_MODEL_CHOICES.keys()),
                group="Kronos",
            ),
            ParamSpec(
                "kronos_pred_len",
                "Forecast horizon (sessions)",
                ParamType.INT,
                default=5,
                min=1,
                max=60,
                help="Short horizons are better calibrated; also used as the forward-return label.",
                group="Kronos",
            ),
            ParamSpec(
                "kronos_sample_paths",
                "Sampled paths",
                ParamType.INT,
                default=10,
                min=1,
                max=100,
                help="More paths = steadier P(up) but slower on CPU.",
                group="Kronos",
            ),
            ParamSpec(
                "kronos_min_prob_up",
                "Min P(up) to KEEP",
                ParamType.FLOAT,
                default=0.50,
                min=0.0,
                max=1.0,
                help="Trades with forecast P(up) below this are treated as VETOED.",
                group="Kronos",
            ),
            ParamSpec(
                "kronos_block_avoid",
                "Also VETO explicit AVOID calls",
                ParamType.BOOL,
                default=True,
                group="Kronos",
            ),
            ParamSpec(
                "kronos_lookback",
                "Kronos lookback (sessions)",
                ParamType.INT,
                default=256,
                min=30,
                max=512,
                group="Kronos",
                advanced=True,
            ),
            ParamSpec(
                "use_cache",
                "Reuse downloaded prices",
                ParamType.BOOL,
                default=True,
                group="Advanced",
                advanced=True,
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        from kronos.gate_eval import (
            load_trades_csv,
            records_from_dicts,
            run_gate_eval,
        )
        from kronos.predictor import KronosUnavailable

        source = params.get("source", "swing")

        # 1) Assemble the trade list.
        try:
            if source == "csv":
                path = str(params.get("trades_csv") or "").strip()
                if not path or not Path(path).exists():
                    return StrategyResult(
                        self.id,
                        "failed",
                        report=(
                            "## Missing trades.csv\n\n"
                            "`source=csv` needs a valid `trades_csv` path pointing at a "
                            "backtest trades.csv (columns: symbol, entry_date, pnl_pct)."
                        ),
                        error="missing_trades_csv",
                    )
                trades = load_trades_csv(path)
                title = Path(path).parent.name or "imported"
            else:
                trade_dicts = self._generate_swing_trades(params)
                trades = records_from_dicts(trade_dicts)
                title = "52-week-high swing"
        except Exception as exc:  # noqa: BLE001
            return StrategyResult(
                self.id, "failed",
                report=f"## Could not build trade list\n\n```\n{exc}\n```",
                error="trade_source_failed",
            )

        if not trades:
            return StrategyResult(
                self.id,
                "failed",
                report=(
                    "## No trades to evaluate\n\n"
                    "The selected source produced zero closed trades over this window. "
                    "Widen the window/universe (source=swing) or check the CSV."
                ),
                error="no_trades",
            )

        # 2) Run the separation test.
        model = _MODEL_CHOICES.get(params["kronos_model"], "NeoQuasar/Kronos-small")
        try:
            rep = run_gate_eval(
                trades,
                cache_dir=_CACHE_DIR,
                model=model,
                pred_len=int(params["kronos_pred_len"]),
                sample_paths=int(params["kronos_sample_paths"]),
                lookback=int(params["kronos_lookback"]),
                min_prob_up=float(params["kronos_min_prob_up"]),
                block_avoid=bool(params["kronos_block_avoid"]),
                gate_mode=params.get("gate_mode", "rank"),
                keep_fraction=float(params["keep_fraction"]),
                use_cache=bool(params["use_cache"]),
                title=title,
            )
        except KronosUnavailable as exc:
            return StrategyResult(
                self.id,
                "failed",
                report=(
                    "## Kronos is not installed\n\n"
                    "This separation test needs the Kronos model (optional dependency).\n\n"
                    f"```\n{exc}\n```"
                ),
                error="kronos_unavailable",
            )

        markdown = rep.pop("markdown", "")
        return StrategyResult(self.id, "completed", report=markdown, data=rep)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _generate_swing_trades(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Run the mechanical swing (52-week-high) backtest once and return its
        closed trades as dicts — no Kronos gate, just the strategy's own picks."""
        from backtesting.swing_trading.config import BacktestConfig
        from backtesting.swing_trading.service import run_backtest

        cfg = BacktestConfig(
            start_date=date.fromisoformat(params["start"]),
            end_date=date.fromisoformat(params["end"]),
            universe_index=params["universe_index"],
            max_positions=int(params["max_positions"]),
            use_cache=bool(params["use_cache"]),
            use_kronos_gate=False,
        )
        result = run_backtest(
            cfg,
            symbols=params.get("symbols") or None,
            write_outputs=False,
        )
        return result.get("trades", [])
