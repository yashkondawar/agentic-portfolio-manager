"""Kronos gate A/B strategy — does Kronos confirmation improve the swing edge?

Runs the point-in-time swing backtest twice on the same data/window — baseline
vs. Kronos-gated — and reports whether the gate lifts hit-rate and risk-adjusted
return. This is **Phase 1** of the Kronos rollout: prove the overlay adds value
before trusting it live or loosening any existing filters.

Kronos is an optional dependency; if it is not installed the strategy returns a
clean ``failed`` result with setup instructions instead of crashing.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from backtesting.swing_trading.config import BacktestConfig
from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)

_MODEL_CHOICES = {
    "Kronos-base (102M)": "NeoQuasar/Kronos-base",
    "Kronos-small (24.7M, faster)": "NeoQuasar/Kronos-small",
}


@register
class KronosSwingABStrategy(BaseStrategy):
    id = "kronos_swing_ab"
    name = "Kronos Gate A/B (Swing)"
    description = (
        "Backtest the swing playbook with vs. without a Kronos confirmation gate "
        "and compare hit-rate, return, and drawdown to see if the gate adds edge."
    )
    long_description = (
        "Phase-1 validation of using Kronos as a confirmation filter on the "
        "existing mechanical swing screen. Runs an identical point-in-time "
        "backtest twice over shared data — baseline and Kronos-gated — with "
        "next-session fills and trading costs, then reports the deltas and a "
        "verdict. Requires the optional Kronos dependency (torch + model repo)."
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
                "universe_index",
                "Universe index",
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
                group="Universe",
            ),
            ParamSpec(
                "symbols",
                "Custom universe symbols",
                ParamType.SYMBOLS,
                default=[],
                help="Optional symbols that replace the selected index (faster A/B).",
                group="Universe",
            ),
            ParamSpec(
                "max_positions",
                "Maximum concurrent positions",
                ParamType.INT,
                default=8,
                min=1,
                group="Portfolio rules",
            ),
            # ── Kronos gate knobs ─────────────────────────────────────────────
            ParamSpec(
                "kronos_model",
                "Kronos model",
                ParamType.ENUM,
                default="Kronos-base (102M)",
                choices=list(_MODEL_CHOICES.keys()),
                group="Kronos gate",
            ),
            ParamSpec(
                "kronos_pred_len",
                "Forecast horizon (sessions)",
                ParamType.INT,
                default=10,
                min=1,
                max=120,
                group="Kronos gate",
            ),
            ParamSpec(
                "kronos_sample_paths",
                "Sampled paths",
                ParamType.INT,
                default=10,
                min=1,
                max=100,
                help="More paths = better P(up) estimate but slower backtest.",
                group="Kronos gate",
            ),
            ParamSpec(
                "kronos_min_prob_up",
                "Min P(up) to allow entry",
                ParamType.FLOAT,
                default=0.55,
                min=0.0,
                max=1.0,
                help="Veto candidates whose forecast P(up) is below this.",
                group="Kronos gate",
            ),
            ParamSpec(
                "kronos_block_avoid",
                "Veto explicit AVOID calls",
                ParamType.BOOL,
                default=True,
                group="Kronos gate",
            ),
            ParamSpec(
                "kronos_lookback",
                "Kronos lookback (sessions)",
                ParamType.INT,
                default=256,
                min=30,
                max=512,
                group="Kronos gate",
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
        from backtesting.swing_trading.kronos_ab import run_kronos_ab

        model = _MODEL_CHOICES.get(params["kronos_model"], "NeoQuasar/Kronos-base")
        cfg = BacktestConfig(
            starting_capital=float(params["capital"]),
            start_date=date.fromisoformat(params["start"]),
            end_date=date.fromisoformat(params["end"]),
            universe_index=params["universe_index"],
            max_positions=int(params["max_positions"]),
            commission_pct=float(params["commission_pct"]),
            use_cache=bool(params["use_cache"]),
            kronos_model=model,
            kronos_pred_len=int(params["kronos_pred_len"]),
            kronos_sample_paths=int(params["kronos_sample_paths"]),
            kronos_min_prob_up=float(params["kronos_min_prob_up"]),
            kronos_block_avoid=bool(params["kronos_block_avoid"]),
            kronos_lookback=int(params["kronos_lookback"]),
        )

        try:
            output = run_kronos_ab(cfg, symbols=params.get("symbols") or [])
        except Exception as exc:  # noqa: BLE001
            from kronos.predictor import KronosUnavailable

            if isinstance(exc, KronosUnavailable):
                return StrategyResult(
                    self.id,
                    "failed",
                    report=(
                        "## Kronos is not installed\n\n"
                        "This A/B strategy needs the Kronos model (optional dependency).\n\n"
                        f"```\n{exc}\n```"
                    ),
                    error="kronos_unavailable",
                )
            raise

        return StrategyResult(
            self.id,
            "completed",
            report=output["summary"],
            data={key: value for key, value in output.items() if key != "summary"},
        )
