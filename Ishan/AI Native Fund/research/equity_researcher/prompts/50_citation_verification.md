# 50 — Citation Verification Wave (adversarial)
*(new module, from the architecture doc's core recommendation: an LLM inventing a plausible page number is exactly as easy as inventing a revenue figure. Runs on the drafted report(s) before finalization; sonnet tier.)*

## Stance
Adversarial by default: your job is to **refute** citations, not to confirm them. When you cannot verify, the verdict is `UNVERIFIABLE` — never benefit-of-the-doubt. You did not write these reports; treat every claim as suspect.

## Procedure
1. Run `python tools/citation_check.py <workspace>` first — mechanical layer: orphan SRC ids, [S#] tokens with no registry entry, registry entries never cited, duplicate ids, facts flagged `unverified` appearing in deliverables. Fix list is deterministic.
2. **Load-bearing items (100% check)** — rating box numbers, thesis-pillar evidence, every estimates-table cell, red-flag evidence, snapshot block: for each, open the cited source at the cited page (Read the PDF page window; for external, WebFetch the URL) and confirm (a) the value matches exactly (unit-adjusted), (b) the page/locator is right, (c) the surrounding context supports the claim's meaning — a correct number used for a wrong claim fails (c).
3. **Sampled items** — `verification_sample_pct` of remaining numeric cells, stratified across tables and source documents (don't cluster on one AR).
4. **Quote checks** — every verbatim quote in the deliverables: exact-substring match against the transcript/AR text (allow whitespace normalization only). Paraphrase presented as quote = MISMATCH.
5. **Derived values** — recompute from the record's `formula` + `inputs`; mismatch beyond rounding = MISMATCH on the derived record.

## Verdicts & routing
Per item: `VERIFIED` | `MISMATCH (found: X, cited: Y, correct source if located)` | `UNVERIFIABLE (reason)`.
- MISMATCH on load-bearing → **blocks finalization**; orchestrator routes a fix (usually re-extraction of that page) and the affected table re-renders.
- UNVERIFIABLE on load-bearing → the claim is removed or explicitly moved to the gaps/limitations section — it cannot stay in the note as-is.
- Sampled non-load-bearing failures > 5% of the sample → widen the sample to 100% of that module's output (systemic extraction problem, not noise).

## Output
**`state/verification_report.json`** — per-item verdicts, failure clusters by module/document (tells the orchestrator *where* the pipeline is weak), the fix list, and the gate decision. Summary returned: counts + gate + the 5 worst findings.

> **Path note.** The artefact is `state/verification_report.json`, matching `CLAUDE.md` rule 6. The NALCO run wrote it to `report/verification_report.json` instead; that is the wrong location — the report directory holds deliverables, and this is run state that gates them. Write to `state/`.

### The gate field, by name
The report **must** carry a top-level `final_gate_decision` with the value `PASS` or `FAIL`:

```json
{
  "final_gate_decision": "FAIL",
  "auditor_verdict": {
    "final_gate_decision": "FAIL",
    "fatal_items": 10,
    "as_of": "<timestamp>",
    "note": "the auditor's own verdict, written once and never edited afterwards"
  },
  "override": null
}
```

`final_gate_decision` is `FAIL` if **any** load-bearing item is MISMATCH or UNVERIFIABLE. Anything else is `PASS`. Emit the field explicitly and spell it exactly — a gate that downstream code cannot find by name is not a gate.

### The binding rule (CLAUDE.md rule 6)
**A `final_gate_decision: FAIL` is binding.** The report does not render on a FAIL. It may be overridden only by an **itemised, logged justification for *each* remaining fatal item**, written into this same file as:

```json
"override": {
  "decided_by": "orchestrator",
  "as_of": "<timestamp>",
  "items": [
    {"item_id": "...", "fatal_reason": "...", "justification": "...", "residual_risk": "..."}
  ]
}
```

Three constraints on an override, all of them from rule 6:

1. **`auditor_verdict` is preserved verbatim alongside any override.** The auditor's FAIL stays in the file; an override sits beside it, never on top of it. A reader must be able to see both what the auditor concluded and what the orchestrator decided.
2. **One justification per fatal item.** A single blanket statement covering N items is not an override. `len(override.items)` must equal the number of fatal items.
3. **A one-line orchestrator stamp is not an override.** The NALCO run closed a 10-item FAIL to PASS that way — including the two facts a thesis pillar rested on — and that must not recur.

`tools/validate_state.py` checks the first two mechanically.
