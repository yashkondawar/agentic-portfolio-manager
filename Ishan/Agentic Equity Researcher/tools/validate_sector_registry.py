"""Validate config/sector_registry.yaml. Deterministic, zero LLM tokens.

    python tools/validate_sector_registry.py
    python tools/validate_sector_registry.py --sync-schema   # rewrite the handoff enum

Checks:
  E1  every family's pack file exists
  E2  every playbook's `family` resolves to a declared family
  E3  every playbook marked `status: authored` has its file on disk
  E4  no duplicate playbook slug, no slug colliding with a family slug
  E5  no keyword shorter than 5 characters — the bare-acronym trap that once matched
      "ape"/"apex" 44 times in a transmission-conductor note and routed it to BFSI
  E6  no keyword claimed by two playbooks in different families (ambiguous routing)
  E7  schema/valuation_handoff.schema.json's sector_pack enum matches the family list
  E8  every declared signature KPI appears in its playbook file (registry <-> playbook
      contract; tools/compute_kpis.py checks run coverage against the same list)
  E9  an authored playbook carries the sections downstream modules read
  E10 a playbook does not restate its family pack's KPI content — packs route, playbooks
      analyse. Added after the first two-tier draft had bfsi.md and nbfc_diversified.md
      duplicating essentially every KPI.
  E11 the registry does not carry prose that belongs in a playbook file. `valuation_convention`
      used to sit here as a one-line summary per playbook, which made this file a second,
      shorter, drifting copy of the playbook's own "## Valuation convention" section. The
      prose moved down; this check stops it coming back.
  E12 every authored playbook, and every family, declares an interpretation frame — a
      `primary_multiple` and at least one `multiple_conditioner`. Without a conditioner a
      reading has nothing to name, and docs/OPINION_VS_ANALYSIS.md section 7 collapses back
      into "the analyst thinks 30x is expensive".
  E13 every token in `primary_multiple` / `secondary_multiples` / `multiple_conditioners`
      comes from `interpretation_vocabulary`. The vocabulary is closed on purpose: readings
      are only comparable across notes if the conditioner names are. An invented token is
      the same defect E7 exists for — it validates silently and routes nothing.
  E14 an authored playbook carries a "## Divergence cases" section. E9 checks the sections a
      module reads to *analyse*; this one checks the section prompts/33 reads to seed
      state/interpretation_ledger.json.
  W1  a family with no playbooks
  I1  playbooks still `status: pending`

Exit code 1 on any E-level failure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "config" / "sector_registry.yaml"
HANDOFF_SCHEMA = REPO / "schema" / "valuation_handoff.schema.json"
MIN_KEYWORD_LEN = 5


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync-schema", action="store_true",
                    help="rewrite the sector_pack enum in the handoff schema from the registry")
    a = ap.parse_args()

    reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    families: dict = reg.get("families") or {}
    playbooks: dict = reg.get("playbooks") or {}

    errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    # E1
    for slug, f in families.items():
        pack = REPO / str(f.get("pack", ""))
        if not pack.exists():
            errors.append(f"E1 family '{slug}': pack file missing -> {f.get('pack')}")

    # E2/E3/E4
    seen: set[str] = set()
    for slug, p in playbooks.items():
        if slug in seen:
            errors.append(f"E4 duplicate playbook slug '{slug}'")
        seen.add(slug)
        if slug in families and slug != "generic":
            errors.append(f"E4 playbook slug '{slug}' collides with a family slug")
        fam = p.get("family")
        if fam not in families:
            errors.append(f"E2 playbook '{slug}': family '{fam}' is not declared")
        status = p.get("status", "pending")
        path = REPO / "prompts" / "sector_playbooks" / f"{slug}.md"
        # No exemptions. An earlier version carried `and slug != "generic"`, which meant the
        # registry could mark `generic` authored with no file on disk and E3 stayed silent —
        # while prompts/02, /03 and /41 all resolve `sector_playbooks/<slug>.md` for an
        # authored playbook, so a `generic` classification hit a missing file at run time.
        # The escape hatch hid exactly the defect this check exists to catch.
        if status == "authored" and not path.exists():
            errors.append(f"E3 playbook '{slug}' is marked authored but {path.relative_to(REPO)} is missing")
        if status == "pending":
            infos.append(f"I1 playbook '{slug}' pending (routes to family pack "
                         f"'{families.get(fam, {}).get('pack', '?')}' meanwhile)")
        if status not in ("authored", "pending"):
            errors.append(f"E3 playbook '{slug}': unknown status '{status}'")

    # E5/E6
    owner: dict[str, list[str]] = defaultdict(list)
    for slug, p in playbooks.items():
        for kw in p.get("keywords") or []:
            k = str(kw).strip().lower()
            if len(k) < MIN_KEYWORD_LEN:
                errors.append(
                    f"E5 playbook '{slug}': keyword {k!r} is {len(k)} chars. Bare short "
                    f"acronyms match inside longer words — see the header warning in "
                    f"sector_registry.yaml. Use a multi-word phrase.")
            owner[k].append(slug)
    for kw, slugs in owner.items():
        if len(slugs) > 1:
            fams = {playbooks[s].get("family") for s in slugs}
            if len(fams) > 1:
                errors.append(f"E6 keyword {kw!r} claimed across families by {slugs}")
            else:
                warnings.append(f"W  keyword {kw!r} shared within one family by {slugs}")

    # W1
    have = {p.get("family") for p in playbooks.values()}
    for slug in families:
        if slug not in have:
            warnings.append(f"W1 family '{slug}' has no playbooks")

    # E8 — every declared signature KPI actually appears in its playbook file. The registry's
    # signature_kpis list is the machine-readable contract that tools/compute_kpis.py checks
    # coverage against; if a name is in the registry but not in the playbook's KPI table, the
    # two halves of the contract disagree and a run will chase a KPI nobody defined.
    # E9 — an authored playbook carries the sections downstream modules read.
    REQUIRED_SECTIONS = ["Signature KPIs", "Valuation convention", "Standard exhibit set",
                         "forensic screens", "Common archetypes"]
    for slug, p in playbooks.items():
        if p.get("status") != "authored":
            continue
        path = REPO / "prompts" / "sector_playbooks" / f"{slug}.md"
        if not path.exists():
            continue  # already reported by E3
        text = path.read_text(encoding="utf-8")
        low = text.lower()
        # Compare against a squashed haystack (letters+digits only) so surface differences in
        # punctuation don't read as disagreements: the registry writes `..._top5_pct` where the
        # playbook writes "top-5 customer share".
        squashed = re.sub(r"[^a-z0-9]+", "", low)
        for sig in p.get("signature_kpis") or []:
            # match on the KPI's word stems, not the exact snake_case name — the playbook
            # writes "EBITDA per tonne" where the registry writes "ebitda_per_tonne_inr"
            stems = [t for t in re.findall(r"[a-z0-9]+", str(sig).lower())
                     if t not in {"pct", "inr", "usd", "x", "count", "bps", "mn", "cr", "per", "of", "to"}]
            if stems and not all(s.rstrip("s") in squashed for s in stems):
                errors.append(f"E8 playbook '{slug}': registry signature KPI '{sig}' does not "
                              f"appear in {path.relative_to(REPO)} — the registry and the "
                              f"playbook disagree about this sub-sector's defining metrics")
        for sec in REQUIRED_SECTIONS:
            if sec.lower() not in low:
                errors.append(f"E9 playbook '{slug}': missing required section '{sec}'")

    # E10 — a playbook must not restate its family pack's KPI content. Packs are tier-1
    # routers; playbooks own the analysis. This check exists because the first version of the
    # two-tier design had bfsi.md and nbfc_diversified.md duplicating essentially every KPI.
    # The pack's "Child playbooks" routing table is excluded — its unit-lens column legitimately
    # names the same denominator the playbook uses.
    # Compare the KPI PHRASES a table mentions, not whole cell strings. Matching whole cells
    # only caught byte-identical text, so a pack row reading "cost of funds %, cost-income %"
    # and a playbook row reading "**Cost of funds**" registered as no overlap at all — which
    # is precisely the duplication this check exists to stop.
    KPI_KEYS = ("margin", "roce", "roe", "roa", "nim", "gnpa", "nnpa", "days", "per tonne",
                "per key", "per bed", "per store", "per employee", "per test", "per policy",
                "yield", "utilisation", "utilization", "occupancy", "turnover", "ebitda",
                "arpu", "sssg", "revpar", "arpob", "book-to-bill", "cost of funds",
                "cost-income", "cost to income", "credit cost", "order book", "casa")

    def _kpi_phrases(text: str, drop_child_table: bool = False) -> set[str]:
        if drop_child_table:
            # the pack's routing table legitimately names each child's unit lens
            text = re.sub(r"\n\|\s*Playbook\s*\|.*?(?=\n\n|\n#|\Z)", "", text, flags=re.S)
        out = set()
        for ln in text.splitlines():
            if ln.strip().startswith("|") and ln.count("|") >= 3:
                c = ln.lower()
                for k in KPI_KEYS:
                    if k in c:
                        out.add(k)
        return out

    for slug, p in playbooks.items():
        if p.get("status") != "authored":
            continue
        cp = REPO / "prompts" / "sector_playbooks" / f"{slug}.md"
        fam = families.get(p.get("family")) or {}
        pk = REPO / str(fam.get("pack", ""))
        if not (cp.exists() and pk.exists()):
            continue
        overlap = (_kpi_phrases(pk.read_text(encoding="utf-8"), drop_child_table=True)
                   & _kpi_phrases(cp.read_text(encoding="utf-8")))
        if overlap:
            errors.append(f"E10 playbook '{slug}' and its family pack {pk.name} both carry KPI "
                          f"content: {sorted(overlap)[:5]} — packs route, playbooks analyse. "
                          f"Move it down into the playbook.")

    # E11 — the registry routes and contracts; it does not narrate. Any key here that restates
    # something the playbook file owns is a second copy that will drift, so it is an error, not a
    # style preference. Keys allowed on a playbook entry are exactly the machine-read ones.
    PROSE_KEYS = {"valuation_convention", "analysis_sequence", "exhibit_set",
                  "forensic_screens", "economic_engine", "traps"}
    # The interpretation-frame keys are machine tokens, not prose — three enum values, no
    # sentences — so they are allowed here while `valuation_convention` stays banned. The
    # distinction E11 actually enforces is "does this duplicate a paragraph the playbook
    # owns", and a token list does not.
    ALLOWED_PLAYBOOK_KEYS = {"family", "status", "keywords", "signature_kpis", "unit_denominator",
                             "primary_multiple", "secondary_multiples", "multiple_conditioners"}
    for slug, p in playbooks.items():
        for k in p:
            if k in PROSE_KEYS:
                errors.append(
                    f"E11 playbook '{slug}': key '{k}' belongs in "
                    f"prompts/sector_playbooks/{slug}.md, not in the registry. Keeping it in both "
                    f"places creates a shorter copy that drifts from the playbook's own section.")
            elif k not in ALLOWED_PLAYBOOK_KEYS:
                warnings.append(
                    f"W  playbook '{slug}': unrecognised key '{k}'. The registry carries only "
                    f"{sorted(ALLOWED_PLAYBOOK_KEYS)}; anything else probably belongs in the "
                    f"playbook file.")

    # E12/E13/E14 — the interpretation frame (docs/OPINION_VS_ANALYSIS.md section 7).
    # A "reading" is `fact + conditioning variable + sector convention -> verdict`. The
    # convention prose lives in the playbook (E11 put it there); what lives here is the
    # machine form. These three checks keep that form honest: declared, drawn from a closed
    # vocabulary, and backed by a section in the playbook that a human actually wrote.
    vocab = reg.get("interpretation_vocabulary") or {}
    VOCAB_CONDS = set(vocab.get("conditioning_variables") or [])
    VOCAB_MULTS = set(vocab.get("multiples") or [])
    if not VOCAB_CONDS or not VOCAB_MULTS:
        errors.append("E13 interpretation_vocabulary is missing or incomplete — it must declare "
                      "both `conditioning_variables` and `multiples`. Without it E13 cannot "
                      "distinguish a real token from a typo, which is the whole point.")

    def _check_frame(kind: str, slug: str, entry: dict) -> None:
        primary = entry.get("primary_multiple")
        secondary = entry.get("secondary_multiples") or []
        conds = entry.get("multiple_conditioners") or []
        if not primary:
            errors.append(f"E12 {kind} '{slug}': no primary_multiple. Every routable unit must "
                          f"name the multiple its readings are judged against.")
        if not conds:
            errors.append(f"E12 {kind} '{slug}': no multiple_conditioners. A reading with no "
                          f"named conditioner is an unearned adjective "
                          f"(docs/OPINION_VS_ANALYSIS.md section 2, F6).")
        if not isinstance(secondary, list):
            errors.append(f"E12 {kind} '{slug}': secondary_multiples must be a list")
            secondary = []
        for tok in ([primary] if primary else []) + list(secondary):
            if VOCAB_MULTS and tok not in VOCAB_MULTS:
                errors.append(f"E13 {kind} '{slug}': multiple {tok!r} is not in "
                              f"interpretation_vocabulary.multiples. Add it there deliberately "
                              f"or fix the typo — the vocabulary is closed so that readings "
                              f"stay comparable across notes.")
        for tok in conds:
            if VOCAB_CONDS and tok not in VOCAB_CONDS:
                errors.append(f"E13 {kind} '{slug}': conditioner {tok!r} is not in "
                              f"interpretation_vocabulary.conditioning_variables. "
                              f"schema/interpretation.schema.json carries the same enum; a token "
                              f"only here would fail state validation at run time.")

    for slug, f in families.items():
        _check_frame("family", slug, f)
    for slug, p in playbooks.items():
        if p.get("status") == "authored":
            _check_frame("playbook", slug, p)

    # E14 — the playbook's own "## Divergence cases" section. Kept separate from E9's
    # REQUIRED_SECTIONS so the failure message can say what the section is *for*: prompts/33
    # reads it to seed state/interpretation_ledger.json, and an empty seed produces a ledger
    # where our reading is the only reading on record — check 17's failure mode.
    for slug, p in playbooks.items():
        if p.get("status") != "authored":
            continue
        path = REPO / "prompts" / "sector_playbooks" / f"{slug}.md"
        if not path.exists():
            continue  # already reported by E3
        if "## divergence cases" not in path.read_text(encoding="utf-8").lower():
            errors.append(f"E14 playbook '{slug}': missing '## Divergence cases'. prompts/33 "
                          f"reads it to seed state/interpretation_ledger.json — without it the "
                          f"sub-sector has no worked same-fact/different-reading examples and "
                          f"the ledger degrades to a single reading per fact.")

    # E7 (+ optional sync)
    if HANDOFF_SCHEMA.exists():
        schema = json.loads(HANDOFF_SCHEMA.read_text(encoding="utf-8"))
        node = (schema.get("properties", {}).get("company", {})
                .get("properties", {}).get("sector_pack", {}))
        want = sorted(families)
        if a.sync_schema:
            node["enum"] = want
            node.setdefault("description",
                            "Family slug from config/sector_registry.yaml. "
                            "Kept in sync by tools/validate_sector_registry.py --sync-schema.")
            HANDOFF_SCHEMA.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
            print(f"synced sector_pack enum -> {want}")
        else:
            got = node.get("enum")
            if got is None:
                errors.append("E7 valuation_handoff.schema.json: company.sector_pack has no enum "
                              "(a typo'd pack name validates silently). Run --sync-schema.")
            elif sorted(got) != want:
                errors.append(f"E7 sector_pack enum out of sync.\n     schema:   {sorted(got)}\n"
                              f"     registry: {want}\n     Run --sync-schema.")

    for m in infos:
        print(f"INFO  {m}")
    for m in warnings:
        print(f"WARN  {m}")
    for m in errors:
        print(f"ERROR {m}")

    authored = sum(1 for p in playbooks.values() if p.get("status") == "authored")
    print(f"\n{len(families)} families, {len(playbooks)} playbooks "
          f"({authored} authored, {len(playbooks)-authored} pending), "
          f"{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
