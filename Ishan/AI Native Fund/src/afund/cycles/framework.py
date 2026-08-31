"""Pydantic-validated loader for registry/strategies/cycle_framework.yaml —
the Universal Cycle-Positioning Framework's constitution-as-config.

Mirrors registry/registry.py and knowledge/loader.py's pattern: a `.load()`
classmethod, pydantic validation, a `.version` computed the same way (git
short SHA, or a content-hash fallback).

This module reads the YAML directly by path rather than through
Registry.load() because cycle_framework.yaml deliberately does NOT validate
against registry.Strategy (see the `kind: cycle_framework` discriminator
that makes Registry.load() skip it). This is the framework's own loader.

Usage:
    from afund.cycles.framework import CycleFramework, load
    fw = load()
    fw.phases["euphoria"].percentile_band
    fw.group_weights_by_cluster["Recovery"]["market_structure"]
    fw.version
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FRAMEWORK_PATH = REPO_ROOT / "registry" / "strategies" / "cycle_framework.yaml"


# ---------------------------------------------------------------------------
# phases
# ---------------------------------------------------------------------------

class PercentileBand(BaseModel):
    min: float
    max: float


class Phase(BaseModel):
    phase_id: str
    name: str
    position_on_wave: str
    percentile_band: PercentileBand
    direction_rule: str
    default_posture: str
    narrative_markers: list[str] = Field(default_factory=list)
    illustrative_quantitative_trigger: Optional[str] = None
    directional_lean: int


class GapResolution(BaseModel):
    band: PercentileBand
    note: str


class ClassificationRules(BaseModel):
    nearest_band_tiebreak_max_distance: float
    gap_resolutions: list[GapResolution] = Field(default_factory=list)
    direction_compatibility: dict[str, list[str]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# orientations
# ---------------------------------------------------------------------------

class ValueTypeOrientation(BaseModel):
    description: str
    value_type: str


class FearTypeOrientation(BaseModel):
    description: str
    fear_type_invert: str


class GoldilocksBand(BaseModel):
    min: float
    max: float


class GoldilocksTypeOrientation(BaseModel):
    description: str
    goldilocks_band: dict[str, GoldilocksBand] = Field(default_factory=dict)


class Orientations(BaseModel):
    value_type: ValueTypeOrientation
    fear_type: FearTypeOrientation
    goldilocks_type: GoldilocksTypeOrientation


# ---------------------------------------------------------------------------
# direction
# ---------------------------------------------------------------------------

class MomentumOfMomentum(BaseModel):
    description: str
    states: list[str]
    stable_threshold_pct: float


class Direction(BaseModel):
    windows_months: list[int]
    flat_threshold_pct: float
    momentum_of_momentum: MomentumOfMomentum


# ---------------------------------------------------------------------------
# parabolic_rule
# ---------------------------------------------------------------------------

class ParabolicRule(BaseModel):
    description: str
    window_months: int
    compression_factor: str
    min_abs_return_pct: float
    action: str


# ---------------------------------------------------------------------------
# evi
# ---------------------------------------------------------------------------

class Evi(BaseModel):
    components: list[str]
    weights: dict[str, float]
    compute_only_when_all_available: bool
    partial_evi_disclosure: str


# ---------------------------------------------------------------------------
# functional_groups / regime_clusters / group_weights_by_cluster
# ---------------------------------------------------------------------------

class FunctionalGroup(BaseModel):
    name: str
    cycles: list[str]
    question: str


class ClusterWeights(BaseModel):
    macro_regime: float
    market_structure: float
    external: float
    why: str


class RegimeClassificationRules(BaseModel):
    description: str
    unknown_when_data_pending: bool
    phase_to_cluster_map: dict[str, str] = Field(default_factory=dict)
    resolution: str


# ---------------------------------------------------------------------------
# alignment
# ---------------------------------------------------------------------------

class Alignment(BaseModel):
    directional_lean_map: dict[str, list[str]]
    alignment_score_definition: str


# ---------------------------------------------------------------------------
# allocation_bands
# ---------------------------------------------------------------------------

class YieldGapThresholds(BaseModel):
    deep_value_below: float
    euphoria_above: float


class AllocationRange(BaseModel):
    min: float
    max: float


class AllocationBand(BaseModel):
    composite_reading: str
    regime_label: str
    equity_pct: AllocationRange
    debt_pct: AllocationRange
    gold_reits_pct: AllocationRange
    cash_pct: AllocationRange
    note: Optional[str] = None


class AllocationBands(BaseModel):
    yield_gap_thresholds: YieldGapThresholds
    bands: list[AllocationBand]


# ---------------------------------------------------------------------------
# reconciliation
# ---------------------------------------------------------------------------

class NarrativeBucketBand(BaseModel):
    min: float
    max: float


class ReconciliationQuadrant(BaseModel):
    quant_phase_bucket: str
    narrative_bucket: str
    interpretation: str
    outcome: str
    flags: dict[str, bool] = Field(default_factory=dict)


class Reconciliation(BaseModel):
    narrative_bucket_bands: dict[str, NarrativeBucketBand]
    quadrants: list[ReconciliationQuadrant]


# ---------------------------------------------------------------------------
# governance
# ---------------------------------------------------------------------------

class ChecklistItem(BaseModel):
    item: str
    type: str  # "mechanical" | "judgment"


class Sizing(BaseModel):
    formula: str
    capped_by: str


class Governance(BaseModel):
    checklist: list[ChecklistItem]
    premortem_trigger: str
    hitl_triggers: list[str]
    sizing: Sizing


# ---------------------------------------------------------------------------
# CycleFramework (top level)
# ---------------------------------------------------------------------------

class CycleFramework(BaseModel):
    kind: str
    framework_id: str
    version: int
    status: str
    source_doc: str

    phases: list[Phase]
    classification_rules: ClassificationRules
    orientations: Orientations
    direction: Direction
    parabolic_rule: ParabolicRule
    evi: Evi
    functional_groups: dict[str, FunctionalGroup]
    regime_clusters: list[str]
    group_weights_by_cluster: dict[str, ClusterWeights]
    regime_classification_rules: RegimeClassificationRules
    alignment: Alignment
    allocation_bands: AllocationBands
    reconciliation: Reconciliation
    governance: Governance

    content_version: str = ""  # git-SHA-or-hash stamp, set by load()

    def phase_map(self) -> dict[str, Phase]:
        return {p.phase_id: p for p in self.phases}

    def phase_order(self) -> list[str]:
        """Phases in wheel order, as declared in the YAML."""
        return [p.phase_id for p in self.phases]

    @classmethod
    def load(cls, path: Path | None = None) -> "CycleFramework":
        framework_path = path or DEFAULT_FRAMEWORK_PATH
        data = yaml.safe_load(framework_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("kind") != "cycle_framework":
            raise ValueError(
                f"{framework_path} is not a cycle_framework file "
                f"(expected top-level kind: cycle_framework)"
            )
        fw = cls(**data)
        fw.content_version = cls._compute_version(framework_path)
        return fw

    @staticmethod
    def _compute_version(framework_path: Path) -> str:
        """Git short SHA if available (repo-wide, since this is one file
        inside a larger repo), else sha256 of the file's own bytes, first 12
        chars. Same pattern as registry.Registry._compute_version /
        knowledge.loader.Knowledge._compute_version."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short=12", "HEAD"],
                cwd=str(framework_path.parent),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        hasher = hashlib.sha256()
        hasher.update(framework_path.read_bytes())
        return hasher.hexdigest()[:12]


def load(path: Path | None = None) -> CycleFramework:
    """Convenience wrapper: cycles.framework.load() == CycleFramework.load()."""
    return CycleFramework.load(path)


if __name__ == "__main__":
    fw = load()
    print(f"Framework version: {fw.version} (content {fw.content_version})")
    print(f"Status: {fw.status}")
    print(f"Phases: {fw.phase_order()}")
    print(f"Regime clusters: {fw.regime_clusters}")
