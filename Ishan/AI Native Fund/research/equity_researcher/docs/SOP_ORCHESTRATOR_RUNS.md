# SOP — Orchestrating an ER run (notes for the next orchestrator model)

Living document, started during the NALCO trial run (2026-07-15). Accumulates operational
lessons the playbook (CLAUDE.md) and protocol (prompts/01) don't spell out. Final version
consolidated at end of run; sections marked (draft) are being updated as the run progresses.

## 1. Persist every intermediate artifact (user directive — non-negotiable)

All intermediate outputs live as files under `workspace/<TICKER>/`, referable by any later
model without re-reading PDFs:

- `cache/markdown/<docid>.md` — page-anchored markitdown conversion (from convert_docs.py)
- `cache/tables/<docid>_p<N>_t<K>.json` — pdfplumber per-page tables
- `facts/fragments/facts_<docid>.json` — fact records per document (extractors)
- `facts/quotes/quotes_<docid>.json`, `guidance_<docid>.json` — narrative records
- `state/registry_fragments/<docid>.json` — per-doc SRC registries, merged after the wave
- `facts/financials.json`, `state/source_registry.json` — merged canonical stores
- `state/comprehensive_statement.{json,md}`, `facts/derived_metrics.json` — computed layer

Rules: dispatch prompts always name explicit output paths; agents write files BEFORE
returning summaries; never delete the conversion cache between waves (it is idempotent);
summaries in return messages are for scheduling only — the file is the artifact.

## 2. Environment gotchas (Windows, this machine)

- Run `pip install -r tools/requirements.txt` before the first CONVERT of a fresh clone —
  markitdown/pdfplumber were missing and the first convert run died.
- Any Python that prints PDF/registry text to console needs
  `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` — cp1252 crashes on
  Devanagari/Odia glyphs in Indian filings.
- PowerShell mangles quotes in `python -c "..."` one-liners — write scratchpad .py files.
- PowerShell 5.1 `ConvertFrom-Json` is stricter/quirkier than Python's json — validate JSON
  artifacts with Python.

## 3. Haiku extractor failure modes seen (add to dispatch prompts)

- Writes `"page": 3-4` (bare range) → invalid JSON. Dispatch prompts must say:
  "page = single integer; no trailing commas." A regex patch
  (`("page"\s*:\s*)(\d+\s*-\s*\d+)` → quote it) repairs existing files deterministically.
- Writes registry LAST → an interrupted agent leaves quotes/facts with orphaned src_ids.
  Prefer instructing: write registry entries incrementally alongside records.
- Return-message record counts can disagree with what's on disk (one agent claimed 30
  registry entries, file had 6). Never trust the summary — validate files (JSON-parse +
  orphan check) before merging.

## 4. Session-limit resilience (learned the hard way)

A 13-agent parallel wave hit the Claude session token cap mid-flight; 11 agents died.
Because every agent wrote to its own fragment file, recovery = disk inventory → keep valid
files → re-dispatch only the missing/partial documents (10 of 13 needed some redo, but 3
were fully salvaged and 4 more needed only small repair/completion tasks, not full re-runs).
Standing procedure after ANY extraction wave:
1. `Get-ChildItem` the three output dirs; JSON-validate every file (Python).
2. Cross-check src_ids referenced in facts/quotes vs registry fragments (orphan scan).
3. Re-dispatch per-document redo/repair agents only for gaps. Never restart the wave.

## 5. Wave order that worked (NALCO)

0. Classify opaque input PDFs deterministically (pypdf first-page + keyword scan; zero LLM
   tokens) → rename into input/<TICKER>/ convention. LLM never reads raw PDFs for intake.
0.5 CONVERT in background while triage/state files are written.
1. TRIAGE rules from prompts/02; log every decision + reason in state/triage.json.
2. EXTRACT: one haiku agent per document, parallel, reserved SRC-id blocks per document
   (e.g. AR_FY2025 = SRC-500..599) so parallel writes can't collide.
3. Deterministic validation + merge (registry first, then merge_facts.py) — see §4.
4. Deterministic close-out: registry merge (preserve analyst-appended SRC-1000+ entries when
   rebuilding from fragments!) → merge_facts.py → compute_ratios → build_comprehensive_statement
   → eps_bridge_check + export_financials_xlsx. Append merge value-conflicts to red_flags.json
   as data_quality candidates (forensic adjudicates them).
5. ANALYZE: 4 sonnet analysts + DR1 in ONE parallel wave (5 agents). Each writes findings +
   its own question fragment (never a shared questions file — write collisions). Forensic owns
   red_flags.json exclusively during its run.
6. Consolidate questions → state/open_questions.json → route in ONE wave: DR2 (sector/peers,
   once), DR1-B follow-up (targeted checks, ≤15 searches), extraction-answers pass (haiku, one
   agent, all doc-answerable questions batched). Staleness: send updates to EXISTING agents via
   SendMessage (context retained, much cheaper than fresh spawns) — worked for forensic
   (RF-GUI adjudication) and governance (score re-derivation after new external facts).
7. SYNTHESIZE: peer-valuation + estimates in parallel. Then the two thesis waves, serial:
   **6a** `thesis-synthesizer` (prompts/33) owns `state/thesis.json` — return decomposition
   first, then archetype from `prompts/thesis_archetypes/`, then that archetype's
   must-be-true checklist, then the rating bottom-up with "not-X-because" both directions.
   **6b** `thesis-redteam` (prompts/34) attacks it **from a fresh context** — never a second
   pass by the author. At least one 6a→6b→6a round trip is mandatory, and RENDER is gated on
   the verdict (see prompts/01 §3a). The orchestrator writes neither file.
   *(Superseded: this step used to read "one sonnet thesis-assembly agent" with no module
   number, no archetype and no adversarial pass. That was the improvised convention the
   NALCO run followed.)*
8. RENDER (opus) → VERIFY (citation-auditor) → fix loop. Budget ~2 fix rounds: round 1
   report-writer content fixes; round 2 is almost always mechanical schema drift — fix
   DETERMINISTICALLY (scripts), don't re-spawn the auditor for one token; close the gate with a
   script that checks every [S###] resolves.

## 6. Recurring integrity defects (check for ALL of these after every wave)

- SRC-range overflow: agents legitimately need more ids than reserved. Reserve ≥100/document.
  Overflows collide silently — validate before merge, renumber with +1000 offsets.
- "Summary ≠ disk": agents report entries/records they never wrote, and write files they
  don't mention. Only the validation script's counts are real.
- Schema drift zoo (all seen once): object-wrapped arrays; `source_ids` list vs
  `source.src_id`; `sources: [..]`; registry entries embedded in fact files under
  `source_registry_additions`; missing `load_bearing`; bare `"page": 3-4`; unclosed source
  brace; finding-id citation tokens ([F-EXT-…], [EST-…]) in report prose instead of [S###].
  The merge/validate scripts in scratchpad handled every one deterministically — port them
  into tools/ as validate_fragments.py for future runs (TODO).
- Estimates records need their own SRC ids (doc: "computed") or the estimates exhibit is
  citation-orphaned at verification.

## 7. Deep research: two monolithic passes vs. smaller interleaved searches (decision rule)

What this run showed:
- DR1 (company) as ONE bounded pass (≤20 searches) alongside the analysis wave worked — its
  facts (Pottangi opposition, lease-date conflict) were ready exactly when analysts produced
  the questions that needed them.
- DR2 (sector/peers) as ONE bounded pass AFTER analysis worked — by then the open-questions
  ledger told it precisely what to answer (price-outlook cross-check, cost-curve claim, peer
  set), so nothing was researched "just in case."
- The highest-value research tokens were the SMALL follow-ups: DR1-B (≤15 searches, 8 precise
  questions) found the two governance items (LODR fine, CBI probe) that changed the verdict,
  and a single orchestrator WebSearch closed the promoter-holding verification in one query.
Rule of thumb: keep TWO bounded deep passes as the skeleton (DR1 with analysis; DR2 after
extraction confirms segments) + budget one targeted follow-up wave driven by the question
ledger + allow single-query orchestrator searches for rating-box-adjacent verifications.
Never run an unbounded "research everything" pass; never re-research what input docs already
contain (classify DR docs at intake). Small searches beat a third deep pass every time.

## 8. Token budget observed (NALCO, for planning)

Extraction ~1.1M subagent tokens (13 docs, incl. one full redo wave from a session-limit
wipeout — halve this with ≤6-agent waves and incremental writes), analysis+research ~0.8M,
synthesis+render+verify ~1.1M (opus render 253k+278k was the single largest item; the
verification fix loop re-invoked it once — tightening extraction schema conformance up front
is the cheapest way to shrink the render/verify loop). Orchestrator overhead is dominated by
subagent return messages: enforce "return ≤10 lines" in EVERY dispatch prompt.

## 9. FORMAT stage (step 9) — styled .docx from the markdown notes

Added 2026-07-19. After the citation gate PASSes, the `equity-research-formatter` skill
(`.claude/skills/equity-research-formatter/`) renders each note to an institutional-look
`.docx`. Split of labour, same as every other stage:
- **Judgment (LLM, report-writer/opus):** read each note, classify archetype
  (final_note=ER, dossier=forensic, buy_side_note=buy-side), extract into a content module at
  `workspace/<TICKER>/report/formatted/<name>.content.js`. Build from the run's OWN numbers,
  not the skill's shipped NALCO examples (those are structural reference only). Keep fact-IDs
  on forensic/buy-side; strip them on ER; preserve disclaimers verbatim; introduce no new
  claims; condense low-signal blocks but say what was condensed.
- **Deterministic (zero tokens, orchestrator):** `node tools/report_formatter/build_reports.js
  <TICKER>` → one `.docx` per module into `report/`. Engine + local `docx` dep already
  installed; never re-`npm install` per run.

## 10. The v2 analytical spine (business model → KPIs → unit economics)

Added 2026-07-19 after benchmarking our NALCO output against a professional initiation note.
Full rationale in `docs/PROCESS_V2_REIMAGINED.md`; operating rules here.

**The one change that matters most:** run the **business-model & value-chain map (prompts/03)
EARLY** — right after triage, before the analysis wave — not late in research. It emits
`state/business_model.json`: the value-chain map (each node own/buy/sell-into), the
company-specific **KPI tree** (the 8–15 metrics that actually drive THIS business, tagged
driver/health/moat, each naming its input facts), the **unit-economics** definitions, the
**net-long/short** framing, the **swing drivers**, and the **DR2 research seeds**. Everything
downstream reads it: extraction prioritises the KPI-tree inputs, `compute_kpis.py` builds the
trends, DR2 answers the seeds, module 20 interprets the KPIs, module 32 builds the sensitivity,
the report carries the exhibits. It is one cheap sonnet pass and it is the difference between a
filing summary and a business analysis.

**COMPUTE now has a fourth zero-token tool:** `tools/compute_kpis.py`
```
python tools/compute_kpis.py workspace/<T>/facts/financials.json \
    --out workspace/<T>/facts/kpis.json --out-md workspace/<T>/state/kpi_trends.md \
    --business-model workspace/<T>/state/business_model.json --ticker <T>
```
It joins operating volumes to segment financials for per-unit economics + segment analytics.
Two paths: (a) *business-model-driven* — computes each KPI-tree entry from its named,
unit-matched inputs (reliable; use this); (b) *keyword fallback* when the map is absent —
sanity-bounded segment margins/contribution only, and it **deliberately refuses** to guess
per-unit economics (realization/tonne, EBIT/tonne, utilization) because unit mismatches
(₹cr vs '000t vs MTPA) produce garbage — it records those as skips that seed extraction-deeper.
Verified on NALCO: fallback gave clean segment-mix trends (alumina EBIT share 26%→45%,
aluminium 74%→55% — the "net-long-alumina" signal) and correctly deferred unit economics.
Lesson baked into the tool: **a fallback that emits garbage is worse than one that emits a
labelled gap** — sanity-bound every fuzzy-matched KPI, and defer the rest to the map.

**Sparse-data runs** (triage `data_mode: sparse`, prompts/70): same structure, lean harder on
the business-model spine + external anchoring (peers/industry carry the report), publish
estimates as a confidence-capped range not a point, make the gaps section prominent. The
business-model map is built from first principles + one AR, so it survives thin data — which
is exactly why it's the spine.

**Circular research** is now driver-tagged: 03 emits the industry questions → DR2 answers
those precisely (not a generic sector pass); analysts may raise **micro-searches** (≤3 queries,
`impacts`-tagged, budget in config) mid-analysis; new facts propagate via the existing
staleness engine. Two bounded deep passes + micro-searches + single-query rating-box lookups —
never an unbounded "research everything" pass.

Gotchas learned wiring it here:
- The skill assumes the Linux sandbox (`/mnt/skills/public/docx`, `/mnt/user-data/outputs`,
  `soffice`→`pdftoppm`). None exist on this Windows box. The installed SKILL.md is patched to
  point at `tools/report_formatter/` and to verify via **Word COM → PDF** (Word 16 is present;
  LibreOffice is not). If you Read the .docx `document.xml` you can structurally verify without
  Word, but visual verification (column-width ratios, tombstone color) needs the PDF.
- The shipped `scripts/example_*_content.js` `require("./reportStyle.js")` relative to the
  skill's own dir, which has no `node_modules/docx` — so you cannot `require()` them from a
  smoke test that expects docx to resolve. Use them as read-only reference; render only via
  `tools/report_formatter/` where docx is installed.
- `colWeights` is the #1 visual defect: always widen prose columns (Lever/Read, Risk, Rule×
  Read) — e.g. `[1, 3.2]` — or text wraps ugly against the numeric-table default.
- Tombstone only on ER + buy-side; forensic uses a "no recommendation" callout instead.
- TODO (nice-to-have): a `tools/report_formatter/` content-schema validator that checks each
  module exports the 4 required keys and that every `table` row length matches its headers,
  before build — would catch content-extraction errors without a full render.
