"""Pydantic-validated loader for the knowledge/ deep-definitions tree.

knowledge/ is the middle tier of the three-tier knowledge contract (see
knowledge/README.md): registry/ (compact agent vocabulary) -> knowledge/data/
(this loader — deep, machine-readable KPI definitions and the cycle
catalog) -> knowledge/references/ (prose methodology/interpretation guides,
listed only, never parsed).

Mirrors registry/registry.py's pattern deliberately: a `.load()` classmethod,
pydantic validation, a `.version` computed the same way (git short SHA, or a
content-hash fallback).

Usage:
    from knowledge.loader import Knowledge, load
    k = load()
    k.kpis["yield_gap"].source_status
    k.catalog.cycles[0].cycle_id
    k.version
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

KNOWLEDGE_ROOT = Path(__file__).resolve().parent

_ORIENTATIONS = {"value_type", "fear_type", "goldilocks_type"}
_STATUSES = {"available", "derivable", "manual", "missing"}
_SCOPES = {"macro", "sector", "market_structure"}


# ---------------------------------------------------------------------------
# KPI models (knowledge/data/kpis/*.yaml, knowledge/data/kpis/micro/*.yaml)
# ---------------------------------------------------------------------------

class InputRef(BaseModel):
    name: str
    source: str
    status: str

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in _STATUSES:
            raise ValueError(f"status must be one of {_STATUSES}, got {v!r}")
        return v


class KpiDef(BaseModel):
    kpi_id: str
    scope: str
    cycle_refs: list[str] = Field(default_factory=list)
    formula: str
    inputs: list[InputRef]
    orientation: str
    lookback_years: float
    cadence: str
    source_status: str
    registry_xref: Optional[str] = None
    references_xref: list[str] = Field(default_factory=list)
    # Optional named threshold bands inherited from the strategy framework
    # (e.g. yield_gap: deep_value_below=1.40, euphoria_above=1.70). ALL
    # DRAFT until back-tested — see CLAUDE.md hard rules.
    thresholds: dict[str, float] = Field(default_factory=dict)

    @field_validator("scope")
    @classmethod
    def _valid_scope(cls, v: str) -> str:
        if v not in _SCOPES:
            raise ValueError(f"scope must be one of {_SCOPES}, got {v!r}")
        return v

    @field_validator("orientation")
    @classmethod
    def _valid_orientation(cls, v: str) -> str:
        if v not in _ORIENTATIONS:
            raise ValueError(f"orientation must be one of {_ORIENTATIONS}, got {v!r}")
        return v

    @field_validator("source_status")
    @classmethod
    def _valid_source_status(cls, v: str) -> str:
        if v not in _STATUSES:
            raise ValueError(f"source_status must be one of {_STATUSES}, got {v!r}")
        return v


class MicroKpiFile(BaseModel):
    """One knowledge/data/kpis/micro/<sector>.yaml file: a small set of
    KpiDefs for one registry sector, plus a pointer back to the registry
    vocabulary file it's deepening."""
    sector: str
    registry_ref: str
    kpis: list[KpiDef]


# ---------------------------------------------------------------------------
# Cycle catalog models (knowledge/data/cycles/catalog.yaml)
# ---------------------------------------------------------------------------

_FUNCTIONAL_GROUPS = {"macro_regime", "market_structure", "external", "idiosyncratic"}


class CycleDef(BaseModel):
    cycle_id: str
    name: str
    functional_group: str
    anchor_kpi_ids: list[str] = Field(default_factory=list)
    orientation: str
    orientation_note: Optional[str] = None
    lookback_years: str
    cadence: str
    leads_lags: str

    @field_validator("functional_group")
    @classmethod
    def _valid_group(cls, v: str) -> str:
        if v not in _FUNCTIONAL_GROUPS:
            raise ValueError(f"functional_group must be one of {_FUNCTIONAL_GROUPS}, got {v!r}")
        return v

    @field_validator("orientation")
    @classmethod
    def _valid_orientation(cls, v: str) -> str:
        if v not in _ORIENTATIONS:
            raise ValueError(f"orientation must be one of {_ORIENTATIONS}, got {v!r}")
        return v


class CycleCatalog(BaseModel):
    version: int
    cycles: list[CycleDef]

    def get(self, cycle_id: str) -> CycleDef:
        for c in self.cycles:
            if c.cycle_id == cycle_id:
                return c
        raise KeyError(cycle_id)


# ---------------------------------------------------------------------------
# References (listed only, never parsed as structured data)
# ---------------------------------------------------------------------------

class ReferenceDoc(BaseModel):
    """A pointer into knowledge/references/ — path + a one-line summary
    (the file's first non-blank, non-heading-marker line), for cheap
    inclusion in an agent context packet. The full prose is only read by an
    agent that decides it needs it (see knowledge/README.md)."""
    path: str  # relative to knowledge/references/
    summary: str


# ---------------------------------------------------------------------------
# Knowledge
# ---------------------------------------------------------------------------

class Knowledge(BaseModel):
    kpis: dict[str, KpiDef]
    catalog: CycleCatalog
    references: list[ReferenceDoc]
    version: str

    @classmethod
    def load(cls, root: Path | None = None) -> "Knowledge":
        knowledge_root = root or KNOWLEDGE_ROOT

        kpis: dict[str, KpiDef] = {}

        # Macro KPIs: knowledge/data/kpis/*.yaml (flat files, skip _*.yaml).
        for path in sorted((knowledge_root / "data" / "kpis").glob("*.yaml")):
            if path.name.startswith("_"):
                continue  # skip _schema.yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            kpi = KpiDef(**data)
            if kpi.kpi_id in kpis:
                raise ValueError(f"duplicate kpi_id {kpi.kpi_id!r} in {path}")
            kpis[kpi.kpi_id] = kpi

        # Micro/sector KPIs: knowledge/data/kpis/micro/*.yaml (one file per
        # sector, each containing a list of KpiDefs).
        for path in sorted((knowledge_root / "data" / "kpis" / "micro").glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            micro_file = MicroKpiFile(**data)
            for kpi in micro_file.kpis:
                if kpi.kpi_id in kpis:
                    raise ValueError(f"duplicate kpi_id {kpi.kpi_id!r} in {path}")
                kpis[kpi.kpi_id] = kpi

        # Cycle catalog.
        catalog_path = knowledge_root / "data" / "cycles" / "catalog.yaml"
        catalog_data = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        catalog = CycleCatalog(**catalog_data)

        # Cross-check: every anchor_kpi_id must resolve to a defined kpi_id.
        for cycle in catalog.cycles:
            for anchor_id in cycle.anchor_kpi_ids:
                if anchor_id not in kpis:
                    raise ValueError(
                        f"cycle {cycle.cycle_id!r} anchor_kpi_ids references "
                        f"undefined kpi_id {anchor_id!r}"
                    )

        # References: listed only (path + first-line summary), never parsed.
        references: list[ReferenceDoc] = []
        references_root = knowledge_root / "references"
        for path in sorted(references_root.rglob("*.md")):
            rel_path = path.relative_to(references_root).as_posix()
            summary = ""
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip().lstrip("#").strip()
                if stripped:
                    summary = stripped
                    break
            references.append(ReferenceDoc(path=rel_path, summary=summary))

        version = cls._compute_version(knowledge_root)

        return cls(kpis=kpis, catalog=catalog, references=references, version=version)

    @staticmethod
    def _compute_version(knowledge_root: Path) -> str:
        """Git short SHA if available (and knowledge/ is inside a git repo),
        else sha256 of the concatenated knowledge YAML/MD files, first 12
        chars. Same pattern as registry.Registry._compute_version."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short=12", "HEAD"],
                cwd=str(knowledge_root),
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
            p for p in knowledge_root.rglob("*")
            if p.is_file() and p.suffix in (".yaml", ".yml", ".md") and p.name != "loader.py"
        )
        for path in file_paths:
            hasher.update(path.read_bytes())
        return hasher.hexdigest()[:12]


def load(root: Path | None = None) -> Knowledge:
    """Convenience wrapper: knowledge.loader.load() == Knowledge.load()."""
    return Knowledge.load(root)


if __name__ == "__main__":
    k = load()
    print(f"Knowledge version: {k.version}")
    print(f"KPIs: {len(k.kpis)} -> {sorted(k.kpis.keys())}")
    print(f"Cycles: {len(k.catalog.cycles)} -> {[c.cycle_id for c in k.catalog.cycles]}")
    print(f"References: {len(k.references)}")
