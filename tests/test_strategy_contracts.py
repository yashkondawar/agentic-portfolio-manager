from datetime import date

import pytest

from core import registry
from core.strategy import BaseStrategy, ParamSpec, ParamType, StrategyResult


class ContractStrategy(BaseStrategy):
    id = "contract"
    name = "Contract"

    @classmethod
    def param_specs(cls):
        return [
            ParamSpec("count", "Count", ParamType.INT, required=True, min=1, max=5),
            ParamSpec(
                "mode",
                "Mode",
                ParamType.ENUM,
                default="safe",
                choices=["safe", "fast"],
            ),
            ParamSpec("day", "Day", ParamType.DATE, default="2026-01-01"),
        ]

    def run(self, params):
        return StrategyResult(self.id, "completed", data=params)


def test_parameter_coercion_and_validation():
    strategy = ContractStrategy()
    params = strategy.coerce_params(
        {"count": "3", "mode": "fast", "day": date(2026, 7, 22)}
    )
    assert params == {"count": 3, "mode": "fast", "day": "2026-07-22"}

    with pytest.raises(ValueError, match="at least"):
        strategy.coerce_params({"count": 0})
    with pytest.raises(ValueError, match="at most"):
        strategy.coerce_params({"count": 6})
    with pytest.raises(ValueError, match="one of"):
        strategy.coerce_params({"count": 1, "mode": "unsafe"})


def test_registry_exposes_every_workbench_strategy():
    strategy_ids = {spec["id"] for spec in registry.list_specs()}
    assert strategy_ids == {
        "sequential_agents",
        "parallel_agents",
        "swing_trading",
        "portfolio_analysis",
        "watchlist_curation",
        "qtr_results",
        "swing_backtest",
        "kronos_forecast",
        "kronos_swing_ab",
        "kronos_gate_eval",
    }
