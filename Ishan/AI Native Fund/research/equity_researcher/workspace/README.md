# workspace/ — per-run state and outputs (created by the orchestrator)

```
workspace/<TICKER>/
  state/          manifest.json · triage.json · source_registry.json · assumptions.json
                  open_questions.json · red_flags.json · thesis.json · run_log.md
                  verification_report.json · citation_check.json
  facts/          fragments/ (per-doc extraction) · financials.json (merged canonical)
                  derived_metrics.json · market_data.json · quotes.json · estimates.json
                  external/ (dr1_*.json, dr2_*.json)
  findings/       fundamental.json · forensic.json · guidance.json · governance.json
                  valuation_moat.json
  research/       dr1_report.md · dr2_report.md
  report/         dossier.md · final_note.md
  handoff/        valuation_handoff.json
  cache/          <hash>.done wave markers (resumability)
```

Safe to delete a company folder to fully reset its run. `state/run_log.md` is the audit of *how* the run unfolded — which wave ran when, triggered by what, and what it changed.

## Fund integration

This folder is populated by runs kicked off from the fund side (see the
"Fund integration" section in `../CLAUDE.md`) and read back by
`src/afund/research/er_adapter.py` in the parent fund repo. Nothing here
is checked into fund source control by convention — it's per-run scratch
output, same as before the fund integration existed.
