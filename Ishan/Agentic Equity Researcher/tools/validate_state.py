"""Validate a run's workspace state against schema/*.json. Deterministic, zero LLM tokens.

    python tools/validate_state.py workspace/NALCO
    python tools/validate_state.py workspace/NALCO --strict   # absent artefacts are errors

Why this exists: `workspace/NALCO/state/thesis.json` was written by a run that predated
`schema/thesis.schema.json` and is missing **6 of its 9 required fields** (as_of,
return_decomposition, archetype, pillars, must_be_true, monitorables). Nothing noticed,
because nothing validated run state — the schemas existed and were read by humans only.
The whole point of `prompts/33` is that the thesis is *owned*; an unvalidated thesis file
is not owned, it is just a file.

Checks, by artefact:
  thesis.json                 required fields, enums, return-decomposition arithmetic,
                              the 40% re-rating gate, redteam block ownership
  interpretation_ledger.json  required fields, >=2 readings per entry, conditioning
                              variables inside the closed vocabulary, discriminator type
                              admissible, and `resolved: true` actually backed by one
  business_model.json         value chain, KPI tree, unit economics, net position
  triage.json                 schema shape + family/playbook resolve against the registry
  facts/*.json                fact-record required fields, unique ids, source anchors
  state/red_flags.json        red-flag record shape; no unresolved `candidate` at convergence
  state/open_questions.json   open-question shape; severity>=medium must be answered or disclosed
  verification_report.json    final_gate_decision present and named; CLAUDE.md rule 6's
                              itemised-override rule enforced mechanically

Exit code 1 on any ERROR. INFO/WARN never fail the run.

No jsonschema dependency: the checks are written directly so this runs on the key-free
install (see tools/requirements.txt).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO / "schema"
REGISTRY = REPO / "config" / "sector_registry.yaml"

errors: list[str] = []
warnings: list[str] = []
infos: list[str] = []


def err(code: str, msg: str) -> None:
    errors.append(f"{code} {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)


def info(msg: str) -> None:
    infos.append(msg)


def rel(path: Path) -> str:
    """Repo-relative display path, tolerant of a workspace passed as a relative path or
    living outside the repo — both are legitimate, since the workspace is user input."""
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def load_json(path: Path):
    """Returns (data, error_string). Never raises."""
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def schema_required(name: str) -> list[str]:
    data, e = load_json(SCHEMA_DIR / name)
    if e or not isinstance(data, dict):
        return []
    return list(data.get("required") or [])


def registry() -> dict:
    if not REGISTRY.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - registry is advisory here
        warn(f"could not read {REGISTRY.name} ({exc}); registry cross-checks skipped")
        return {}


# --------------------------------------------------------------------------- #
# thesis.json — the artefact this tool was written for
# --------------------------------------------------------------------------- #
def check_thesis(ws: Path, strict: bool) -> None:
    path = ws / "state" / "thesis.json"
    data, e = load_json(path)
    if e == "missing":
        msg = (f"{rel(path)} absent - wave 6a (prompts/33) has not run. Nothing else owns the "
               f"thesis, so the rating would be unsourced.")
        err("E-THESIS-MISSING", msg) if strict else warn(msg)
        return
    if e:
        err("E-THESIS-JSON", f"{rel(path)}: {e}")
        return

    req = schema_required("thesis.schema.json")
    missing = [k for k in req if k not in data]
    if missing:
        err("E-THESIS-REQUIRED",
            f"{rel(path)} is missing {len(missing)} of {len(req)} required fields: "
            f"{missing}. prompts/33 owns this file; a thesis that does not validate is not owned.")

    rd = data.get("return_decomposition")
    if isinstance(rd, dict):
        exp = rd.get("expected_return_pct")
        share = rd.get("multiple_share_pct")
        if share is not None and not (0 <= _num(share, -1) <= 100):
            err("E-THESIS-SHARE", f"return_decomposition.multiple_share_pct={share!r} is not a percentage")
        cm, tm = _num(rd.get("current_multiple")), _num(rd.get("target_multiple"))
        cme, tme = _num(rd.get("current_metric")), _num(rd.get("target_year_metric"))
        if None not in (cm, tm, cme, tme) and cm > 0 and cme > 0:
            # total return = (tm*tme)/(cm*cme) - 1 ; the multiple's share of that
            total = (tm * tme) / (cm * cme) - 1.0
            if exp is not None and abs(total * 100 - _num(exp, 0)) > 5.0:
                warn(f"thesis.return_decomposition: expected_return_pct={exp} but "
                     f"multiple x metric implies {total*100:.1f}% — decomposition may not tie")
            if total not in (0,) and share is not None:
                implied = ((tm / cm) - 1.0) / total * 100 if total else 0.0
                if abs(implied - _num(share, 0)) > 10.0:
                    warn(f"thesis.return_decomposition: multiple_share_pct={share} but the "
                         f"multiples imply ~{implied:.0f}% — recheck the split")
        if not rd.get("valuation_base_year"):
            warn("thesis.return_decomposition.valuation_base_year is empty — the corpus's "
                 "rolled-forward-base trap (ER_CORPUS_FINDINGS §4) needs the base year stated")

        # The 40% rule is arithmetic, not editorial. It is symmetric: a thesis whose return is
        # mostly the multiple FALLING is just as multiple-driven as one where it rises, and gets
        # the same checklist. So `de-rating` and `cyclical-peak` satisfy it alongside `re-rating`,
        # and an explicit `forced_rerating: true` satisfies it however the archetype is labelled.
        MULTIPLE_DRIVEN = {"re-rating", "de-rating", "cyclical-peak"}
        thr = _config_threshold()
        if share is not None and thr is not None and _num(share, 0) > thr:
            arch = data.get("archetype") or {}
            if isinstance(arch, dict):
                name = str(arch.get("primary") or arch.get("name") or "").lower()
                secondary = str(arch.get("secondary") or "").lower()
                forced = bool(arch.get("forced_rerating"))
            else:
                name, secondary, forced = str(arch).lower(), "", False
            if not forced and name not in MULTIPLE_DRIVEN and secondary not in MULTIPLE_DRIVEN:
                err("E-THESIS-40PCT",
                    f"multiple_share_pct={share} exceeds rerate_share_threshold_pct={thr}, but the "
                    f"archetype is {name!r} and forced_rerating is not set. Above the threshold the "
                    f"re-rating checklist applies whatever the thesis calls itself — set "
                    f"archetype.forced_rerating: true, or use one of {sorted(MULTIPLE_DRIVEN)}.")

    rt = data.get("redteam")
    if isinstance(rt, dict):
        if _num(rt.get("rounds"), 0) < 1:
            err("E-THESIS-REDTEAM-ROUNDS",
                "redteam.rounds < 1 — one 33->34->33 round trip is mandatory "
                "(config.thesis.redteam_min_rounds)")
        if rt.get("verdict") == "not_established":
            err("E-THESIS-REDTEAM-VERDICT",
                "redteam.verdict is 'not_established' — the thesis is not publishable as-is; "
                "prompts/33 step 7b must revise it or downgrade the rating")
    elif "must_be_true" in data:
        warn("thesis.redteam absent — module 34 has not run, or module 33 has not done its "
             "mandatory post-red-team pass (prompts/33 step 7b, which owns this block)")


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _config_threshold():
    cfg = REPO / "config" / "agent_config.yaml"
    if not cfg.exists():
        return None
    try:
        import yaml
        c = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        return _num((c.get("thesis") or {}).get("rerate_share_threshold_pct"))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
def check_business_model(ws: Path, strict: bool) -> None:
    path = ws / "state" / "business_model.json"
    data, e = load_json(path)
    if e == "missing":
        msg = (f"{rel(path)} absent — wave 1.5 (prompts/03) has not run. This is "
               f"the analytical spine: without it compute_kpis.py falls back to keyword "
               f"matching and emits per-unit economics as skips.")
        err("E-BIZMODEL-MISSING", msg) if strict else warn(msg)
        return
    if e:
        err("E-BIZMODEL-JSON", f"{rel(path)}: {e}")
        return
    for field, why in [
        ("value_chain", "the asset map prompts/41 renders as an exhibit"),
        ("kpi_tree", "what compute_kpis.py computes per-unit economics from"),
        ("unit_economics", "the denominator per-unit KPIs divide by"),
        ("swing_drivers", "what the sensitivity table in prompts/32 varies"),
        ("net_position", "the one-line structural tilt the note's rating box states"),
    ]:
        if not data.get(field):
            err("E-BIZMODEL-FIELD", f"business_model.json has no `{field}` — {why}")
    ue = data.get("unit_economics")
    if isinstance(ue, dict) and not ue.get("denominator"):
        err("E-BIZMODEL-DENOM",
            "unit_economics.denominator is empty — per-unit economics cannot be computed "
            "without it (compare unit_denominator for this playbook in the registry)")


# --------------------------------------------------------------------------- #
def check_triage(ws: Path, strict: bool) -> None:
    path = ws / "state" / "triage.json"
    data, e = load_json(path)
    if e == "missing":
        msg = f"{rel(path)} absent — wave 1 (prompts/02) has not run"
        err("E-TRIAGE-MISSING", msg) if strict else warn(msg)
        return
    if e:
        err("E-TRIAGE-JSON", f"{rel(path)}: {e}")
        return

    for k in schema_required("triage.schema.json"):
        if k not in data:
            err("E-TRIAGE-REQUIRED", f"triage.json missing required field `{k}` "
                                     f"(schema/triage.schema.json)")

    reg = registry()
    fams, pbs = (reg.get("families") or {}), (reg.get("playbooks") or {})
    sec = data.get("sector")
    if not isinstance(sec, dict):
        # tolerate the pre-schema shape but say so plainly
        if isinstance(data.get("decisions"), list):
            warn("triage.json has no `sector` object — this is the pre-2026-08-03 shape where T2 "
                 "lived only as prose inside `decisions`. Downstream consumers "
                 "(compute_kpis --playbook, compute_ratios --family, prompts/31, prompts/41) "
                 "cannot read a slug out of prose. Re-run T2 to emit the structured block.")
        return
    fam, pb = sec.get("family"), sec.get("playbook")
    if fams and fam not in fams:
        err("E-TRIAGE-FAMILY", f"triage sector.family={fam!r} is not a declared family in "
                               f"config/sector_registry.yaml")
    if pb and pbs and pb not in pbs:
        err("E-TRIAGE-PLAYBOOK", f"triage sector.playbook={pb!r} is not a declared playbook in "
                                 f"config/sector_registry.yaml")
    if pb and pbs.get(pb) and fam and pbs[pb].get("family") != fam:
        err("E-TRIAGE-MISMATCH",
            f"triage says playbook={pb!r} with family={fam!r}, but the registry puts {pb!r} "
            f"under family {pbs[pb].get('family')!r}")
    if pb and (REPO / "prompts" / "sector_playbooks" / f"{pb}.md").exists() is False:
        err("E-TRIAGE-NOFILE", f"playbook {pb!r} has no file at prompts/sector_playbooks/{pb}.md")
    if sec.get("confidence") == "low":
        info(f"triage confidence is `low` for playbook={pb!r} — T2-RECHECK after prompts/03 is "
             f"mandatory and the run should expect to leave this classification")
    if pb == "generic" and not sec.get("generic_reason"):
        warn("playbook is `generic` but sector.generic_reason is unset — record which of "
             "uncovered_subsector / conglomerate / low_confidence applies "
             "(prompts/sector_playbooks/generic.md)")


# --------------------------------------------------------------------------- #
# interpretation_ledger.json — same fact, divergent readings
# --------------------------------------------------------------------------- #
def _schema_enum(name: str, *path: str) -> list[str]:
    """Pull an enum out of a schema by key path, so the vocabulary is never duplicated here."""
    data, e = load_json(SCHEMA_DIR / name)
    if e or not isinstance(data, dict):
        return []
    node = data
    for key in path:
        if not isinstance(node, dict):
            return []
        node = node.get(key)
    return list(node) if isinstance(node, list) else []


def check_interpretation_ledger(ws: Path, strict: bool) -> None:
    """docs/OPINION_VS_ANALYSIS.md §7. Written by prompts/33 step 6b, audited by prompts/34
    checks 16-18. This tool checks only what is mechanically checkable — that the entries
    have two readings, that the tokens are in the closed vocabulary, and that a `resolved`
    flag has a real discriminator behind it. Whether an opposing reading is *credible* is
    check 17's job and needs a reader."""
    path = ws / "state" / "interpretation_ledger.json"
    data, e = load_json(path)
    if e == "missing":
        msg = (f"{rel(path)} absent — prompts/33 step 6b has not run. Every valuation-relevant "
               f"fact whose reading is load-bearing needs an entry; without the ledger, "
               f"prompts/34 checks 16-18 cannot run.")
        err("E-LEDGER-MISSING", msg) if strict else warn(msg)
        return
    if e:
        err("E-LEDGER-JSON", f"{rel(path)}: {e}")
        return
    if not isinstance(data, dict):
        err("E-LEDGER-SHAPE", f"{rel(path)} is not an object (schema/interpretation.schema.json)")
        return

    for k in schema_required("interpretation.schema.json"):
        if k not in data:
            err("E-LEDGER-REQUIRED", f"interpretation_ledger.json missing required field `{k}` "
                                     f"(schema/interpretation.schema.json)")

    conds = set(_schema_enum("interpretation.schema.json",
                             "$defs", "conditioning_variable", "enum"))
    dtypes = set(_schema_enum("interpretation.schema.json",
                              "$defs", "discriminator", "properties", "type", "enum"))
    entry_req = ((load_json(SCHEMA_DIR / "interpretation.schema.json")[0] or {})
                 .get("$defs", {}).get("entry", {}).get("required") or [])

    # the playbook decides which convention the readings are judged against
    reg = registry()
    pbs = reg.get("playbooks") or {}
    pb = data.get("sector_playbook")
    if pb and pbs and pb not in pbs:
        err("E-LEDGER-PLAYBOOK", f"interpretation_ledger.sector_playbook={pb!r} is not a declared "
                                 f"playbook in config/sector_registry.yaml")
    triage, _ = load_json(ws / "state" / "triage.json")
    tpb = ((triage or {}).get("sector") or {}).get("playbook") if isinstance(triage, dict) else None
    if pb and tpb and pb != tpb:
        warn(f"interpretation_ledger.sector_playbook={pb!r} but triage says {tpb!r} — the ledger "
             f"is being judged against a different sector convention than the run classified")

    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        err("E-LEDGER-EMPTY",
            "interpretation_ledger.entries is empty — a thesis with no contested facts has not "
            "been tested (prompts/34 check 16). If nothing in the note is genuinely contestable, "
            "say that in the note rather than shipping an empty ledger.")
        return

    unresolved_high = 0
    for i, ent in enumerate(entries):
        tag = f"entries[{i}]"
        if not isinstance(ent, dict):
            err("E-LEDGER-ENTRY", f"{tag} is not an object")
            continue
        for k in entry_req:
            if k not in ent:
                err("E-LEDGER-ENTRY-REQUIRED", f"{tag} missing required field `{k}`")

        readings = ent.get("readings")
        if not isinstance(readings, list) or len(readings) < 2:
            n = len(readings) if isinstance(readings, list) else 0
            err("E-LEDGER-ONE-READING",
                f"{tag} has {n} reading(s); at least 2 are required. One reading is not a "
                f"divergence — it is failure mode F3 (a base case that is really the bull case) "
                f"in a new costume (prompts/34 check 17).")
            readings = readings if isinstance(readings, list) else []

        ours = 0
        for j, r in enumerate(readings):
            if not isinstance(r, dict):
                err("E-LEDGER-READING", f"{tag}.readings[{j}] is not an object")
                continue
            cv = r.get("conditioning_variable")
            if not cv:
                err("E-LEDGER-NO-CONDITIONER",
                    f"{tag}.readings[{j}] names no conditioning_variable — a reading without one "
                    f"is an unearned adjective (docs/OPINION_VS_ANALYSIS.md §2 F6)")
            elif conds and cv not in conds:
                err("E-LEDGER-VOCAB",
                    f"{tag}.readings[{j}].conditioning_variable={cv!r} is outside the closed "
                    f"vocabulary (docs/OPINION_VS_ANALYSIS.md §7.4)")
            if not str(r.get("reasoning") or "").strip():
                err("E-LEDGER-NO-REASONING",
                    f"{tag}.readings[{j}] has no reasoning — a reader must be able to reproduce "
                    f"the arithmetic that gets from the fact to the verdict")
            if r.get("is_ours"):
                ours += 1
        if readings and ours != 1:
            warn(f"{tag} marks {ours} reading(s) as `is_ours` — exactly one should carry it, so "
                 f"the note's own position is unambiguous")

        d = ent.get("discriminator")
        if not isinstance(d, dict):
            err("E-LEDGER-NO-DISCRIMINATOR", f"{tag} has no discriminator object")
            continue
        dt, ev, resolved = d.get("type"), str(d.get("evidence") or "").strip(), d.get("resolved")
        if dtypes and dt not in dtypes:
            err("E-LEDGER-DISC-TYPE",
                f"{tag}.discriminator.type={dt!r} is not one of the admissible types "
                f"{sorted(dtypes)}. Tone, consensus, 'the market is wrong' and analyst conviction "
                f"are not discriminators (docs/OPINION_VS_ANALYSIS.md §7.2).")
        if not ev:
            err("E-LEDGER-DISC-EVIDENCE",
                f"{tag}.discriminator.evidence is empty. With type `none_available`, state what "
                f"evidence WOULD settle it and why it could not be obtained.")
        if resolved and dt == "none_available":
            err("E-LEDGER-FALSE-RESOLVE",
                f"{tag} is marked resolved with discriminator type `none_available` — "
                f"prompts/34 check 18 downgrades this to unresolved. Set resolved:false and "
                f"promote it to a load-bearing assumption.")
        if resolved and not ev:
            err("E-LEDGER-FALSE-RESOLVE",
                f"{tag} is marked resolved with no evidence behind the discriminator")
        if dt == "forward_observable" and not str(d.get("review_date") or "").strip():
            warn(f"{tag}.discriminator is a forward observable with no review_date — a forward "
                 f"observable without a date cannot settle anything (§7.2)")

        if resolved is False and not ent.get("becomes_load_bearing_assumption"):
            warn(f"{tag} is unresolved but not flagged becomes_load_bearing_assumption — an "
                 f"unresolved divergence the thesis proceeds on is a disclosed assumption, "
                 f"not a silent one (§7.5)")
        if resolved is False and ent.get("materiality") == "high":
            unresolved_high += 1

    if unresolved_high:
        info(f"{unresolved_high} high-materiality divergence(s) unresolved — each must appear in "
             f"the note's load-bearing assumptions and in rating.capped_by")


# --------------------------------------------------------------------------- #
def check_records(ws: Path) -> None:
    """Fact / red-flag / open-question stores against their schemas."""
    specs = [
        ("facts", sorted((ws / "facts").glob("*.json")) if (ws / "facts").exists() else [],
         "fact_record.schema.json", "facts"),
        ("red_flags", [ws / "state" / "red_flags.json"], "red_flag.schema.json", "red_flags"),
        ("open_questions", [ws / "state" / "open_questions.json"],
         "open_question.schema.json", "open_questions"),
    ]
    for label, paths, schema_name, key in specs:
        req = schema_required(schema_name)
        for path in paths:
            data, e = load_json(path)
            if e == "missing":
                continue
            if e:
                err("E-RECORD-JSON", f"{rel(path)}: {e}")
                continue
            recs = data.get(key, data) if isinstance(data, dict) else data
            if not isinstance(recs, list):
                continue
            # Not every file under facts/ is a fact store. facts/merge_discrepancies.json is a
            # merge LOG (metric/basis/period/kept/superseded), so validating it against
            # fact_record.schema.json reports every row as broken and buries the real findings.
            # Detect by shape rather than by filename: if essentially no record carries any of
            # the schema's required fields, this file is a different artefact.
            if req and recs:
                dicts = [r for r in recs if isinstance(r, dict)]
                if dicts:
                    # "any required field" is too loose — a merge log carries `metric`, `basis`
                    # and `period`, which are fact-record fields too. Require a MAJORITY of the
                    # schema's required fields before treating a row as a record of this kind.
                    fact_like = sum(1 for r in dicts
                                    if sum(1 for k in req if k in r) >= 0.6 * len(req))
                    if fact_like / len(dicts) < 0.5:
                        info(f"{rel(path)}: not a {label} store — only {fact_like}/{len(dicts)} "
                             f"rows carry a majority of {schema_name}'s required fields. Skipped, "
                             f"not failed (a merge/diff log is a different artefact).")
                        continue
            seen: dict[str, int] = {}
            bad_fields: dict[str, int] = {}
            for i, r in enumerate(recs):
                if not isinstance(r, dict):
                    continue
                rid = r.get("id")
                if rid:
                    seen[rid] = seen.get(rid, 0) + 1
                for k in req:
                    if k not in r:
                        bad_fields[k] = bad_fields.get(k, 0) + 1
            dupes = {k: v for k, v in seen.items() if v > 1}
            if dupes:
                err("E-RECORD-DUPID",
                    f"{rel(path)}: duplicate {label} ids {sorted(dupes)[:5]} "
                    f"({len(dupes)} total) — ids are the citation anchor, so a duplicate makes "
                    f"a [S#] reference ambiguous")
            if bad_fields:
                err("E-RECORD-FIELD",
                    f"{rel(path)}: {len(recs)} {label} record(s), missing required "
                    f"fields {dict(sorted(bad_fields.items()))} (schema/{schema_name})")

    # convergence conditions from CLAUDE.md
    data, e = load_json(ws / "state" / "red_flags.json")
    if not e and data:
        recs = data.get("red_flags", data) if isinstance(data, dict) else data
        if isinstance(recs, list):
            cand = [r.get("id") for r in recs if isinstance(r, dict) and r.get("status") == "candidate"]
            if cand:
                warn(f"{len(cand)} red flag(s) still `candidate` ({cand[:5]}) — convergence "
                     f"requires the ledger have no unresolved candidates (CLAUDE.md)")

    data, e = load_json(ws / "state" / "open_questions.json")
    if not e and data:
        recs = data.get("open_questions", data) if isinstance(data, dict) else data
        if isinstance(recs, list):
            stuck = [r.get("id") for r in recs
                     if isinstance(r, dict)
                     and str(r.get("severity", "")).lower() in ("medium", "high", "critical")
                     and str(r.get("status", "")).lower() not in ("answered", "disclosed", "resolved", "closed")]
            if stuck:
                warn(f"{len(stuck)} open question(s) at severity>=medium neither answered nor "
                     f"disclosed ({stuck[:5]}) — convergence requires one or the other")


# --------------------------------------------------------------------------- #
def check_verification(ws: Path) -> None:
    """CLAUDE.md rule 6, enforced mechanically."""
    canonical = ws / "state" / "verification_report.json"
    misplaced = ws / "report" / "verification_report.json"

    path = canonical
    if not canonical.exists() and misplaced.exists():
        err("E-VERIFY-PATH",
            f"verification_report.json is at {rel(misplaced)} but rule 6 and "
            f"prompts/50 both specify {rel(canonical)}. report/ holds deliverables; "
            f"this is run state that GATES them. Move it.")
        path = misplaced
    data, e = load_json(path)
    if e == "missing":
        warn("verification_report.json absent — the citation gate (prompts/50) has not run")
        return
    if e:
        err("E-VERIFY-JSON", f"{rel(path)}: {e}")
        return

    gate = data.get("final_gate_decision")
    if gate is None:
        err("E-VERIFY-GATE",
            "verification_report.json has no `final_gate_decision`. prompts/50 requires the "
            "field by that exact name — a gate downstream code cannot find is not a gate.")
    elif gate not in ("PASS", "FAIL"):
        shown = str(gate)
        if len(shown) > 120:
            shown = shown[:120].rstrip() + f"… [{len(str(gate))} chars]"
        err("E-VERIFY-GATE-VALUE",
            f"final_gate_decision must be exactly 'PASS' or 'FAIL'; got {shown!r}. The NALCO run "
            f"put the whole verdict narrative in this field, which means no downstream check can "
            f"branch on it. Put the reasoning in `auditor_verdict.note`; keep this field a token.")

    auditor = data.get("auditor_verdict")
    override = data.get("override")

    if override:
        if not auditor:
            err("E-VERIFY-VERDICT-LOST",
                "an `override` is present but `auditor_verdict` is not. Rule 6 requires the "
                "auditor's own verdict be preserved ALONGSIDE any override — an override sits "
                "beside the verdict, never on top of it.")
        items = override.get("items") if isinstance(override, dict) else None
        if not isinstance(items, list) or not items:
            err("E-VERIFY-OVERRIDE-BLANKET",
                "`override` carries no itemised `items`. Rule 6: an override needs a justification "
                "for EACH remaining fatal item. A one-line orchestrator stamp is not an override — "
                "the NALCO run closed a 10-item FAIL to PASS that way, including the two facts a "
                "thesis pillar rested on.")
        else:
            fatal = _fatal_count(data, auditor)
            if fatal is not None and len(items) < fatal:
                err("E-VERIFY-OVERRIDE-SHORT",
                    f"`override.items` has {len(items)} justification(s) for {fatal} fatal "
                    f"item(s). One per item, itemised, or it is not an override.")
            for i, it in enumerate(items):
                if not isinstance(it, dict) or not it.get("justification"):
                    err("E-VERIFY-OVERRIDE-EMPTY",
                        f"override.items[{i}] has no `justification`")
        if gate == "PASS" and isinstance(auditor, dict) and auditor.get("final_gate_decision") == "FAIL":
            info("gate reads PASS over an auditor FAIL with an itemised override present — "
                 "permitted by rule 6, and both verdicts are on file as required")


def _fatal_count(data: dict, auditor) -> int | None:
    for src in (auditor if isinstance(auditor, dict) else {}, data):
        for k in ("fatal_items", "fatal_count", "load_bearing_failures"):
            n = src.get(k) if isinstance(src, dict) else None
            if isinstance(n, int):
                return n
            if isinstance(n, list):
                return len(n)
    return None


# --------------------------------------------------------------------------- #
def check_evidence_floors(ws: Path) -> None:
    """config.report.evidence_floors are what "do not compromise the detail" means in checkable
    terms. Under stance: evidence_first the evidence layer IS the deliverable, so a floor the run
    did not reach must be reported rather than left for a reader to notice."""
    cfg = REPO / "config" / "agent_config.yaml"
    if not cfg.exists():
        return
    try:
        import yaml
        c = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return
    rep = c.get("report") or {}
    floors = rep.get("evidence_floors") or {}
    if not floors:
        return
    info(f"report stance = {rep.get('stance', 'unset')!r}; checking "
         f"{len(floors)} evidence floor(s)")

    # statement depth
    comp, e = load_json(ws / "state" / "comprehensive_statement.json")
    want_levels = floors.get("statement_levels")
    if want_levels and not e and isinstance(comp, dict):
        def depth(node, d=1):
            ch = node.get("children") or []
            return d if not ch else max(depth(x, d + 1) for x in ch)
        for stmt in ("income_statement", "balance_sheet", "cash_flow"):
            tree = comp.get(stmt) or {}
            if not tree:
                continue
            got = max((depth(r) for r in tree.values()), default=0)
            if got < want_levels:
                warn(f"evidence floor: {stmt} reaches {got} level(s), floor is {want_levels}. "
                     f"Extraction is not recording `parent` on level-2/3 records (prompts/10).")

    # operating-KPI trend length
    kpis, e = load_json(ws / "facts" / "kpis.json")
    want_periods = floors.get("operating_kpi_periods_min")
    if want_periods and not e and isinstance(kpis, dict):
        per_metric: dict[str, set] = {}
        for f in kpis.get("facts") or []:
            if isinstance(f, dict) and f.get("metric") and f.get("period"):
                per_metric.setdefault(f["metric"], set()).add(f["period"])
        thin = [m for m, ps in per_metric.items() if len(ps) < want_periods]
        if thin:
            warn(f"evidence floor: {len(thin)} operating KPI(s) have fewer than {want_periods} "
                 f"periods ({thin[:4]}) — a per-unit snapshot is not a trend")

    # xlsx analysis tabs
    if floors.get("horizontal_vertical_analysis") == "required":
        xlsx = list((ws / "exports").glob("*_financials.xlsx")) if (ws / "exports").exists() else []
        if not xlsx:
            warn("evidence floor: no exports/*_financials.xlsx — horizontal and vertical analysis "
                 "are required deliverables (tools/export_financials_xlsx.py)")
        else:
            try:
                import zipfile, re as _re
                with zipfile.ZipFile(xlsx[0]) as z:
                    wb = z.read("xl/workbook.xml").decode("utf-8", "ignore")
                names = set(_re.findall(r'name="([^"]+)"', wb))
                missing = [n for n in ("IS_horizontal", "IS_vertical", "BS_horizontal",
                                       "BS_vertical") if n not in names]
                if missing:
                    warn(f"evidence floor: {xlsx[0].name} is missing analysis tab(s) {missing} — "
                         f"re-run tools/export_financials_xlsx.py")
            except Exception as exc:  # noqa: BLE001
                warn(f"could not inspect {xlsx[0].name}: {exc}")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("workspace", help="workspace/<TICKER>")
    ap.add_argument("--strict", action="store_true",
                    help="treat an absent artefact as an error (use on a run that claims to be "
                         "complete; the default only warns, so a mid-run workspace is checkable)")
    a = ap.parse_args()

    ws = Path(a.workspace)
    if not ws.exists():
        print(f"ERROR workspace not found: {ws}")
        sys.exit(1)

    check_triage(ws, a.strict)
    check_business_model(ws, a.strict)
    check_thesis(ws, a.strict)
    check_interpretation_ledger(ws, a.strict)
    check_records(ws)
    check_verification(ws)
    check_evidence_floors(ws)

    for m in infos:
        print(f"INFO  {m}")
    for m in warnings:
        print(f"WARN  {m}")
    for m in errors:
        print(f"ERROR {m}")

    print(f"\n{ws}: {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
