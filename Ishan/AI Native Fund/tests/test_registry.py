"""Registry-level tests: loading, KPI coverage, strategy completeness, version."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from registry.registry import Registry  # noqa: E402


def test_registry_loads():
    reg = Registry.load()
    assert reg is not None


def test_at_least_eight_kpi_sector_sets():
    reg = Registry.load()
    assert len(reg.kpis) >= 8


def test_bfsi_contains_nim_and_gnpa():
    reg = Registry.load()
    assert "bfsi" in reg.kpis
    kpi_names = {kpi.name for kpi in reg.kpis["bfsi"].quantitative_kpis}
    assert "nim" in kpi_names
    assert "gnpa" in kpi_names


def test_every_strategy_has_invalidation_template():
    reg = Registry.load()
    assert len(reg.strategies) >= 1
    for strategy_id, strategy in reg.strategies.items():
        assert strategy.invalidation_template, f"{strategy_id} missing invalidation_template"


def test_version_string_non_empty():
    reg = Registry.load()
    assert isinstance(reg.version, str)
    assert len(reg.version) > 0


def test_expected_sector_files_present():
    reg = Registry.load()
    expected = {
        "bfsi",
        "consumer_retail",
        "commodities_energy",
        "it_technology",
        "pharma_chemicals",
        "auto_engineering",
        "infra_capital_goods",
        "generic",
    }
    assert expected.issubset(set(reg.kpis.keys()))
