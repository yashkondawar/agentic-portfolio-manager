"""S18 registry/UI tests isolate the DB-owned service without external inputs."""

import ast
import json
import os
import sys
from datetime import date
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from core import registry, storage
from core.strategy import ParamType, StrategyCategory
from strategies.s18 import (
    COMBOS,
    METAL_MODES,
    S18BacktestStrategy,
    S18DailyStrategy,
    S18ReplayStrategy,
)


@pytest.fixture
def service(monkeypatch):
    module = ModuleType("backtesting.s18.service")
    output = {
        "report": "Paper model report",
        "metrics": {"sharpe": 1.0},
        "validation": {"passed": True},
        "holdings": [],
        "orders": [],
        "fills": [{"fill_id": "A-1", "actual_charges": None}],
        "trades": [],
        "equity_curve": [],
        "portfolio_state": {"tranches": {"A": {}, "B": {}}},
        "artifact_group_id": "example-group",
        "warnings": ["Slippage untested"],
    }
    for name in ("run_backtest", "run_replay", "run_daily"):
        setattr(module, name, Mock(return_value=output))
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.delenv("S18_KIT_PATH", raising=False)
    monkeypatch.delenv("S18_FORWARD_PATH", raising=False)
    return module


def test_s18_catalog_fixed_choices_and_safety():
    specs = {spec["id"]: spec for spec in registry.list_specs()}
    assert {"s18_daily", "s18_backtest", "s18_replay"} <= specs.keys()
    assert S18BacktestStrategy.category == StrategyCategory.BACKTEST
    assert S18ReplayStrategy.category == StrategyCategory.BACKTEST
    for cls in (S18BacktestStrategy, S18DailyStrategy):
        params = {spec.name: spec for spec in cls.param_specs()}
        assert params["combo"].choices == list(COMBOS)
        assert params["combo"].default == "P15"
        assert params["metal_mode"].choices == list(METAL_MODES)
        assert params["metal_mode"].default == "both_priority"
        assert params["capital"].default == 100_000.0
        assert (
            not {
                "tranche",
                "tranche_weight",
                "place_orders",
                "confirm_fills",
                "bypass_validation",
                "seed_reference",
            }
            & params.keys()
        )
    daily = {spec.name: spec for spec in S18DailyStrategy.param_specs()}
    assert daily["as_of"].tracks_today
    assert daily["as_of"].default == date.today().isoformat()
    assert daily["persist"].default is True
    assert daily["shadow_charges"].type == ParamType.JSON
    assert daily["shadow_charges"].default == {}
    assert daily["shadow_charges"].advanced is True
    assert S18ReplayStrategy.param_specs() == []
    for strategy_id in ("s18_backtest", "s18_daily", "s18_replay"):
        names = {spec["name"] for spec in specs[strategy_id]["params"]}
        assert not {"kit_path", "forward_path", "data_source"} & names


def test_service_imports_are_lazy():
    source = Path("strategies") / "s18.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        assert not (
            isinstance(node, ast.ImportFrom)
            and str(node.module).startswith("backtesting.s18")
        )
        if isinstance(node, ast.Import):
            assert all(
                not name.name.startswith("backtesting.s18") for name in node.names
            )


def test_backtest_wrapper_preserves_envelope_without_paths(service):
    result = registry.run_strategy("s18_backtest", {})
    assert result.ok
    service.run_backtest.assert_called_once_with(
        combo="P15",
        metal_mode="both_priority",
        start="2014-01-01",
        end="2026-08-31",
        capital=100_000.0,
        write_dossier=True,
    )
    assert result.report == "Paper model report"
    assert "report" not in result.data
    assert result.data["portfolio_state"] == {"tranches": {"A": {}, "B": {}}}
    assert result.data["artifact_group_id"] == "example-group"
    assert service.run_backtest.return_value["report"] == "Paper model report"


@pytest.mark.parametrize("combo", COMBOS)
@pytest.mark.parametrize("metal_mode", METAL_MODES)
def test_each_fixed_book_passes_to_service(service, combo, metal_mode):
    result = registry.run_strategy(
        "s18_backtest",
        {
            "combo": combo,
            "metal_mode": metal_mode,
            "capital": "250000",
            "write_dossier": "false",
        },
    )
    assert result.ok
    kwargs = service.run_backtest.call_args.kwargs
    assert kwargs["combo"] == combo
    assert kwargs["metal_mode"] == metal_mode
    assert kwargs["capital"] == 250_000.0
    assert kwargs["write_dossier"] is False


def test_daily_dry_run_without_paths_preserves_book_identity(service):
    result = registry.run_strategy(
        "s18_daily",
        {
            "book_id": "experiment",
            "as_of": date(2026, 9, 15),
            "persist": "false",
        },
    )
    assert result.ok
    service.run_daily.assert_called_once_with(
        combo="P15",
        metal_mode="both_priority",
        as_of="2026-09-15",
        capital=100_000.0,
        book_id="experiment",
        persist=False,
        shadow_charges={},
    )


@pytest.mark.parametrize(
    ("strategy_cls", "method"),
    [
        (S18BacktestStrategy, "run_backtest"),
        (S18DailyStrategy, "run_daily"),
        (S18ReplayStrategy, "run_replay"),
    ],
)
def test_obsolete_paths_and_environment_are_never_used(
    service, monkeypatch, strategy_cls, method
):
    legacy_env = {"S18_KIT_PATH", "S18_FORWARD_PATH"}
    for key in legacy_env:
        monkeypatch.setenv(key, "unavailable-experiment-folder")
    environ_getitem = type(os.environ).__getitem__

    def reject_legacy_lookup(environ, key):
        assert key not in legacy_env, f"Obsolete S18 environment lookup: {key}"
        return environ_getitem(environ, key)

    monkeypatch.setattr(type(os.environ), "__getitem__", reject_legacy_lookup)
    assert not {"kit_path", "forward_path", "data_source"} & {
        spec.name for spec in strategy_cls.param_specs()
    }
    result = registry.run_strategy(
        strategy_cls.id,
        {
            "kit_path": "unavailable-reference-folder",
            "forward_path": "unavailable-forward-folder",
            "data_source": "csv",
        },
    )
    assert result.ok
    runner = getattr(service, method)
    runner.assert_called_once()
    assert runner.call_args.args == ()
    assert (
        not {"kit_path", "forward_path", "data_source"} & runner.call_args.kwargs.keys()
    )
    if method == "run_replay":
        runner.assert_called_once_with()


def test_daily_passes_shadow_charges_without_rewriting_model_state(service):
    charges = {
        "A-1": {
            "stt": 1.5,
            "stamp_duty": 0.25,
            "exchange_fees": 0.2,
            "gst": 0.1,
            "dp_charges": 0,
            "brokerage": 0,
            "other": 0,
        }
    }
    state = {"cash": 10_000, "basis": 90_000, "nav": 101_000}
    service.run_daily.return_value["portfolio_state"] = state.copy()
    result = registry.run_strategy("s18_daily", {"shadow_charges": json.dumps(charges)})
    assert result.ok
    assert service.run_daily.call_args.kwargs["shadow_charges"] == charges
    assert result.data["portfolio_state"] == state
    assert result.data["fills"] == [{"fill_id": "A-1", "actual_charges": None}]


def test_invalid_shadow_charge_json_fails_before_service(service):
    result = registry.run_strategy("s18_daily", {"shadow_charges": "{invalid"})
    assert not result.ok
    service.run_daily.assert_not_called()


@pytest.mark.parametrize(
    "charges",
    [
        [],
        {"A-1": []},
        {"A-1": {"stt": -1}},
        {"A-1": {"stt": True}},
        {"A-1": {"stt": "1"}},
        {"A-1": {"stt": float("nan")}},
        {"A-1": {"stt": float("inf")}},
        {"A-1": {"unknown": 1}},
    ],
)
def test_invalid_shadow_charge_breakdowns_fail_before_service(service, charges):
    result = registry.run_strategy("s18_daily", {"shadow_charges": charges})
    assert not result.ok
    service.run_daily.assert_not_called()


def test_replay_without_arguments_propagates_certificate_failure(service):
    service.run_replay.side_effect = ValueError("Golden mismatch: dates differ")
    result = registry.run_strategy("s18_replay", {})
    assert not result.ok
    assert "Golden mismatch" in result.error
    service.run_replay.assert_called_once_with()


def test_daily_has_no_certificate_bypass(service):
    service.run_daily.side_effect = ValueError("Current golden certificate required")
    result = registry.run_strategy("s18_daily", {"bypass_validation": True})
    assert not result.ok
    assert "golden certificate required" in result.error
    assert "bypass_validation" not in service.run_daily.call_args.kwargs


@pytest.mark.parametrize(
    "params", [{"combo": "P25"}, {"metal_mode": "gold"}, {"capital": 0}]
)
def test_invalid_parameters_fail_before_service(service, params):
    assert not registry.run_strategy("s18_backtest", params).ok
    service.run_backtest.assert_not_called()


def test_discover_contains_separate_s18_portfolio_tab(service):
    app = AppTest.from_string(
        "from ui.state import initialize_state\n"
        "from ui.pages import discover_page\n"
        "initialize_state()\n"
        "discover_page()\n"
    ).run(timeout=120)
    assert not app.exception
    assert "S18 Portfolio" in [tab.label for tab in app.tabs]
    assert app.selectbox(key="discover_s18_combo").value == "P15"
    assert app.selectbox(key="discover_s18_metal_mode").options == list(METAL_MODES)
    assert app.checkbox(key="discover_s18_persist").value is True
    keys = {item.key for item in app.text_input} | {item.key for item in app.selectbox}
    assert (
        not {
            "discover_s18_kit_path",
            "discover_s18_forward_path",
            "discover_s18_data_source",
        }
        & keys
    )
    service.run_daily.assert_not_called()


def test_backtest_lab_contains_backtest_and_golden_replay(service):
    app = AppTest.from_string(
        "from ui.state import initialize_state\n"
        "from ui.pages import backtest_page\n"
        "initialize_state()\n"
        "backtest_page()\n"
    ).run(timeout=120)
    assert not app.exception
    selector = next(item for item in app.selectbox if item.label == "Strategy")
    assert "S18 Backtest" in selector.options
    assert "S18 Golden Replay" in selector.options
    selector.select("s18_backtest").run(timeout=120)
    assert not app.exception
    assert app.selectbox(key="backtest_s18_backtest_combo").value == "P15"
    service.run_backtest.assert_not_called()


def test_settings_catalog_automatically_includes_s18():
    app = AppTest.from_string(
        "from ui.state import initialize_state\n"
        "from ui.pages import settings_page\n"
        "initialize_state()\n"
        "settings_page()\n"
    ).run(timeout=120)
    assert not app.exception
    labels = [item.label for item in app.expander]
    assert "S18 Daily · swing" in labels
    assert "S18 Backtest · backtest" in labels
    assert "S18 Golden Replay · backtest" in labels


def test_s18_renderer_is_read_only_and_downloads_stored_dossier():
    group, artifacts = storage.save_artifacts(
        "s18-test",
        "UI fixture",
        {"custom_dossier.xlsx": b"fixture-dossier"},
        content_types={
            "custom_dossier.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        },
    )
    payload = {
        "metrics": {"nav": 101_000.0, "sharpe": 1.0},
        "validation": {"passed": True, "cases": [{"combo": "P15", "passed": True}]},
        "holdings": [
            {"symbol": "ACME", "tranche": "A", "armed": True, "stop": 90.0},
            {"symbol": "OTHER", "tranche": "B", "armed": False, "stop": 95.0},
        ],
        "orders": [{"symbol": "NEW", "action": "BUY", "tranche": "B"}],
        "fills": [
            {
                "fill_id": "A-1",
                "symbol": "ACME",
                "actual_charges": 1.5,
                "charge_breakdown": {"stt": 1.5},
            }
        ],
        "trades": [{"symbol": "OLD", "reason": "floor", "tranche": "A"}],
        "equity_curve": [{"date": "2026-09-01", "equity": 101_000.0}],
        "portfolio_state": {"tranches": {"A": {"cash": 50000}, "B": {"cash": 50000}}},
        "artifact_group_id": group,
        "artifacts": artifacts,
        "warnings": ["Slippage untested"],
    }
    app = AppTest.from_string(
        "from core.strategy import StrategyResult\n"
        "from ui.components import render_result\n"
        f"render_result(StrategyResult('s18_daily', 'completed', 'Model report', data={payload!r}))\n"
    ).run(timeout=120)
    assert not app.exception
    assert not app.get("plotly_chart")
    diagnostics = next(
        item for item in app.expander if item.label == "Diagnostics and assumptions"
    )
    assert not diagnostics.proto.expanded
    assert not app.get("data_editor")
    labels = [item.proto.label for item in app.get("download_button")]
    assert "Download stored custom_dossier.xlsx" in labels
    assert "Download portfolio state JSON" in labels
    assert "Download orders CSV" in labels
    assert "Download fills CSV" in labels
    tables = [item.value for item in app.dataframe]
    assert any(
        "Symbol" in table and list(table["Symbol"]) == ["ACME"] for table in tables
    )
    assert any(
        "Fill ID" in table and list(table["Fill ID"]) == ["A-1"] for table in tables
    )
    assert not app.button


def test_armed_display_does_not_treat_false_string_as_armed():
    from ui.components import _s18_tables

    tables = _s18_tables(
        {
            "holdings": [
                {"symbol": "A", "armed": "false"},
                {"symbol": "B", "armed": "yes"},
            ],
        }
    )
    assert tables["Armed names and stops"] == [{"symbol": "B", "armed": "yes"}]
