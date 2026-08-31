# workspace/ — per-run state and outputs (created by the orchestrator)

```
workspace/<TICKER>/
  state/          manifest.json · triage.json · business_model.json · source_registry.json
                  assumptions.json · open_questions.json · red_flags.json
                  comprehensive_statement.{json,md} · eps_bridge_check.json
                  kpi_trends.md · thesis.json · verification_report.json
                  citation_check.json · run_log.md
  facts/          fragments/ (per-doc extraction) · financials.json (merged canonical)
                  derived_metrics.json · market_data.json · kpis.json · estimates.json
                  merge_discrepancies.json · quotes/ · external/ (dr1_*.json, dr2_*.json)
  findings/       fundamental.json · forensic.json · guidance.json · governance.json
                  peer_valuation.json · estimates.json · thesis_redteam.json
                  *_questions.json (per-module open questions)
  research/       dr1_company.md · dr2_sector_peers.md · dr*_open.json
  report/         dossier.md · final_note.md · buy_side_note.md (if that stage ran)
                  formatted/*.content.js · <TICKER>_{ER,Forensic,BuySide}.docx
  exports/        <TICKER>_financials.xlsx
  cache/          markdown/ · tables/ (step 0.5 CONVERT output) · <hash>.done wave markers
  handoff/        valuation_handoff.json
```

## Who owns what

Ownership matters because two modules writing one file is how a thesis ends up with no owner.

| Artefact | Written by | Note |
|---|---|---|
| `state/triage.json` | prompts/02 | The `sector` block is machine-read by four downstream consumers, so it must carry the family **and** playbook slugs — not prose. |
| `state/business_model.json` | prompts/03 (wave 1.5) | The analytical spine. Written **early**, before deep extraction, so it can steer extraction depth. |
| `facts/kpis.json`, `state/kpi_trends.md` | tools/compute_kpis.py | Zero tokens. Reads the `kpi_tree`; without it, per-unit economics become named skips instead of numbers. |
| `state/thesis.json` | **prompts/33 only** | Including the `redteam` block, which 33 writes on its mandatory post-red-team pass (step 7b). Module 34 must not touch this file. |
| `findings/thesis_redteam.json` | **prompts/34 only** | Runs in a separate context. It attacks the thesis; it does not edit it. |
| `state/verification_report.json` | prompts/50 | In `state/`, **not** `report/` — it is run state that *gates* the deliverables. Carries `final_gate_decision` as a bare `PASS`/`FAIL` token. |
| `report/*` | prompts/40, 41 | Deliverables. Nothing here gates anything. |

## Validate a run

```bash
python tools/validate_state.py workspace/<TICKER>
```

It checks `thesis.json`, `business_model.json` and `triage.json` against `schema/*.json`, the
fact/red-flag/open-question stores against their record schemas, and CLAUDE.md rule 6's
binding-gate and itemised-override rules on the verification report. It exists because
`workspace/NALCO/state/thesis.json` was once missing **6 of its 9 required fields** and nothing
noticed — the schemas were being read by humans only. `python tools/preflight.py workspace/<TICKER>`
runs it alongside the repo-level checks.

Warnings are not failures. An open question at severity ≥ medium that is neither answered nor
disclosed is a real convergence gap in that run, not a defect in the tooling, so it warns.

## Resetting

Safe to delete a company folder to fully reset its run. `state/run_log.md` is the audit of *how*
the run unfolded — which wave ran when, triggered by what, and what it changed. Deleting the
`cache/*.done` markers alone re-runs the waves while keeping the converted documents in
`cache/markdown/` and `cache/tables/`, which is usually what you want: conversion is the
expensive-but-deterministic part.

## `workspace/NALCO/` is a worked example, not a clean run

It is the repo's only executed run, and it is kept deliberately *including its defects*, because
several of them are precisely what the validators were built to catch:

- `state/verification_report.json` reads `final_gate_decision: FAIL` with **no override**, so per
  rule 6 the report does not pass the citation gate. The auditor's full narrative is preserved in
  `auditor_verdict.note`.
- 16 open questions at severity ≥ medium are unresolved, so the run has not converged.
- Per-unit economics resolve for **FY2022 only**, because extraction named production volumes three
  different ways across years. The fix is recorded in `business_model.json`'s `extraction_feedback`.
- FY2023 is absent from the segment-margin series: it carries segment revenue but no segment
  result. `compute_kpis.py` now emits a named skip for that rather than dropping the year silently.
- The ticker is `NATIONALUM.NS`. An earlier `thesis.json` said `NALCO`, which yfinance 404s —
  `tools/market_data.py` exits 2 on it rather than failing quietly.
- Two of five signature KPIs for the resolved playbook (`cost_of_production_per_tonne_inr`,
  `captive_rm_pct`) are uncomputable from what was extracted, and the thesis says so rather than
  asserting the cost-curve claim they would have supported.
