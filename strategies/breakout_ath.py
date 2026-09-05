"""Registered backtest strategy for the all-time-high breakout sleeve."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from backtesting.breakout_ath.config import AthBreakoutConfig
from backtesting.breakout_ath.service import run_backtest
from core.registry import register
from core.strategy import (
    BaseStrategy,
    ParamSpec,
    ParamType,
    StrategyCategory,
    StrategyResult,
)


def _report(metrics: Dict[str, Any], cfg: AthBreakoutConfig, dossier: Any) -> str:
    lines = [
        f"### ATH breakout — {metrics['start_date']} to {metrics['end_date']}",
        "",
        f"- **CAGR** {metrics['cagr']:.2%} · final value "
        f"₹{metrics['final_value']:,.0f} from ₹{metrics['starting_capital']:,.0f}",
        f"- **Max drawdown** {metrics['max_drawdown']:.2%} · "
        f"Sharpe {metrics['sharpe']:.2f} · Sortino {metrics['sortino']:.2f}",
        f"- **{metrics['round_trips']:,} round trips** · win rate "
        f"{metrics['win_rate']:.1%} · avg hold {metrics['avg_holding_days']:.0f} days",
        f"- Mean positions {metrics['mean_positions_open']:.1f} of "
        f"{cfg.max_positions} · mean cash {metrics['mean_cash_pct']:.1%}",
        "",
    ]
    if cfg.pit_index:
        lines.append(
            f"Universe: point-in-time **{cfg.pit_index}** membership, so delisted "
            "names are included for the days they qualified."
        )
    else:
        lines.append(
            f"Universe: current **{cfg.universe_index}** constituents applied "
            "across all history — this run carries survivorship bias."
        )
    if dossier:
        lines += ["", f"Dossier: `{dossier}`"]
    return "\n".join(lines)


@register
class BreakoutAthBacktestStrategy(BaseStrategy):
    id = "breakout_ath_backtest"
    name = "ATH Breakout Backtest"
    description = (
        "Backtest the trail-only all-time-high breakout sleeve and write a "
        "nine-sheet dossier with tax, drawdown and rolling-return detail."
    )
    long_description = (
        "Runs the same entry and exit functions the daily sleeve uses, so the "
        "backtest cannot drift from live. A stock is bought when it closes "
        "above every close of the prior 252 sessions while still within 15% of "
        "its lifetime closing high; candidates are ranked by 3-month momentum "
        "and fill whatever slots are free, each sized to an equal share of "
        "equity re-struck quarterly. There is no profit target and no time "
        "exit — a position is held until its close falls 16% below the highest "
        "close since entry. Set a point-in-time index to remove survivorship "
        "bias by scanning the constituents as they actually stood on each day."
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
                default=(today - timedelta(days=5 * 365)).isoformat(),
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
                default=100_000.0,
                min=1,
                group="Capital",
            ),
            ParamSpec(
                "pit_index",
                "Point-in-time universe",
                ParamType.ENUM,
                default="Nifty 500",
                choices=["Nifty 500", "none"],
                help=(
                    "'Nifty 500' scans the index as it actually stood each day, "
                    "including names that later delisted. 'none' uses the "
                    "current constituent list and is survivorship biased."
                ),
                group="Universe",
            ),
            ParamSpec(
                "max_positions",
                "Maximum concurrent positions",
                ParamType.INT,
                default=28,
                min=1,
                max=100,
                group="Strategy",
            ),
            ParamSpec(
                "sl_pct",
                "Trailing stop (fraction below peak close)",
                ParamType.FLOAT,
                default=0.16,
                min=0.01,
                max=0.99,
                help="0.16 exits when the close is 16% under the highest close since entry.",
                group="Strategy",
            ),
            ParamSpec(
                "ath_band",
                "Maximum distance below lifetime high",
                ParamType.FLOAT,
                default=0.15,
                min=0.0,
                max=0.99,
                group="Strategy",
            ),
            ParamSpec(
                "lookback",
                "Breakout lookback (sessions)",
                ParamType.INT,
                default=252,
                min=2,
                group="Strategy",
            ),
            ParamSpec(
                "selection_rule",
                "Ranking rule",
                ParamType.ENUM,
                default="mom_3m",
                choices=["mom_3m", "mom_6m", "mom_12m"],
                group="Strategy",
            ),
            ParamSpec(
                "slot_reset_freq",
                "Position-size reset cadence",
                ParamType.ENUM,
                default="Q",
                choices=["Q", "M", "A", "N"],
                group="Strategy",
            ),
            ParamSpec(
                "cost_bps",
                "Round-trip cost (bps per side)",
                ParamType.FLOAT,
                default=25.0,
                min=0.0,
                group="Costs",
            ),
            ParamSpec(
                "download",
                "Refresh prices before running",
                ParamType.BOOL,
                default=False,
                help="Turn off to run against the cached bar store.",
                group="Advanced",
                advanced=True,
            ),
            ParamSpec(
                "write_dossier",
                "Write the Excel dossier",
                ParamType.BOOL,
                default=True,
                group="Advanced",
                advanced=True,
            ),
        ]

    def run(self, params: Dict[str, Any]) -> StrategyResult:
        pit = params.get("pit_index") or "none"
        cfg = AthBreakoutConfig(
            start_date=date.fromisoformat(params["start"]),
            end_date=date.fromisoformat(params["end"]),
            start_capital=float(params["capital"]),
            max_positions=int(params["max_positions"]),
            sl_pct=float(params["sl_pct"]),
            ath_band=float(params["ath_band"]),
            lookback=int(params["lookback"]),
            selection_rule=params["selection_rule"],
            slot_reset_freq=params["slot_reset_freq"],
            cost_bps=float(params["cost_bps"]),
            pit_index=None if pit == "none" else pit,
        )
        output = run_backtest(
            cfg,
            download=bool(params["download"]),
            write_dossier=bool(params["write_dossier"]),
        )
        metrics = output["metrics"]
        dossier = output.get("dossier")
        return StrategyResult(
            strategy_id=self.id,
            status="completed",
            report=_report(metrics, cfg, dossier),
            data={
                "metrics": metrics,
                "results_dir": str(output["results_dir"]),
                "dossier": str(dossier) if dossier else None,
            },
        )
