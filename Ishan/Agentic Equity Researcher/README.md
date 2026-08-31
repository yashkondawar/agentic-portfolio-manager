# Agentic Equity Researcher (v1)

A sell-side equity research agent for India-listed companies, built to run **natively in Claude Code**: open this folder in Claude Code and the orchestrator playbook (`CLAUDE.md`) takes over. It produces an initiation-style research note (≤12 pages), a full audit dossier, and a machine-readable handoff for a downstream valuation/sensitivity agent (PE re-rate/de-rate/constant → target price — future iteration).

## Quickstart (native mode — default)

1. Drop company documents into `input/<TICKER>/` (see `input/README.md` for the ideal set and naming).
2. Open Claude Code in this folder and say: **"Initiate coverage on `<TICKER>` (`TICKER.NS`)"** — include the yfinance symbol so market data resolves.
3. The orchestrator runs intake → triage → parallel extraction → deterministic ratios → analysis waves → deep research loops → estimates → verification → report. Progress and every scheduling decision land in `workspace/<TICKER>/state/run_log.md`.
4. Outputs in `workspace/<TICKER>/`:
   - `report/final_note.md` — the ≤12-page note (rating once, at top)
   - `report/dossier.md` — long-form audit document with global source legend
   - `handoff/valuation_handoff.json` — contract for the next agent (see `templates/valuation_handoff.example.json`)

You can steer mid-run like a real desk head: "dig deeper into the capex plan", "add peer X", "re-check receivables" — the circular protocol absorbs new work and updates dependent findings rather than restarting.

## What it does (and deliberately doesn't)

- **Does**: two-tier financial extraction with page-level audit trail; deterministic ratio/flag computation; forensic earnings-quality review; management-guidance credibility scoring; governance/promoter checks (India-specific); web deep research (company DR1 + sector/peers DR2 with sector KPI packs); drivers-based FY+1/FY+2 estimates; forward-PE positioning; adversarial citation verification.
- **Doesn't (v1, by design)**: DCF/WACC, ESG section (config toggles for later); formal target price (that's the downstream agent's job — this agent ships the scenario seeds and PE bands it needs); chart images (tables only in v1).

## The circular part

This is not a linear pipeline. State lives in a shared dossier (`facts/`, `findings/`, `state/`); every finding declares what it depends on; new information (a research answer, a restatement, a contradiction) marks dependent findings stale, and **only those** re-run. Order varies per company via rule-based triage (`prompts/02`) — a pure-play launches sector research immediately in parallel; a multi-segment story extracts financials first, then branches research per segment. The *reason* for every ordering decision is logged. Full protocol: `prompts/01_orchestration_protocol.md`.

## Repo map

```
CLAUDE.md                 orchestrator playbook (the agent's brain in native mode)
config/sector_registry.yaml  THE single source of truth for sector routing: 8 families ->
                          32 playbooks -> keywords -> signature KPIs -> unit denominator
config/agent_config.yaml  rating scale, page budget, thresholds, model tiers, loops
config/eps_bridge_thresholds.yaml  buy-side EPS-bridge rules + per-sector overrides
prompts/                  21 module prompts, 00-70 (single source of truth for subagents)
prompts/sector_packs/     8 tier-1 routing families. THIN ROUTERS — family scope, the
                          statement fork, cross-cutting lenses, child index. No KPI tables.
                          (Slugs are not listed here on purpose: the registry owns that list,
                          and a hardcoded copy in this file is exactly the drift the registry
                          was created to end.)
prompts/sector_playbooks/ 32 tier-2 sub-sector playbooks — economic engine, ordered analysis
                          sequence, signature KPIs with formula/unit/benchmark/source,
                          standard exhibit set, valuation convention + traps, forensic
                          screens, dependencies, archetypes. All `status: authored`.
prompts/thesis_archetypes/ 15 files: the archetype library + README, each with must-be-true
                          conditions, standard failure mode, falsifiers, skepticism weight
.claude/agents/           14 subagents (haiku extraction / sonnet analysis / sonnet thesis /
                          opus adversarial / opus writing)
.claude/skills/           equity-research-formatter (FORMAT stage; scripts/ is reference-only)
schema/                   6 schemas: fact record, open question, red flag, triage, thesis,
                          valuation handoff
tools/                    13 deterministic Python entry points. Start with preflight.py
                          (runs every static check) and validate_state.py (a run's state vs
                          the schemas); plus market_data, convert_docs, merge_facts,
                          compute_ratios, compute_kpis, build_comprehensive_statement,
                          eps_bridge_check, export_financials_xlsx, render_tables,
                          citation_check, validate_sector_registry
tools/er_corpus/          corpus toolchain: discover -> fetch -> convert -> profile -> digest
tools/report_formatter/   Node/docx-js engine for the FORMAT stage (step 9)
tools/disclosure_fetcher/ step 0 FETCH: BSE + Screener, key-free
templates/                final note, dossier, disclaimer, handoff example
input/<TICKER>/           your documents go here
workspace/<TICKER>/       run state + outputs (created per run) — see workspace/README.md
reference/er_corpus/      the 165-note broker corpus: pdf, md, digest, profile, seeds
api_mode/                 optional API/SDK runner. A documented scaffold, NOT parity —
                          waves 6a/6b (thesis + red team) are unimplemented there
docs/                     6 documents: ER_CORPUS_FINDINGS (what 165 real initiation notes
                          do), OPINION_VS_ANALYSIS (the 15-check audit), BROKER_CALIBRATION,
                          PROCESS_V2_REIMAGINED (superseded in part), DESIGN_DECISIONS,
                          SOP_ORCHESTRATOR_RUNS
```

Verify the map rather than trusting it: `python tools/preflight.py` checks the registry, the
schemas, the configs, every backticked path reference in the markdown, and that the two copies
of `reportStyle.js` are byte-identical.

## Requirements

Python 3.10+ and the key-free dependency set:

```bash
python -m pip install -r tools/requirements.txt
python tools/preflight.py --deps-only
```

Nothing in that set needs an API key — the whole default pipeline, the BSE/Screener fetch and the
corpus toolchain run on it. The Gemini/Tavily web-search fallback is opt-in and lives in
`tools/disclosure_fetcher/requirements.txt`; do not merge it into the key-free set. Node is needed
only for the FORMAT stage (`tools/report_formatter/`, which carries its own `package.json`).

Web access for deep research degrades gracefully to document-only with disclosed gaps.

## Iteration-1 limits & next steps

No consensus-estimates feed, so the variant view is vs. guidance; charts are markdown tables.
The `.docx` FORMAT stage now exists (step 9, `tools/report_formatter/`). The benchmark harness —
comparing our output against a real initiation note — is now largely served by
`docs/ER_CORPUS_FINDINGS.md`, which measures 165 real notes instead of one.

Known open items, honestly: peer *multiples* remain the most-requested-and-most-missed output
(the NALCO run's largest disclosed gap, still open); `api_mode/` does not implement waves 6a/6b;
and per-unit economics depend on extraction naming volumes consistently across years — see the
`extraction_feedback` block in a run's `state/business_model.json`. See
`docs/DESIGN_DECISIONS.md` §Roadmap.
