"""Kronos forecast strategy — foundation-model price signals for NSE symbols.

Wraps the :mod:`kronos` service behind the common :class:`BaseStrategy`
contract so it shows up in the CLI / UI alongside every other system. It turns
Kronos candlestick forecasts into per-symbol BUY / HOLD / AVOID calls with a
suggested stop and target derived from the forecast volatility cone.

Kronos itself is an **optional** dependency (torch + the cloned model repo). If
it is not installed the strategy returns a clean ``failed`` result carrying
setup instructions rather than crashing the registry.
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

_MODEL_CHOICES = {
    "Kronos-small (24.7M, CPU-friendly)": "NeoQuasar/Kronos-small",
    "Kronos-base (102M)": "NeoQuasar/Kronos-base",
    "Kronos-mini (4.1M, 2k context)": "NeoQuasar/Kronos-mini",
}
_MINI_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-2k"
_BASE_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"


@register
class KronosForecastStrategy(BaseStrategy):
    id = "kronos_forecast"
    name = "Kronos Price Forecast"
    description = (
        "Use the Kronos OHLCV foundation model to forecast future candles and "
        "derive BUY/HOLD/AVOID calls with stop & target for each symbol."
    )
    long_description = (
        "Samples multiple stochastic forecast paths from Kronos for each symbol, "
        "then converts the forecast distribution into a directional signal "
        "(probability of upside, expected return) and a volatility-cone-based "
        "stop/target. Runs zero-shot on CPU; treats the forecast distribution — "
        "not the exact predicted price — as the signal. Decision-support only."
    )
    category = StrategyCategory.SWING

    @classmethod
    def param_specs(cls) -> List[ParamSpec]:
        return [
            ParamSpec(
                "symbols",
                "Symbols",
                ParamType.SYMBOLS,
                required=True,
                help="NSE tickers, e.g. RELIANCE, TCS, INFY.",
                group="Basic",
            ),
            ParamSpec(
                "model",
                "Kronos model",
                ParamType.ENUM,
                default="Kronos-small (24.7M, CPU-friendly)",
                choices=list(_MODEL_CHOICES.keys()),
                group="Basic",
            ),
            ParamSpec(
                "pred_len",
                "Forecast horizon (sessions)",
                ParamType.INT,
                default=10,
                min=1,
                max=120,
                help="How many future daily bars to forecast (your swing horizon).",
                group="Forecast",
            ),
            ParamSpec(
                "lookback",
                "Lookback (sessions)",
                ParamType.INT,
                default=400,
                min=30,
                max=512,
                help="History fed to the model. Kept <= the 512 context limit.",
                group="Forecast",
            ),
            ParamSpec(
                "sample_paths",
                "Sampled paths",
                ParamType.INT,
                default=20,
                min=1,
                max=100,
                help="More paths = better probability estimates but more CPU time.",
                group="Forecast",
            ),
            ParamSpec(
                "device",
                "Device",
                ParamType.ENUM,
                default="cpu",
                choices=["cpu", "cuda"],
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                "temperature",
                "Sampling temperature (T)",
                ParamType.FLOAT,
                default=1.0,
                min=0.1,
                max=2.0,
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                "top_p",
                "Nucleus sampling (top_p)",
                ParamType.FLOAT,
                default=0.9,
                min=0.1,
                max=1.0,
                group="Advanced",
                advanced=True,
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        # Imported here so a missing torch/Kronos install never breaks registry
        # import — only running this strategy surfaces the requirement.
        from kronos.config import KronosConfig
        from kronos.predictor import KronosUnavailable
        from kronos.service import forecast_symbols
        from kronos.signals import signals_to_frame

        symbols = params.get("symbols") or []
        if not symbols:
            return StrategyResult(
                self.id, "failed", report="No symbols provided.", error="no symbols"
            )

        model = _MODEL_CHOICES.get(params["model"], "NeoQuasar/Kronos-small")
        tokenizer = _MINI_TOKENIZER if model.endswith("Kronos-mini") else _BASE_TOKENIZER
        cfg = KronosConfig(
            model=model,
            tokenizer=tokenizer,
            device=params.get("device", "cpu"),
            lookback=int(params["lookback"]),
            pred_len=int(params["pred_len"]),
            sample_paths=int(params["sample_paths"]),
            temperature=float(params["temperature"]),
            top_p=float(params["top_p"]),
        )

        try:
            results = forecast_symbols(list(symbols), config=cfg)
        except KronosUnavailable as exc:
            return StrategyResult(
                self.id,
                "failed",
                report=(
                    "## Kronos is not installed\n\n"
                    "This strategy needs the Kronos model (optional dependency).\n\n"
                    f"```\n{exc}\n```"
                ),
                error="kronos_unavailable",
            )

        signals = [r.signal for r in results if r.ok and r.signal is not None]
        errors = {r.symbol: r.error for r in results if not r.ok}

        report = self._build_report(cfg, signals, errors)
        table = signals_to_frame(signals)
        return StrategyResult(
            self.id,
            "completed",
            report=report,
            data={
                "signals": [s.to_dict() for s in signals],
                "table": table.to_dict(orient="records") if not table.empty else [],
                "errors": errors,
                "config": {
                    "model": cfg.model,
                    "pred_len": cfg.pred_len,
                    "lookback": cfg.clamped_lookback(),
                    "sample_paths": cfg.sample_paths,
                    "device": cfg.device,
                },
            },
        )

    @staticmethod
    def _build_report(cfg, signals, errors) -> str:
        lines: List[str] = []
        lines.append("# 🔮 Kronos Price Forecast")
        lines.append("")
        lines.append(
            f"Model `{cfg.model}` · horizon **{cfg.pred_len}** sessions · "
            f"lookback **{cfg.clamped_lookback()}** · **{cfg.sample_paths}** sampled "
            f"paths · device `{cfg.device}`"
        )
        lines.append("")
        lines.append(
            "> Decision-support only. Signal = forecast *distribution/direction*, "
            "not the exact predicted price. Validate in the backtest before trading."
        )
        lines.append("")

        if not signals:
            lines.append("_No forecasts produced._")
        else:
            lines.append(
                "| Symbol | Call | Conf | P(up) | Exp.Ret | Entry | Stop | Target | R:R |"
            )
            lines.append("|---|---|---|---|---|---|---|---|---|")
            order = {"BUY": 0, "HOLD": 1, "AVOID": 2}
            for s in sorted(
                signals, key=lambda x: (order.get(x.direction, 3), -x.prob_up)
            ):
                lines.append(
                    f"| {s.symbol} | {s.direction} | {s.confidence} | "
                    f"{s.prob_up:.0%} | {s.expected_return:+.1%} | "
                    f"{s.last_close:,.2f} | {s.suggested_stop:,.2f} | "
                    f"{s.suggested_target:,.2f} | {s.reward_risk:.1f} |"
                )
            lines.append("")
            for s in sorted(signals, key=lambda x: (order.get(x.direction, 3), -x.prob_up)):
                lines.append(f"- **{s.symbol}** — {s.rationale}")

        if errors:
            lines.append("")
            lines.append("### Skipped")
            for sym, err in errors.items():
                lines.append(f"- {sym}: {err}")
        return "\n".join(lines)
