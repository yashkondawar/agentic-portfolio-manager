"""Pydantic-validated loader for the registry/ rulebook.

The Registry is the governed knowledge store described in the architecture
blueprint (Section 3.2): the single source of truth for KPI vocabularies,
strategy definitions, and mandate-level risk rules. Nothing downstream is
meant to hardcode this content — it should always be read through this
loader.

Usage:
    from registry.registry import Registry
    reg = Registry.load()
    reg.kpis["bfsi"].quantitative_kpis
    reg.strategies["cycle_contrarian"].status
    reg.rules.max_single_position_pct
    reg.version
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

REGISTRY_ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# KPI models
# ---------------------------------------------------------------------------

class KpiEntry(BaseModel):
    name: str
    unit: str
    category: str


class SectorKpiSet(BaseModel):
    sector: str
    description: str
    quantitative_kpis: list[KpiEntry] = Field(default_factory=list)
    qualitative_checks: list[dict] = Field(default_factory=list)
    cycle_overlap_checks: list[dict] = Field(default_factory=list)
    niche_pointers: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Strategy models
# ---------------------------------------------------------------------------

class EligibleUniverse(BaseModel):
    asset_classes: list[str] = Field(default_factory=list)
    market_cap_bands: list[str] = Field(default_factory=list)
    sectors_include: list[str] = Field(default_factory=list)
    sectors_exclude: list[str] = Field(default_factory=list)


class Strategy(BaseModel):
    strategy_id: str
    name: str
    objective: str
    philosophy: str
    eligible_universe: EligibleUniverse
    required_kpi_sets: list[str] = Field(default_factory=list)
    entry_criteria: list[str] = Field(default_factory=list)
    exit_criteria: list[str] = Field(default_factory=list)
    invalidation_template: str
    position_sizing_rule: Optional[str] = None
    capital_ceiling_pct: Optional[float] = None
    review_cadence: Optional[str] = None
    status: str = "DRAFT"


# ---------------------------------------------------------------------------
# Risk rules model
# ---------------------------------------------------------------------------

class RiskRule(BaseModel):
    value: object
    status: str
    note: Optional[str] = None


class PhaseMultipliers(BaseModel):
    """Phase 10 — cycle-aware position-size multipliers, applied to
    max_single_position_pct by portfolio.risk.cycle_adjusted_limit(). Keys
    are cycle_framework.yaml phase_id values (see registry/strategies/
    cycle_framework.yaml phases:). DRAFT until back-tested, like every other
    threshold in this file."""
    value: dict[str, float]
    status: str
    note: Optional[str] = None


class RiskLimits(BaseModel):
    max_single_position_pct: RiskRule
    max_sector_pct: RiskRule
    max_single_mf_etf_pct: RiskRule
    cash_floor_pct: RiskRule
    cash_ceiling_pct: RiskRule
    long_only: RiskRule
    escalation: RiskRule
    phase_multipliers: PhaseMultipliers


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class Registry(BaseModel):
    kpis: dict[str, SectorKpiSet]
    strategies: dict[str, Strategy]
    rules: RiskLimits
    version: str

    @classmethod
    def load(cls, root: Path | None = None) -> "Registry":
        registry_root = root or REGISTRY_ROOT

        kpis: dict[str, SectorKpiSet] = {}
        for path in sorted((registry_root / "kpis").glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            kpi_set = SectorKpiSet(**data)
            kpis[kpi_set.sector] = kpi_set

        strategies: dict[str, Strategy] = {}
        for path in sorted((registry_root / "strategies").glob("*.yaml")):
            if path.name.startswith("_"):
                continue  # skip _template.yaml and similar
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            # Escape hatch for non-Strategy-shaped files sharing this directory
            # (e.g. cycle_framework.yaml — the Phase 7 cycle engine's own
            # constitution-as-config, validated by its own loader in
            # src/afund/cycles/framework.py, not this strict Strategy model).
            # Such files self-declare `kind: <something other than "strategy">`
            # at the top level; anything without that marker is assumed to be
            # a plain Strategy and validated as before (unconditionally, so a
            # genuine Strategy file with a schema mistake still fails loudly).
            if isinstance(data, dict) and data.get("kind") and data.get("kind") != "strategy":
                continue
            strategy = Strategy(**data)
            strategies[strategy.strategy_id] = strategy

        rules_path = registry_root / "rules" / "risk_limits.yaml"
        rules_data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
        rules = RiskLimits(**rules_data)

        version = cls._compute_version(registry_root)

        return cls(kpis=kpis, strategies=strategies, rules=rules, version=version)

    @staticmethod
    def _compute_version(registry_root: Path) -> str:
        """Git short SHA if available (and registry is inside a git repo),
        else sha256 of the concatenated registry YAML/MD files, first 12 chars.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short=12", "HEAD"],
                cwd=str(registry_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass

        hasher = hashlib.sha256()
        file_paths = sorted(
            p for p in registry_root.rglob("*")
            if p.is_file() and p.suffix in (".yaml", ".yml", ".md") and p.name != "registry.py"
        )
        for path in file_paths:
            hasher.update(path.read_bytes())
        return hasher.hexdigest()[:12]


if __name__ == "__main__":
    reg = Registry.load()
    print(f"Registry version: {reg.version}")
    print(f"KPI sector sets: {len(reg.kpis)} -> {sorted(reg.kpis.keys())}")
    print(f"Strategies: {len(reg.strategies)} -> {sorted(reg.strategies.keys())}")
