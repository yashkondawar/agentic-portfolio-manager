# Orchestration Protocol — circular scheduling over a shared dossier

The run is **goal-seeking, not a fixed pipeline**. The orchestrator repeatedly asks: *"given the current dossier state, what work has the highest information value right now?"* — and dispatches that as the next wave. Some waves run in parallel, some in series; the same module can run more than once. What makes this auditable rather than arbitrary is that every dispatch is logged with its trigger.

## 1. Shared state (the dossier) — `workspace/<TICKER>/state/`

| File | Contents | Written by |
|---|---|---|
| `manifest.json` | every input file: kind (AR/quarterly/transcript/presentation/deep_research/peer/kpi/other), fiscal period, basis available (standalone/consolidated), pages | intake |
| `triage.json` | branch decisions + the rule that fired + reason (prompts/02) | triage |
| `source_registry.json` | global SRC map (see citation standard) | all modules (append) |
| `assumptions.json` | assumption ledger | any module |
| `open_questions.json` | gap ledger — see schema | all modules (append), deep-researcher (answers) |
| `red_flags.json` | **shared** red-flag ledger — see schema. Single source of truth; no module keeps a private flag list | compute_ratios (candidates), forensic (confirm/dismiss), all (append) |
| `state/business_model.json` | value chain · margin pool · net long/short · KPI tree · unit economics · swing drivers · DR2 research seeds (step 1.5 — the analytical spine) | module 03 (business-model mapping) |
| `kpi_trends.md` + `facts/kpis.json` | operating-KPI trends, per-unit economics, segment analytics, signature-KPI coverage report | `tools/compute_kpis.py` (step 3, zero tokens) |
| `thesis.json` | archetype, return decomposition, pillars with evidence, must-be-true checklist, monitorables with thresholds, variant view, rating derivation — schema: `schema/thesis.schema.json` | **module 33 (thesis-synthesizer)** — and *only* module 33. It also writes the `redteam` block back on its post-red-team pass. |
| `findings/thesis_redteam.json` | the 15-check opinion/analysis audit, banned-reasoning hits, archetype failure-mode attack, steel-manned opposite rating, pre-mortem, verdict | module 34 (thesis-redteam), in a separate context |
| `verification_report.json` | per-item citation verdicts, failure clusters, fix list, `final_gate_decision` | citation-auditor (prompts/50) |
| `comprehensive_statement.json` / `.md` | 3-level line-item tree (IS/BS/CF) × all fiscal years + available quarters, fact_ids per node — the authoritative multi-period view; `.md` is the rendered indented table | tools/build_comprehensive_statement.py (step 3 COMPUTE) |
| `eps_bridge_check.json` | EPS-bridge doctrine (prompts/60_buy_side.md) PASS/FAIL/NA + numbers per rule_id, computed from comprehensive_statement.json's merged facts | tools/eps_bridge_check.py (step 3 COMPUTE, after comprehensive_statement.json exists) |
| `run_log.md` | one entry per wave: trigger → inputs → outputs → state deltas | orchestrator |

Facts live in `facts/` (financials.json, market_data.json, quotes.json, external/*.json, derived_metrics.json, estimates.json). Findings live in `findings/<module>.json`.

## 0. Pre-wave: CONVERT (step 0.5, deterministic, zero tokens)

Before dispatch, run `tools/convert_docs.py <TICKER>` once per run (idempotent —
skips documents whose cache is newer than the source PDF). This produces
`workspace/<TICKER>/cache/markdown/<docid>.md` (page-anchored markdown) and
`workspace/<TICKER>/cache/tables/<docid>_p<N>_t<K>.json` (per-page table
extraction) for every PDF in `input/<TICKER>/`. Extraction dispatches (wave 2)
pass the cache paths to doc-extractor/narrative-extractor alongside the
original PDF path — the cache is a reading aid, not a replacement source; the
original PDF remains the citation-grounding artifact for the verification wave.

## 2. Dependency & staleness (the circularity engine)

- Every finding record carries `depends_on: [fact ids, question ids]`.
- When a fact changes (new research answer, restatement, merge conflict resolution) or a question is answered, the orchestrator marks dependent findings `stale` and schedules **only** the owning modules to re-run. The re-run prompt includes a "what changed" diff so the module updates rather than regenerates.
- New external facts always carry `impacts: [module names]` (the deep-researcher must fill this).
- Contradictions (e.g., management claim vs computed number, web fact vs filing) become open questions with `severity: high` and route to forensic or deep research — whichever owns the evidence type.

This is how "deep research done later circles back to the start": the research answer invalidates precisely the findings built on the old gap, those modules re-run with the new fact, and the thesis/synthesis layer picks up the updated findings on the next pass. Nothing else repeats.

## 3. Scheduling rules

Priority order when choosing the next wave:
1. **Unblock the thesis** — any pillar with < `evidence_min_per_thesis_pillar` refs.
2. **High-severity open questions** — batch them per destination (research vs forensic vs extraction).
3. **Staleness repairs** — findings marked stale.
4. **Standard progression** — the phase ordering in CLAUDE.md when nothing above applies.

Parallelism: per-document extraction is always parallel. Analysis modules (fundamental / forensic / guidance / governance) run parallel after facts merge. Deep research runs **in parallel with analysis** when triage already produced researchable questions (pure-play case), otherwise after the first analysis wave. Estimates-builder needs guidance findings + peer data. Report-writer is last; verification runs on its draft and can send it back once.

### 3a. The thesis waves (6a / 6b) — strictly serial, and gated

These two cannot be parallelised with each other or folded into another wave, because the
whole point is that a different context attacks the conclusion.

```
6  SYNTHESIZE   peer-valuation (23) + estimates (32)        [parallel]
6a THESIS       thesis-synthesizer (prompts/33)             [serial, after 6]
                → state/thesis.json. Return decomposition FIRST, then archetype, then
                  the archetype's must-be-true checklist, then the rating bottom-up.
6b REDTEAM      thesis-redteam (prompts/34)                 [serial, after 6a, FRESH CONTEXT]
                → findings/thesis_redteam.json
   ↺            verdict `not_established` → back to 6a. At least one 6a→6b→6a round trip
                  is mandatory (`config.thesis.redteam_min_rounds`), never skipped, even
                  when the first verdict is `survives`.
```

**Render gate.** `config.thesis.redteam_required: true` means step 8 RENDER may not start
until `findings/thesis_redteam.json` exists, its verdict is not `not_established`, and every
`high`-severity material challenge is either answered in the note or recorded as a disclosed
gap. `config.thesis.require_disconfirming_exhibit: true` means the note must name at least
one exhibit that cuts against its own thesis (audit check #10). These config keys existed
before this section and gated nothing — this is where they bind.

**Scheduling priority 1 restated.** "Unblock the thesis" (§3 below) now has a concrete
target: a pillar with fewer than `evidence_min_per_thesis_pillar` refs, *or* a
`must_be_true` condition sitting at `unestablished` that further extraction or research
could plausibly establish. A majority of `unestablished` conditions does not become a weaker
rating — per `prompts/33` step 4 the archetype is **rejected** and the thesis falls back to
the earnings case with the multiple held flat.

Series constraint: `compute_ratios.py` AND `tools/build_comprehensive_statement.py` run only after `merge_facts.py` (both read the merged facts store; order between the two doesn't matter, both are zero-token); `tools/eps_bridge_check.py` AND `tools/export_financials_xlsx.py` run only after `tools/build_comprehensive_statement.py` has written `state/comprehensive_statement.json` (order between those two doesn't matter either, both are zero-token, both no fund imports); estimates only after guidance + market data; render only after synthesis.

## 4. Convergence & budgets

Stop the research loop when ALL hold:
- every thesis pillar has ≥ 2 independent evidence refs (different source documents);
- no open question with severity ≥ medium is unanswered — or it is moved to `status: disclosed` and will appear in the note's "Data gaps & monitorables";
- no red-flag ledger entry remains `status: candidate` (each is `confirmed`, `dismissed`, or `disclosed`);
- OR `research_loops_max` reached → move remaining items to `disclosed` and proceed.

Token discipline: extraction and deterministic tools are effectively free — prefer another extraction pass (deeper notes, more pages) over another synthesis pass. A third+ research layer is allowed only via scripts/extraction, not via new LLM research synthesis, unless the user raises the budget.

## 5. Failure isolation & resumability

- Subagents write outputs to files **before** returning; the orchestrator treats the file as the artifact and the return message as a summary.
- Cache: before dispatching a wave, hash (prompt file version + input file list). If `cache/<hash>.done` exists and inputs are unchanged, skip. After success, write the marker.
- A failing subagent → log the error in `run_log.md`, retry once with the error appended; if it fails again, continue the run with that module's output marked `N/A — module failed` and surface it in the gaps section. One broken module never kills a run.

## 6. Worked example of circularity (illustrative)

1. Triage: 3 segments, mix shifted 9pp YoY → financials-first branch. Sector research deferred; reason logged.
2. Extraction + compute → DSO up 31% YoY → auto red-flag candidate RF-03.
3. Forensic confirms RF-03 is unexplained by disclosures → opens Q-07 *"Is rising DSO industry-wide or company-specific?"* (severity high, impacts: forensic, peer-valuation).
4. Deep research (DR2 wave) answers Q-07: peer median DSO up only 4%; adds external facts with `impacts: [forensic-auditor, peer-valuation-analyst]`.
5. Orchestrator marks forensic finding F-12 and the peer table stale → re-runs those two only. Forensic upgrades RF-03 severity; thesis pillar "working-capital discipline" flips to a risk.
6. Estimates-builder (already run) depends on receivables assumptions → marked stale → re-runs with higher WC drag. Handoff JSON regenerated.
7. Report renders once, at the end, from the final state — the note reflects step 6, not step 2.
