"""Offline idempotency test for scripts/gen_sector_packs.py.

scripts/ isn't an importable package under src/, so this test imports the
module directly by file path (mirroring how run.py resolves pipeline
classes elsewhere in this codebase) rather than adding scripts/ to
sys.path wholesale.

This test only asserts the *generation* is idempotent against what's
currently committed on disk (research/equity_researcher/prompts/sector_packs/)
-- it does not write anything itself (--check-equivalent: renders in-memory
and diffs, never touches the filesystem).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "gen_sector_packs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("gen_sector_packs", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen_sector_packs():
    return _load_module()


def test_sectors_discovers_every_registry_kpi_file(gen_sector_packs):
    sectors = gen_sector_packs.sectors()
    assert "it_technology" in sectors
    assert "bfsi" in sectors
    assert "generic" in sectors
    registry_files = {p.stem for p in (REPO_ROOT / "registry" / "kpis").glob("*.yaml")}
    assert set(sectors) == registry_files


def test_render_pack_matches_committed_output_for_every_sector(gen_sector_packs):
    # The core idempotency guarantee: re-rendering from the current
    # registry/knowledge sources reproduces exactly what's on disk. If this
    # fails, either the sources changed without re-running the generator, or
    # someone hand-edited a generated pack -- both are regressions.
    stale = []
    for sector in gen_sector_packs.sectors():
        rendered = gen_sector_packs.render_pack(sector)
        out_path = gen_sector_packs.SECTOR_PACKS_DIR / f"{sector}.md"
        on_disk = out_path.read_text(encoding="utf-8") if out_path.exists() else None
        if on_disk != rendered:
            stale.append(sector)
    assert stale == [], f"sector packs out of date (re-run scripts/gen_sector_packs.py): {stale}"


def test_render_pack_is_byte_for_byte_deterministic(gen_sector_packs):
    # Rendering the same sector twice must produce identical output -- no
    # nondeterministic ordering (e.g. dict iteration) leaking into the pack.
    first = gen_sector_packs.render_pack("it_technology")
    second = gen_sector_packs.render_pack("it_technology")
    assert first == second


def test_generated_header_present_in_every_pack(gen_sector_packs):
    for sector in gen_sector_packs.sectors():
        rendered = gen_sector_packs.render_pack(sector)
        assert rendered.startswith(gen_sector_packs.GENERATED_HEADER)


def test_kpi_floor_names_the_registry_without_restating_it(gen_sector_packs):
    # The pack points at registry/kpis/<sector>.yaml and states how wide the governed
    # vocabulary is; it must NOT carry a KPI table. A table here duplicates the tier-2
    # playbook's and fails E10 in research/equity_researcher/tools/validate_sector_registry.py
    # -- that duplication is exactly what this generator was rewritten to remove.
    rendered = gen_sector_packs.render_pack("it_technology")
    assert "| Category | KPIs |" not in rendered
    assert "registry/kpis/it_technology.yaml" in rendered
    count, categories = gen_sector_packs._kpi_floor(
        gen_sector_packs._load_registry_kpis("it_technology")
    )
    assert f"{count} KPIs across {len(categories)} categories" in rendered
    for label in categories:
        assert label in rendered


def test_pack_is_a_tier1_router(gen_sector_packs):
    # Every pack must declare the two-tier contract and route to its children, since
    # prompts/03 makes the playbook supersede the pack wherever they differ.
    for sector in gen_sector_packs.sectors():
        rendered = gen_sector_packs.render_pack(sector)
        assert "*(tier 1 — routing family)*" in rendered
        assert "This pack routes; it does not analyse." in rendered
        assert "## Child playbooks — select exactly one at triage (T2)" in rendered


def test_child_routing_table_matches_the_er_registry(gen_sector_packs):
    # The routing table is read live off research/equity_researcher/config/sector_registry.yaml,
    # which is the source of truth for which playbooks exist. Every child of the family
    # must appear; nothing else may.
    registry = gen_sector_packs.er_registry()
    if not registry:
        pytest.skip("ER subsystem not synced (config/sector_registry.yaml absent)")
    for sector in gen_sector_packs.sectors():
        rendered = gen_sector_packs.render_pack(sector)
        expected = {slug for slug, p in (registry.get("playbooks") or {}).items()
                    if p.get("family") == sector}
        for slug in expected:
            assert f"| `{slug}` |" in rendered, f"{sector} pack omits child {slug}"
        for slug, p in (registry.get("playbooks") or {}).items():
            if p.get("family") != sector:
                assert f"| `{slug}` |" not in rendered, f"{sector} pack claims foreign child {slug}"


def test_kpi_coverage_reports_gaps_rather_than_hiding_them(gen_sector_packs):
    # Uncovered signature KPIs are reported, never silently dropped -- but they don't
    # fail the build: the 32 ER playbooks are deliberately finer-grained than the fund's
    # 8-sector vocabulary. This asserts the reporting mechanism works, not that the gap
    # count is any particular number.
    if not gen_sector_packs.er_registry():
        pytest.skip("ER subsystem not synced (config/sector_registry.yaml absent)")
    gaps = gen_sector_packs.kpi_coverage("pharma_chemicals")
    assert isinstance(gaps, dict)
    for slug, missing in gaps.items():
        assert missing, f"{slug} listed as a gap with nothing missing"
    # stem matching must not be so loose that everything "covers" everything
    assert gen_sector_packs._stems("revenue_per_employee_usd") == {"revenue", "employee"}
