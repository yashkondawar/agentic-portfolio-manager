"""knowledge/ tree tests: loader validation, 16-cycle catalog, anchor
resolution, enum strictness, yield_gap thresholds, source_status presence."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from knowledge.loader import (  # noqa: E402
    CycleDef,
    KpiDef,
    Knowledge,
    load,
)

MACRO_KPI_IDS = {
    "yield_gap", "evi", "credit_to_gdp_gap", "reer", "india_vix",
    "cpi_yoy", "curve_slope", "breadth_200dma", "gsr", "gold_to_nifty",
    "index_eps_growth", "fii_dii_flows", "mf_retail_inflows", "mcap_gdp",
    "hy_spreads", "dxy",
}


# ---------------------------------------------------------------------------
# Loader validates all seeded files
# ---------------------------------------------------------------------------

def test_loader_validates_all_seeded_files():
    k = load()
    assert isinstance(k, Knowledge)
    # 16 macro KPIs plus the sector micro KPIs, no duplicates (loader
    # raises on duplicate kpi_id, so simple membership is enough here).
    assert MACRO_KPI_IDS.issubset(set(k.kpis)), (
        f"missing macro kpis: {MACRO_KPI_IDS - set(k.kpis)}"
    )
    assert len(k.kpis) > len(MACRO_KPI_IDS)  # micro KPIs loaded too
    # references/ listed (not parsed): all three prose folders present.
    ref_paths = {r.path for r in k.references}
    assert any(p.startswith("methodology/") for p in ref_paths)
    assert any(p.startswith("sectors/") for p in ref_paths)
    assert any(p.startswith("kpi_interpretation/") for p in ref_paths)
    assert all(r.summary for r in k.references)
    assert isinstance(k.version, str) and len(k.version) >= 7


def test_all_eight_sector_micro_files_loaded():
    k = load()
    micro_dir = REPO_ROOT / "knowledge" / "data" / "kpis" / "micro"
    sector_files = [p for p in micro_dir.glob("*.yaml") if not p.name.startswith("_")]
    assert len(sector_files) == 8
    # Every micro KPI carries a registry_xref back to its vocabulary entry.
    micro_kpis = [kpi for kpi in k.kpis.values() if kpi.scope == "sector"]
    assert micro_kpis
    for kpi in micro_kpis:
        assert kpi.registry_xref, f"{kpi.kpi_id} missing registry_xref"
        assert kpi.registry_xref.startswith("kpis/"), kpi.kpi_id


# ---------------------------------------------------------------------------
# Cycle catalog: 16 cycles, anchors resolve
# ---------------------------------------------------------------------------

def test_catalog_has_sixteen_cycles():
    k = load()
    assert len(k.catalog.cycles) == 16
    ids = [c.cycle_id for c in k.catalog.cycles]
    assert len(ids) == len(set(ids)), "duplicate cycle_id"
    assert "valuation_cycle" in ids
    assert "policy_regulatory_cycle" in ids


def test_every_catalog_anchor_kpi_id_resolves():
    k = load()
    for cycle in k.catalog.cycles:
        for anchor in cycle.anchor_kpi_ids:
            assert anchor in k.kpis, (
                f"cycle {cycle.cycle_id} anchors undefined kpi_id {anchor!r}"
            )


def test_kpi_cycle_refs_point_at_real_cycles():
    k = load()
    cycle_ids = {c.cycle_id for c in k.catalog.cycles}
    for kpi in k.kpis.values():
        assert kpi.cycle_refs, f"{kpi.kpi_id} has no cycle_refs"
        for ref in kpi.cycle_refs:
            assert ref in cycle_ids, f"{kpi.kpi_id} refs unknown cycle {ref!r}"


# ---------------------------------------------------------------------------
# Enum strictness
# ---------------------------------------------------------------------------

def _kpi_kwargs(**overrides):
    base = dict(
        kpi_id="dummy",
        scope="macro",
        cycle_refs=["valuation_cycle"],
        formula="x / y",
        inputs=[{"name": "x", "source": "afund.index_data", "status": "available"}],
        orientation="value_type",
        lookback_years=10,
        cadence="daily",
        source_status="available",
    )
    base.update(overrides)
    return base


def test_bad_orientation_enum_rejected():
    with pytest.raises(ValidationError):
        KpiDef(**_kpi_kwargs(orientation="bullish"))  # not a real orientation
    with pytest.raises(ValidationError):
        CycleDef(
            cycle_id="c", name="C", functional_group="external",
            anchor_kpi_ids=[], orientation="value-type",  # dash, not underscore
            lookback_years="10", cadence="daily", leads_lags="n/a",
        )


def test_bad_status_and_scope_rejected():
    with pytest.raises(ValidationError):
        KpiDef(**_kpi_kwargs(source_status="somewhere"))
    with pytest.raises(ValidationError):
        KpiDef(**_kpi_kwargs(scope="galactic"))
    with pytest.raises(ValidationError):
        KpiDef(**_kpi_kwargs(inputs=[{"name": "x", "source": "s", "status": "tbd"}]))


# ---------------------------------------------------------------------------
# yield_gap thresholds + source_status presence
# ---------------------------------------------------------------------------

def test_yield_gap_thresholds_present():
    k = load()
    yg = k.kpis["yield_gap"]
    assert yg.thresholds["deep_value_below"] == pytest.approx(1.40)
    assert yg.thresholds["euphoria_above"] == pytest.approx(1.70)
    assert yg.orientation == "value_type"


def test_every_macro_kpi_has_source_status():
    k = load()
    valid = {"available", "derivable", "manual", "missing"}
    for kpi_id in MACRO_KPI_IDS:
        kpi = k.kpis[kpi_id]
        assert kpi.source_status in valid, kpi_id
        # And every input carries its own status too.
        assert kpi.inputs, kpi_id
        for inp in kpi.inputs:
            assert inp.status in valid, f"{kpi_id}:{inp.name}"
