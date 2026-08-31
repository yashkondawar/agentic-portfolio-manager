"""Generate the ER tier-1 sector packs from the fund's governed sources (one-way).

Usage:
    .venv\\Scripts\\python scripts\\gen_sector_packs.py [--check]

For every ``registry/kpis/<sector>.yaml`` this writes
``research/equity_researcher/prompts/sector_packs/<sector>.md`` by combining:

- ``research/equity_researcher/config/sector_registry.yaml`` -> family display name,
  the child-playbook routing table, and the interpretation frame
- ``knowledge/references/sectors/<sector>.md``               -> prose sections
  (Core truth, Qualitative lenses, Preferred sources, Extraction note)
- ``registry/kpis/<sector>.yaml``                            -> the governed KPI floor,
  named by category, plus the coverage check below

## Why the shape changed (2026-08-11)

The packs used to carry a full ``| Category | KPIs |`` table lifted out of
``registry/kpis/``. ER v2.1 turned sector routing into a **two-tier contract**: tier-1
packs route, tier-2 playbooks (``prompts/sector_playbooks/``, 32 of them) analyse. Its
validator enforces that split mechanically — ``tools/validate_sector_registry.py`` E10
fails the build when a pack and one of its child playbooks both carry KPI content in a
table. The old fat packs tripped E10 for all 32 playbooks.

Both rules are right, and they are about different things:

- ``CLAUDE.md``: ``registry/`` is the governed source of truth for KPI vocabulary and must
  never be hardcoded downstream.
- ER v2.1: a KPI table in a tier-1 pack is a second, drifting copy of the playbook's.

So the registry stays authoritative, but it is enforced as a **check rather than a copy**.
A generated markdown table *is* the hardcoding CLAUDE.md warns about; ``--check``'s
coverage report is the governed relationship, read live off the registry each run. The
pack now names the registry file, the KPI count and the categories — a pointer, which is
also what the token-frugality rule asks for — and the per-KPI detail lives in exactly one
place, the tier-2 playbook.

``--check`` renders in-memory and exits non-zero if any pack on disk would differ. It also
prints the **registry coverage report**: for every child playbook, which of its
``signature_kpis`` are matched by a KPI in ``registry/kpis/<family>.yaml``. Uncovered KPIs
are *reported, never silently dropped* — but they do not fail the check, because the ER
playbooks are deliberately finer-grained than the fund's 8-sector vocabulary (a playbook
may legitimately need ``arpob`` where the fund registry has no hospital sector). The report
is how a real vocabulary gap gets noticed instead of quietly persisting.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_KPI_DIR = REPO_ROOT / "registry" / "kpis"
KNOWLEDGE_SECTOR_DIR = REPO_ROOT / "knowledge" / "references" / "sectors"
ER_ROOT = REPO_ROOT / "research" / "equity_researcher"
SECTOR_PACKS_DIR = ER_ROOT / "prompts" / "sector_packs"
ER_SECTOR_REGISTRY = ER_ROOT / "config" / "sector_registry.yaml"

GENERATED_HEADER = (
    "<!-- GENERATED from registry/kpis + knowledge/references + "
    "research/equity_researcher/config/sector_registry.yaml — edit sources, "
    "then re-run scripts/gen_sector_packs.py -->"
)

# Human-friendly sector display names (title of the pack). The ER registry's `display`
# wins when the family exists there; this is the fallback for a sector the ER registry
# does not carry, and it keeps the generator working if the ER subsystem is absent.
SECTOR_TITLES: dict[str, str] = {
    "bfsi": "BFSI (Banks, NBFCs, HFCs, MFIs, Insurers, capital-market infra)",
    "it_technology": "IT & Technology (services, ER&D, SaaS, new-age/platforms)",
    "pharma_chemicals": "Pharma & Chemicals",
    "auto_engineering": "Auto & Engineering (OEMs, ancillaries, defense manufacturing, industrials)",
    "consumer_retail": "Consumer & Retail",
    "commodities_energy": "Commodities & Energy",
    "infra_capital_goods": "Infra & Capital Goods",
    "generic": "Generic (fallback for unclassified / conglomerate / niche sectors)",
}

TIER1_NOTE = (
    "*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in "
    "`prompts/sector_playbooks/` carries the KPI table, the valuation convention, the "
    "divergence cases, the exhibit set and the forensic screens. Per `prompts/03`, **the "
    "playbook supersedes this pack wherever the two differ.** Shared research rules: "
    "`prompts/31`. Routing source of truth: `config/sector_registry.yaml`.*"
)


def _category_label(category: str) -> str:
    """Turn a registry ``category`` slug into a human label."""
    return category.replace("_", " ").title()


def _load_registry_kpis(sector: str) -> dict:
    path = REGISTRY_KPI_DIR / f"{sector}.yaml"
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


_ER_REGISTRY_CACHE: dict | None = None


def er_registry() -> dict:
    """The ER subsystem's two-tier routing registry. Absent when the subsystem has not
    been synced; the generator degrades to a family-only pack rather than failing."""
    global _ER_REGISTRY_CACHE
    if _ER_REGISTRY_CACHE is None:
        if ER_SECTOR_REGISTRY.exists():
            with ER_SECTOR_REGISTRY.open("r", encoding="utf-8") as fh:
                _ER_REGISTRY_CACHE = yaml.safe_load(fh) or {}
        else:
            _ER_REGISTRY_CACHE = {}
    return _ER_REGISTRY_CACHE


def _extract_section(md_text: str, heading: str) -> Optional[str]:
    """Return the body text of a ``## <heading>`` section (excluding the heading
    line itself), or None if the section isn't present."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(md_text)
    if not m:
        return None
    return m.group(1).strip("\n")


_REF_TOKEN = re.compile(r"`([A-Za-z0-9_./-]+\.(?:md|py|json|yaml|yml))`")


def _absolutize_refs(text: str) -> str:
    """Rewrite knowledge-relative backticked paths to full fund-repo paths.

    ``knowledge/references/sectors/generic.md`` cites a sibling as
    ``methodology/buyside_depth.md``, which is correct *there* and meaningless once
    the prose lands in ``research/equity_researcher/``, a different repo root. The ER
    subsystem's ``tools/preflight.py`` scans every backticked path in its markdown and
    fails on ones that resolve nowhere, which is how it earns its keep — so the
    generator owes it a path that means something from where the file ends up."""
    def sub(m: re.Match[str]) -> str:
        ref = m.group(1)
        if (KNOWLEDGE_SECTOR_DIR.parent / ref).exists():
            return f"`knowledge/references/{ref}`"
        return m.group(0)

    return _REF_TOKEN.sub(sub, text)


def _reflow(paragraph: str) -> str:
    """Collapse hard-wrapped source markdown into single-line prose."""
    return _absolutize_refs(re.sub(r"\s+", " ", paragraph).strip())


def _extract_core_truth(md_text: str) -> str:
    section = _extract_section(md_text, "Core truth")
    if section:
        return _reflow(section)
    # generic.md has no "Core truth" heading; fall back to the paragraph
    # right after the title/intro block (first non-heading paragraph).
    return ""


def _extract_bullets(section_text: str) -> list[str]:
    lines = []
    for line in section_text.splitlines():
        line = line.rstrip()
        if line.strip().startswith("- "):
            lines.append(line)
        elif lines and line.startswith("  "):
            # continuation of a wrapped bullet
            lines[-1] += " " + line.strip()
    return [_absolutize_refs(ln) for ln in lines]


def _kpi_floor(registry_data: dict) -> tuple[int, list[str]]:
    """The governed KPI floor as (count, ordered category labels).

    Deliberately NOT a per-KPI table: the tier-2 playbook owns the KPI detail, and
    duplicating it here fails E10 in the ER validator. What the pack owes a reader is
    *where the governed vocabulary lives and how wide it is*, which is this."""
    kpis = registry_data.get("quantitative_kpis", []) or []
    order: list[str] = []
    for kpi in kpis:
        category = kpi.get("category", "uncategorized")
        if category not in order:
            order.append(category)
    return len(kpis), [_category_label(c) for c in order]


def _children(sector: str) -> list[tuple[str, dict]]:
    """Child playbooks of this family, in registry order."""
    reg = er_registry()
    return [(slug, p) for slug, p in (reg.get("playbooks") or {}).items()
            if p.get("family") == sector]


def _child_table(sector: str) -> list[str]:
    """The routing table. E10 excludes it by name (`| Playbook |` header), because its
    unit-lens column legitimately names the same denominator the playbook uses."""
    kids = _children(sector)
    if not kids:
        return []
    rows = ["| Playbook | Routes on | Unit lens | Status |", "|---|---|---|---|"]
    for slug, p in kids:
        kws = p.get("keywords") or []
        # first three keywords are enough to say what the child covers; the full list is
        # the registry's, and restating it here would be a second copy that drifts
        routes = ", ".join(str(k) for k in kws[:3]) if kws else "—"
        unit = str(p.get("unit_denominator") or "—").replace("_", " ")
        rows.append(f"| `{slug}` | {routes} | {unit} | {p.get('status', '?')} |")
    return rows


def _frame_line(sector: str) -> str:
    """The family's interpretation frame, in machine tokens."""
    fam = (er_registry().get("families") or {}).get(sector) or {}
    primary = fam.get("primary_multiple")
    if not primary:
        return ""
    secondary = fam.get("secondary_multiples") or []
    conds = fam.get("multiple_conditioners") or []
    parts = [f"primary `{primary}`"]
    if secondary:
        parts.append("secondary " + ", ".join(f"`{s}`" for s in secondary))
    if conds:
        parts.append("conditioned by " + ", ".join(f"`{c}`" for c in conds))
    return "; ".join(parts)


def render_pack(sector: str) -> str:
    registry_data = _load_registry_kpis(sector)
    knowledge_path = KNOWLEDGE_SECTOR_DIR / f"{sector}.md"
    md_text = knowledge_path.read_text(encoding="utf-8")

    fam = (er_registry().get("families") or {}).get(sector) or {}
    title = fam.get("display") or SECTOR_TITLES.get(sector, sector.replace("_", " ").title())
    core_truth = _extract_core_truth(md_text)
    lenses_bullets = _extract_bullets(_extract_section(md_text, "Qualitative lenses") or "")
    kpi_count, kpi_categories = _kpi_floor(registry_data)
    preferred_sources = _reflow(_extract_section(md_text, "Preferred sources") or "")
    extraction_note = _reflow(_extract_section(md_text, "Extraction note") or "")
    rel_val = _reflow(_extract_section(md_text, "Relative-valuation justifier") or "")

    lines: list[str] = []
    lines.append(GENERATED_HEADER)
    lines.append(f"# Sector Pack — {title} *(tier 1 — routing family)*")
    lines.append("")
    lines.append(TIER1_NOTE)
    lines.append("")
    if core_truth:
        lines.append(f"**Core truth:** {core_truth}")
        lines.append("")
    lines.append("## What the whole family has in common")
    lines.extend(lenses_bullets)
    lines.append("")

    child_table = _child_table(sector)
    lines.append("## Child playbooks — select exactly one at triage (T2)")
    lines.append("")
    if child_table:
        lines.extend(child_table)
        lines.append("")
        lines.append(
            "`Routes on` shows the first few routing keywords only; "
            "`config/sector_registry.yaml` carries the full list and is the source of "
            "truth. A company spanning two children is multi-segment: primary by largest "
            "EBIT, the other recorded as a `secondary_playbook`. If a child is ever marked "
            "`status: pending`, analyse on this pack plus the closest authored sibling, "
            "state in the note which convention you borrowed, and do **not** fall through "
            "to `generic`."
        )
    else:
        lines.append(
            "No child playbooks are registered for this family in "
            "`config/sector_registry.yaml` — analyse on this pack and say so in the note."
        )
    lines.append("")

    frame = _frame_line(sector)
    if frame:
        lines.append("## Interpretation frame (family default)")
        lines.append("")
        lines.append(f"Multiples: {frame}.")
        lines.append("")
        lines.append(
            "These are the family-level defaults; the child playbook overrides them and "
            "carries the sub-sector's `## Divergence cases`. A conditioner names *which "
            "variable* makes a given multiple expensive or cheap — the same P/E supports "
            "opposite readings depending on it (`docs/OPINION_VS_ANALYSIS.md` §7)."
        )
        lines.append("")

    lines.append("## Governed KPI floor")
    lines.append("")
    lines.append(
        f"The fund's governed KPI vocabulary for this sector is "
        f"`registry/kpis/{sector}.yaml` — {kpi_count} KPIs across "
        f"{len(kpi_categories)} categories ({', '.join(kpi_categories)}). "
        f"Read it via `registry.registry.Registry.load()`; it is never restated here, "
        f"and the per-KPI detail belongs to the tier-2 playbook. "
        f"`scripts/gen_sector_packs.py --check` reports any child playbook "
        f"`signature_kpi` this vocabulary does not cover."
    )
    lines.append("")
    if rel_val:
        lines.append(f"**Relative-valuation justifier:** {rel_val}")
        lines.append("")
    if preferred_sources:
        lines.append(f"**Preferred sources:** {preferred_sources}")
        lines.append("")
    if extraction_note:
        lines.append(f"**Note:** {extraction_note}")
        lines.append("")

    text = "\n".join(lines)
    # collapse any accidental multiple-blank-lines and ensure single
    # trailing newline
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"
    return text


def sectors() -> list[str]:
    return sorted(p.stem for p in REGISTRY_KPI_DIR.glob("*.yaml"))


_STOPWORDS = {"pct", "inr", "usd", "mn", "cr", "bps", "x", "count", "per", "of", "to", "ltm"}


def _stems(name: str) -> set[str]:
    return {t.rstrip("s") for t in re.findall(r"[a-z0-9]+", str(name).lower())
            if t not in _STOPWORDS}


def kpi_coverage(sector: str) -> dict[str, list[str]]:
    """Which child-playbook signature KPIs the fund registry's vocabulary does NOT cover.

    Matching is on word stems, the same way ER's E8 matches a registry KPI name against
    playbook prose — `revenue_per_employee_usd` and "revenue per employee" are the same
    KPI wearing different clothes. Returns {playbook_slug: [uncovered kpi names]}."""
    vocab: set[str] = set()
    for kpi in _load_registry_kpis(sector).get("quantitative_kpis", []) or []:
        vocab |= _stems(kpi.get("name", ""))
    gaps: dict[str, list[str]] = {}
    for slug, p in _children(sector):
        missing = [sig for sig in (p.get("signature_kpis") or [])
                   if not (_stems(sig) and _stems(sig) <= vocab)]
        if missing:
            gaps[slug] = missing
    return gaps


def _print_coverage_report() -> None:
    """Reported, never silently dropped — but not fatal. The ER playbooks are finer-
    grained than the fund's 8-sector vocabulary by design, so a gap is information about
    where the fund registry could grow, not a build break."""
    total = 0
    lines: list[str] = []
    for sector in sectors():
        gaps = kpi_coverage(sector)
        for slug, missing in sorted(gaps.items()):
            total += len(missing)
            lines.append(f"    {sector}/{slug}: {', '.join(missing)}")
    print(f"\nRegistry KPI coverage: {total} playbook signature_kpi(s) not in registry/kpis/ "
          f"(reported, not fatal — see the docstring)")
    for ln in lines:
        print(ln)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Don't write files; exit 1 if any generated pack would differ. Also prints "
             "the registry KPI coverage report.",
    )
    args = parser.parse_args()

    diffs: list[str] = []
    written = 0
    for sector in sectors():
        rendered = render_pack(sector)
        out_path = SECTOR_PACKS_DIR / f"{sector}.md"
        existing = out_path.read_text(encoding="utf-8") if out_path.exists() else None
        if existing == rendered:
            continue
        diffs.append(sector)
        if not args.check:
            out_path.write_text(rendered, encoding="utf-8")
            written += 1

    if args.check:
        _print_coverage_report()
        if diffs:
            print(f"\nOUT OF DATE: {', '.join(diffs)}")
            return 1
        print("\nAll sector packs up to date.")
        return 0

    print(f"Generated {len(sectors())} sector packs; {written} changed.")
    if diffs:
        print(f"Changed: {', '.join(diffs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
