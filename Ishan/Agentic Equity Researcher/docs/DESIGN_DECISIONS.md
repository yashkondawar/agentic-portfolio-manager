# Design Decisions — what changed vs. the source documents, and why

The three source documents (extracted copies in `reference/source_documents/`) were treated as a starting point, per the brief. This file records every material deviation so they're arguable rather than silent.

## Conflicts resolved

| # | Conflict | Resolution |
|---|---|---|
| 1 | Architecture doc mandates a **≤12-page** report; Reports_generation_prompt mandates **20–22 pages / 8–10k words** | Both ship: the 20-22p+ spec became the **dossier** (full audit doc, anti-compression); the ≤12p spec became the **final note**. The original user text actually asked for exactly this pair ("a long appended doc with all auditable traceable format, and finally an equity research report… not more than 12 pages"). |
| 2 | Reports_generation_prompt contains company-specific residue (Depository/KRA/Repository segments, T+0 settlement, Insurance Demat, "Digital Toll Bridge") — it was written against a CDSL-type company | Generalized: structure parameterized, sector specifics now come from the sector pack + triage; the metaphor rule became "≤1 structural metaphor, no new facts". |
| 3 | Every prompt demanded "Markdown tables ONLY" as the working format; the architecture doc itself argues for JSON records with markdown only at render | Sided with the architecture doc: JSON fact records everywhere internally (`schema/fact_record.schema.json`), markdown rendered deterministically at the end (`tools/render_tables.py`). Parsing your own markdown back to merge 16 documents is strictly worse. |
| 4 | Fin_analysis_prompt1 and Fin_analysis_prompt2 overlap (both do CFO/NI reconciliation, DSO, receivable flags) with no shared context — they could emit contradictory versions of the same flag | Single shared red-flag ledger (`schema/red_flag.schema.json`). Deterministic thresholds seed candidates; **forensic adjudicates all verdicts**; fundamental only enriches. No private flag lists. |
| 5 | Prompts asked the LLM to do arithmetic "digit-by-digit" | All standard ratios/growth/thresholds moved to `tools/compute_ratios.py` (zero tokens, zero arithmetic hallucination). Audit trail preserved via `formula` + `inputs` on every derived record. LLM computes only what a script can't, and must show work. |
| 6 | DR1 "Task 5,6,7" asked deep research to web-find prices/mcap/index returns | `tools/market_data.py` (yfinance) — deterministic, timestamped, exact. Deep research is barred from price-finding except as flagged last-resort. (Architecture doc's own recommendation.) |
| 7 | Eight slightly different audit-trail instructions ("supersede all other context…") across prompts | One `prompts/00_citation_standard.md` that genuinely supersedes; all module prompts reference it. Global source registry with namespaced ids replaces per-prompt legend conventions ([FN1]/[FA2.1]/[TT1.1] → SRC-###/[S#]). |
| 8 | "Buy-side practical" framing in DR2 prompt family vs the stated goal of a **sell-side** agent | Tone kept analytical; deliverable reframed sell-side: rating box (once), thesis pillars, variant view, estimates table, catalysts/monitorables. Rating scale BUY/ADD/REDUCE/SELL (config). |
| 9 | "IQ above 160" style roleplay in analysis prompts | Removed. Replaced with concrete procedures (what to check, what evidence adjudicates, what to output). Roleplay doesn't improve extraction; explicit method does. |
| 10 | Original FCF definition included "purchase of investments" in capex | Excluded financial-investment purchases from net capex (treasury churn isn't capex; including it breaks FCF for cash-rich companies). Deviation noted in the tool docstring; treasury behaviour still analyzed under other-income dependence. |

## Additions (gaps vs. real sell-side practice — the "critique and add more" ask)

1. **Verification wave** (`prompts/50` + citation-auditor + `tools/citation_check.py`): every prompt asserted an audit trail; nothing checked it. An invented page number is as easy as an invented revenue figure. Adversarial re-derivation, default-refute, load-bearing = 100%.
2. **Estimates module** (`prompts/32`): the source set analyzed history but produced no forward numbers — yet the stated goal needs FY+1/FY+2 projections, forward PE, and a handoff for PE-scenario sensitivity. Drivers-based build with credibility-weighted guidance, sanity gates, scenario seeds.
3. **Guidance credibility tracker** (in `prompts/22`): guidance-vs-delivery history scored per metric family. Sell-side lives and dies on knowing whose guidance to believe; nothing in the source prompts tested it.
4. **Capex/returns engine depth** (in `prompts/20`): incremental ROCE, gross-block→revenue conversion lag, CWIP ageing → commissioning slippage. The brief explicitly emphasized capex; the source prompts only had "CAPEX/CFO spike" as a fraud screen.
5. **Coverage snapshot block + variant view + what's-priced-in + catalysts calendar** (in `prompts/41`): the architecture doc's own critique listed these as the gap between "checklist" and a real initiation note.
6. **Rule-based triage** (`prompts/02`): makes "dynamic, not a flow" auditable — the order varies, but the rule that fired is logged.
7. **Staleness propagation** (`prompts/01` §2): `depends_on`/`impacts` machinery so late research updates exactly the findings built on the old gap — the user's "circle back to the start" requirement, without re-running everything.
8. **BFSI structural fork**: lender financials aren't manufacturing financials; extraction addendum + pack + graceful ratio skipping.
9. **Failure isolation**: per-wave cache keys, retry-once, degrade-to-gap — from the architecture doc's journaling advice.

## Removals / demotions

- **Fin_processing_prompt** as an LLM step — replaced by `compute_ratios.py`; its "no re-calculation, reported wins" rule survives in the citation standard §2.
- **ESG and DCF/WACC** — excluded per explicit instruction; config toggles left in place.
- **"Recommendation only once"** — enforced structurally (template has exactly one rating box; report prompt bans restatement).
- Boolean search strings, NSE URL patterns, cycle-check framework, sector KPI menus — **kept** (they're the domain value of the source docs), reorganized into `prompts/30/31` + sector packs with the 8× repeated boilerplate deduplicated.

## Defaults chosen (change in `config/agent_config.yaml`)

Rating scale BUY/ADD/REDUCE/SELL · markdown deliverables (docx render is roadmap) · consolidated basis preferred when subs material · research loops max 3 · verification sample 30% (load-bearing 100%) · fair-value context only, no TP (downstream agent owns TP).

## Roadmap (post-v1)

1. **Valuation/sensitivity agent** consuming `valuation_handoff.json` → PE re-rate/de-rate/constant grid → TP; then the note's rating box gets a real TP.
2. **Benchmark harness**: run against a company with a real published initiation note; diff section-by-section (the user's stated evaluation plan).
3. Chart rendering (matplotlib → PNG exhibits), docx/PDF export of the final note.
4. Consensus-estimates source (variant view vs street, not only vs guidance).
5. api_mode hardening: docling+langextract extraction with character-offset grounding for the verification wave (span-level, beyond page-level).

## 2026-07-08 — Numbers-depth retrofit

A gap analysis against real sell-side practice ("3 levels deep through all
notes, one comprehensive statement") specified five changes, executed as a
single retrofit:

1. **markitdown preprocessing (step 0.5 CONVERT)**: `tools/convert_docs.py`
   runs deterministically before extraction — page-anchored markdown
   (`cache/markdown/<docid>.md`, via pypdf page-split + markitdown per page,
   since markitdown alone collapses page boundaries on a whole multi-page
   PDF) and per-page table JSON with bbox metadata
   (`cache/tables/<docid>_p<N>_t<K>.json`). Zero tokens; haiku extractors now
   read structured text/tables instead of raw PDF layout. Original PDFs in
   `input/<TICKER>/` are never modified — the caches are derived, and the
   citation-verification wave still grounds against the original PDF page.
2. **Level-3 extraction trigger** (`prompts/10`): extraction no longer stops
   at the first note breakdown — a Level-2 note with its own sub-schedule
   (borrowings by instrument and maturity, ageing buckets, RPT by
   counterparty) now emits Level-3 records. Paired with an explicit
   instruction to exclude one-off items from the FCF calculation and
   disclose the exclusion in `flags`.
3. **Comprehensive statement** (`tools/build_comprehensive_statement.py`,
   new COMPUTE-step tool, zero tokens): assembles
   `state/comprehensive_statement.{json,md}` — a line-item TREE (level 1→2→3)
   per statement (IS/BS/CF) x all fiscal years and available quarters, each
   node carrying its fact_ids. This is the "one comprehensive statement" the
   original ask named; `prompts/20`/`32` now anchor line-item analysis and
   driver decomposition to its nodes, and the dossier (`prompts/40`) renders
   it (full, or top-2-level summary if it would blow the anti-compression
   budget).
4. **Quarterly trend & seasonality** (`prompts/20`, new item): QoQ/YoY-by-quarter
   view of revenue/margins/working-capital from Q/H facts, flagging any
   quarter where the annual narrative and quarterly cadence disagree — a gap
   the original module set didn't cover (annual-only trend analysis).
5. **Role groupings** (`CLAUDE.md`, `config/agent_config.yaml`): a purely
   descriptive mapping from the user's own staging vocabulary (DEX/QFA/
   IGL/CRA/BSA) onto this system's numbered modules, plus an explicit
   "Combined all" note (the `workspace/<TICKER>/` state, centered on
   `state/comprehensive_statement.json`, IS the combined-all artifact — no
   separate mega-file) and an orientation line making explicit that this
   system's center of gravity is equity research and numbers depth, not
   forensic earnings-quality (21 is one module in that flow).

No behavior changed for existing modules beyond the specific insertions
above; no ticker run exists yet to validate end-to-end (no documents in
`input/<TICKER>/` at time of writing) — `convert_docs.py` and
`build_comprehensive_statement.py` were validated against ad hoc fixtures
(a real multi-page PDF for conversion; a synthetic 3-level/2-period fact set
for the statement tree) instead.

## 2026-07-13 — Buy-side EPS-bridge stage added (optional, non-default)

Ported from the fund repo (`D:\Documents\Claude\1Projects\AI Native Fund`),
where the user supplied a buy-side EPS-bridge doctrine (Price = EPS × PE;
consistent >20% EPS growth + low starting PE → rerating; six-rung
decomposition from revenue visibility down to EPS; funding-discipline and
working-capital rules; a qualitative management-intent gate) and it was
first encoded there as `knowledge/references/methodology/eps_bridge.md` +
`registry/rules/eps_bridge.yaml` + `research/equity_researcher/tools/
eps_bridge_check.py` + `.claude/agents/buy_side.md`. This project received
the standalone half of that work:

1. **Added, not wired into the default pipeline.** `.claude/agents/
   buy-side-analyst.md` (opus tier, `tools: Read`) and `prompts/
   60_buy_side.md` exist alongside the 0→8 run lifecycle but are not
   dispatched by any wave in `prompts/01_orchestration_protocol.md`. They
   run only when the user explicitly asks for the buy-side analysis, against
   a ticker that already has a completed run. `CLAUDE.md` gained a short
   "Optional buy-side stage" section saying exactly this; the orchestration
   protocol file only gained COMPUTE-step wiring notes (see below), not a
   dispatch entry — a deliberate scope boundary from the source plan.
2. **Two deterministic tools ported into `tools/`**: `eps_bridge_check.py`
   (reads the merged facts store, computes PASS/FAIL/NA + numbers per
   EPS-bridge rule, zero tokens) and `export_financials_xlsx.py` (openpyxl
   export of the comprehensive-statement tree + ratios + checker output +
   red-flag ledger to `exports/<TICKER>_financials.xlsx`). Both are wired
   into the COMPUTE step (`CLAUDE.md` step 3, after
   `build_comprehensive_statement.py` has written
   `state/comprehensive_statement.json`) alongside the existing
   `compute_ratios.py` / `build_comprehensive_statement.py` pair.
   `export_financials_xlsx.py` needed no changes at all (it already had no
   fund imports). `requirements.txt` gained `openpyxl` and `pyyaml`.
3. **Thresholds inlined locally, not shared via a registry.** This project
   has no `registry/` layer (that's a fund-only concept), so
   `eps_bridge_check.py`'s threshold loader was adapted: it now resolves
   thresholds from an explicit `--thresholds` file if given, else
   auto-discovers `config/eps_bridge_thresholds.yaml` (new file, an inlined
   copy of the fund's `registry/rules/eps_bridge.yaml` values — same DRAFT
   status markers, same `sector_overrides: {}` block, same threshold
   values), else falls back to the same `DEFAULT_THRESHOLDS` constant the
   fund copy already carried for standalone-safety. The YAML-vs-JSON
   `{value, status, note}` block shape is flattened by a small loader
   helper (`_load_thresholds_file`) that didn't exist in the fund version
   (which only ever read a flat JSON override file).
4. **Deliberate duplicate of the doctrine text.** `prompts/60_buy_side.md`
   embeds the full EPS-bridge doctrine prose (adapted from the fund's
   `knowledge/references/methodology/eps_bridge.md` — its pointers to the
   fund's `buyside_depth.md` companion methodology and
   `knowledge/references/sectors/<sector>.md` sector-override files were
   removed or rewritten, since neither exists in this project; the
   management-track-record pointer was redirected to this project's own
   module 22 guidance-credibility ledger instead) plus the reasoning ladder
   and output contract, so the standalone project stays self-contained (no
   fund pointer). This is a second copy of that text by design — keeping it
   in sync with the fund's version if the doctrine changes is a manual,
   human-driven step, not automated. `.claude/agents/buy-side-analyst.md`
   was written in this project's own agent style (plain role-mandate prose,
   "On start, read" list, JSON-only output contract) rather than copying the
   fund's SECURITY-preamble agent format, since none of this project's
   existing 14 subagents use that preamble style.
5. **Sanity-checked, not run end-to-end.** Both ported tools were verified
   with `ast.parse` and `--help` (fund venv Python) and
   `eps_bridge_check.py` was smoke-tested against a small synthetic
   `financials.json` fixture to confirm the local YAML threshold
   auto-discovery resolves correctly. No ticker in this project has a
   completed run yet, so the buy-side agent itself has not been invoked
   end-to-end — same honesty posture as the rest of this file's prior
   entries.

## 2026-08-02 / 2026-08-03 — The corpus-derived knowledge layer, and the validators that keep it honest

Two sessions. The first built a knowledge layer from real broker notes; the second finished it
and, more importantly, made its claims checkable. The design calls worth recording are below —
the file inventory is in `VERSION.md` under v2.1.

### 1. Evidence base moved from one note to 165

`docs/PROCESS_V2_REIMAGINED.md` (2026-07-19) was reverse-engineered by hand from a single Emkay
NALCO note. Its *diagnosis* was right — our process was filing-centric where an analyst's is
business-model-centric — but a sample of one cannot tell you what the genre does. So
`tools/er_corpus/` was built to fetch and profile a corpus, and `docs/ER_CORPUS_FINDINGS.md`
re-derives the same questions from **165 confirmed initiation notes, 25 brokers, 2010-2026**.

The finding that changed the most: **85% of rated initiations are BUY and 94% are positive.**
A distribution with almost no variance cannot discriminate between companies. Hence the rule in
`ER_CORPUS_FINDINGS.md` §5 — *copy the analytical apparatus, discard the verdict distribution* —
and hence modules 33/34, which exist to supply the variance the genre does not.

**PROCESS_V2 is superseded in part, not retired.** Its five-layer framing, value-chain method and
sparse-data reasoning are still the best statement of those ideas. Three specific claims were
wrong or stale and are now corrected *inline at the sections they affect*, so a reader who jumps
straight to §1 sees the correction without having read the header. One deserves naming: **§1 row 6
listed in-note sensitivity as a capability gap; the corpus inverts that** — sensitivity tables
appear in 14% of notes as a named section and 19% anywhere, so `prompts/32`'s mandate already
exceeds what five in six professional initiations do. `ER_CORPUS_FINDINGS.md` §1 says explicitly:
do not weaken it to match the corpus. A benchmark is not automatically a target.

### 2. Two-tier sectors: packs route, playbooks analyse

One flat set of 8 sector packs could not carry both "which statements and lenses" and "what
exactly do I compute, and what does good look like". A bank and an AMC share a statement fork and
nothing else; a hotel and an FMCG brand share almost nothing at all.

So: **8 family packs became thin routers** (family scope, the statement fork, genuinely
cross-cutting lenses, a child index — no KPI tables) and **32 tier-2 playbooks** own the analysis.
`config/sector_registry.yaml` is the single machine-readable source of routing.

The cost of the split, and the mitigation: the first draft immediately produced duplication —
`bfsi.md` and `nbfc_diversified.md` repeated essentially every KPI, and the registry restated each
playbook's `signature_kpis` and `valuation_convention` a third time. Prose cannot be trusted to
stay de-duplicated, so the rule is enforced mechanically:

- **E10** fails if a playbook restates its family pack's KPI content.
- **E11** fails if the registry carries prose that belongs in a playbook. The registry now holds
  only `family`, `status`, `keywords`, `signature_kpis`, `unit_denominator` — the keys a machine
  routes or checks on. All 32 `valuation_convention` copies were deleted.
- **E8** requires every declared `signature_kpis` name to appear in its playbook's KPI table, so
  the registry and the playbook cannot disagree about what defines a sub-sector.

`signature_kpis` deliberately **stays** in the registry despite being a second mention of the KPI
names, because it is not prose: it is the machine-readable coverage contract that
`tools/compute_kpis.py` enforces, emitting a named skip for every signature KPI a run failed to
produce. A duplicate that a validator checks is a contract; one that nothing checks is drift.

### 3. Provenance on every playbook, and four honest gaps

Each playbook declares whether it is **corpus-grounded** (naming the notes) or **domain-derived**.
Four are domain-derived because the corpus genuinely has no note: `microfinance` (no MFI
initiation — CreditAccess, Fusion, Spandana, Satin all absent), `qsr` (no mainstream QSR chain;
only travel-QSR), `diagnostics` (no Dr Lal/Metropolis/Thyrocare) and `oil_gas_cgd` (no oil, gas,
refining or CGD note at all). Each names the adjacent files that *were* read, and raises an open
question to seed the corpus.

This mattered more than expected: checking the corpus rather than trusting the plan **corrected
four coverage labels**. `general_health_insurance`, `electronics_manufacturing`,
`defence_manufacturing` and `logistics` were assumed thin and are in fact corpus-grounded (JM's
70-page insurance note; Dixon and EPACK; BEL and HAL; Delhivery, TCI Express and IndiGo). A
plan's guess about its own evidence is not evidence.

### 4. The 40% rule is arithmetic, and it is symmetric

`config.thesis.rerate_share_threshold_pct: 40` — if more than 40% of expected return comes from
the multiple moving, the re-rating checklist applies **whatever the thesis calls itself**. This is
deliberately not editorial: `prompts/33` computes `multiple_share_pct` first, before naming an
archetype, so the label cannot be chosen to dodge the checklist.

Made symmetric on 2026-08-03. A thesis whose return is mostly the multiple *falling* is exactly as
multiple-driven as one where it rises, so `de-rating` and `cyclical-peak` satisfy the rule
alongside `re-rating`, as does an explicit `archetype.forced_rerating: true`. Found by writing
NALCO's thesis: it came out at 93% multiple share on a **de**-rating, which the first version of
the check would have failed for the wrong reason.

### 5. The mandatory 33-34-33 round trip, and who owns the thesis

`prompts/34` runs in a **separate context** and is forbidden from editing `state/thesis.json` — a
red team that can rewrite the thesis it is attacking is not a red team. But
`schema/thesis.schema.json` has a `redteam` block, so something must write it. The only defensible
owner is **module 33 on its mandatory post-red-team pass** (`prompts/33` step 7b), because 33 owns
the file. Before 2026-08-03 that block had no writer at all and was an orphan.

The round trip is not ceremony. On NALCO it changed the thesis: the red team's challenge that the
target multiple was *asserted* ("9.5x mid-cycle") rather than anchored was accepted, the target was
re-anchored to 8.4x — the top of the company's own realised 5-year P/E band — and expected return
moved from -18.4% to -27.9%. **The correction made the thesis more bearish, not more comfortable**,
which is the behaviour that tells you the pass is real. It also surfaced that the superseded thesis
had quoted the band as "4.6x-8.7x, median 7.6x" when its own cited source says 4.1x-8.4x, median
6.3x — favourable to the stock at every point of the band.

### 6. Documents that assert integrations must be checked by something

The defect this project keeps rediscovering: a comment describing a state of the world that stopped
being true. `tools/requirements.txt` claimed "verified installed" and was wrong twice. The registry
header listed `compute_kpis.py` as a consumer when the tool had no reference to it. A `generic`
playbook was marked `authored` with no file, and the validator carried an escape hatch that hid
exactly that.

Prose cannot police prose, so `tools/preflight.py` is now the single entry point for every static
check — dependency imports, registry integrity (E1-E11, failing on any `pending` playbook), schema
parses, config parses plus model-tier and role-group completeness, a dead-reference scan over all
markdown, the `reportStyle.js` byte-identity check, and a compile check on every `tools/*.py`.
`tools/validate_state.py` does the same for a run's state. `CLAUDE.md` documents preflight as a
pre-run step.

Two design choices inside them worth recording:

- **`requirements.txt` no longer asserts install status at all.** A comment cannot know what is
  installed; `preflight.py --deps-only` can. Replacing a claim with a check is the general fix.
- **The dead-reference scanner has an explicit `INTENTIONALLY_ABSENT` list with a reason per
  entry** — fund-repo paths cited for provenance, files named as future work, and files named
  *in order to say they do not exist*. That last category is the honest kind of dangling
  reference (a correction naming the thing it corrects), and a checker that could not express it
  would push authors toward deleting the correction.

### 7. `api_mode/` is a documented scaffold, and now says so

It was claiming more than it delivered: its README described `extract_docling.py` as "a stub with
the intended interface" when no such file exists or ever did. Corrected, and the larger gap stated
plainly — **waves 6a/6b are unimplemented there**, so an api_mode run produces no thesis artefact,
no red-team verdict and no rating derivation, i.e. none of the three things `CLAUDE.md` rule 7
calls non-negotiable. Native mode is the only mode that runs the full lifecycle. Keeping the
scaffold is fine; letting its existence read as parity is not.

### 8. Honesty posture, unchanged and now enforced

Two things follow from the same principle and are worth stating together.

**Gaps are named, not filled.** `compute_kpis.py` previously dropped a period with partial segment
data without a trace — NALCO's FY2023 vanished from the segment series between FY2022 and FY2024
because it carries segment revenue but no segment result. It now emits a named skip saying exactly
that, and what to extract to close it. The same tool emits a named skip per unmet signature KPI. On
NALCO, 2 of 5 signature KPIs for the resolved playbook are uncomputable, and the thesis says so
rather than asserting the cost-curve claim they would have supported.

**`workspace/NALCO/` is kept with its defects** as the worked example, including a
`final_gate_decision: FAIL` with no override — meaning the report does not pass the citation gate.
Rule 6's override requires an itemised justification *per fatal item*; `validate_state.py` now
checks that mechanically, and the auditor's own verdict is preserved beside any override rather
than replaced by it. The NALCO run once closed a 10-item FAIL to PASS with a one-line stamp,
including the two facts a thesis pillar rested on. That is the failure the check exists to prevent.

One correction to an earlier assumption, for the record: `tools/market_data.py` was believed to
*fail silently* on a wrong ticker. It does not — it exits 2 with `FAIL: no price history returned`.
The real defect was the ticker itself (`NALCO` where yfinance needs `NATIONALUM.NS`), now fixed in
the run state with the trap noted in `business_model.json`.

### 9. 2026-08-03 (later) — Evidence first, and the statement tree actually three levels deep

Four confirmations requested; two were already true, two were not.

**Confirmed as already working: markitdown is step one.** `tools/convert_docs.py` splits each PDF
per page with pypdf (markitdown loses page boundaries on a whole multi-page file), converts each
single page, and stitches the result with `<!-- page N -->` anchors, alongside pdfplumber per-page
table extraction. Extractors read those caches; the citation wave still opens the original PDF at
the cited page. No change needed.

**Not working as advertised: the "3-level decomposition".** `prompts/10` mandates `level: 1|2|3`
and extraction populates it (630/483/107 on NALCO). But it populated `parent` on **79 of 1,220
facts (6%)**, and `build_comprehensive_statement.py` promoted any record without a resolvable
parent to a ROOT regardless of level. Result: 117 "roots" on an income statement with about twelve
face lines, maximum depth 2, and the same label appearing as several sibling rows in the Excel.
The advertised tree was not being built.

Fixes, in order of how much they moved:

1. **Only level 1 becomes a root.** A level-2/3 record without a parent is now *attached*: explicit
   `parent` first, else the longest metric-name prefix shared with a shallower metric in the same
   statement (this vocabulary names breakdowns by extending the parent's stem —
   `revenue_alumina_export` → `revenue_alumina` → `revenue`), else a per-statement bucket node
   labelled "Level-N items whose parent line was not captured by extraction". Every inferred edge is
   counted and the disclosed/inferred/bucketed split is printed, so a largely-reconstructed tree
   announces itself. Nodes carry `inferred_parent: true`.
2. **Period aliases folded.** Extraction emitted the prior-year column as a *separate metric*
   (`revenue_from_operations_prior`) and quarterly cuts likewise (`..._h1`, `..._q2`,
   `..._fy2025_full_year`) while each record's `period` field was already correct — 185 aliases on
   NALCO, every one duplicating a base metric that was present. Folded onto the base line item.
3. **Derived percentages routed out of the statements.** `*_yoy_pct` / `*_qoq_pct` are real facts but
   not statement lines: a percentage in a currency column breaks the common-size base.
4. **Classifier expanded.** 204 line items were sitting in `unclassified`, including `total_income`,
   `profit_for_the_year`, `intangible_assets`, `other_equity`, `total_liabilities` and
   `cash_from_operating_activities` — lost to singular/plural stems (`intangibles` never matches
   `intangible_assets`) and to Ind-AS wording the lists never covered. The bucket was also renamed:
   what remains there is production, capacity, dividends and buybacks, which are legitimately outside
   the three statements and are exactly what the operating-KPI layer needs. It was never a failure
   bucket, and its name should not have implied one.
5. **`prompts/10` now requires `parent` on every level-2/3 record**, forbids inventing `_prior`
   metrics, and asks that breakdowns extend the parent's stem so a forgotten edge stays recoverable.

Net on NALCO: income-statement roots 117 → 47, maximum depth 2 → 3, `revenue_from_operations`
gaining 13 children.

**Not present at all: horizontal and vertical analysis in the Excel.** The workbook had 7 tabs and
neither. It now has 15, including `IS/BS/CF_horizontal` (YoY per line item) and
`IS/BS/CF_vertical` (common-size against revenue / total assets / CFO), an `Other_metrics` tab, and
a `Contents` tab that states what each sheet holds and how much of the tree was inferred.

Three defects surfaced while building it, each fixed at source rather than worked around:

- **Rows sorted alphabetically**, so the income statement opened on "Current tax assets (Net)". They
  now follow a canonical statement sequence, with unrecognised metrics alphabetical *after* the known
  ones so nothing is hidden and no position is invented.
- **The basis collapse.** `Node.values` is keyed by period alone, so a line reported on both bases
  kept whichever record was written last — NALCO's revenue ended up standalone for FY2020 and
  consolidated for FY2021-26. The single-basis column filter then blanked most of the statement, and
  the "dominant" basis was chosen by raw fact count (standalone 157 vs consolidated 122) even though
  consolidated spans six years and standalone one. Basis preference is now deterministic
  (consolidated wins, the displaced value kept as `alt_basis`), and dominance is measured by
  fiscal-year coverage. Line items available only on the other basis are **left blank and the count
  disclosed in the sheet header** — blending bases in one common-size column would be arithmetically
  wrong, and a blank row that looks like missing data is worse than a blank row that explains itself.
- **One structured field aborted the entire workbook.** A why-chain list or merge-discrepancy dict in
  the red-flag ledger raised `ValueError: Cannot convert {...} to Excel` and killed every sheet.
  `_cell_safe()` renders non-scalars instead: this export is a reading surface, and a readable
  summary beats no workbook.

### 10. Stance: `evidence_first`

The reader forms their own opinion, so the report's job is to give them what they need to do it —
extraction depth, external industry and comparables research, analysis and evaluation — and to keep
the house view small, clearly labelled and skippable.

**This is the repo's own finding turned into a default, not a change of standards.**
`docs/ER_CORPUS_FINDINGS.md` §5 measured 94% positive ratings across 165 initiations and concluded
"the rating carries almost no information. The analysis carries nearly all of it." Leading with the
least informative element is a design error the genre normalised; we had inherited it.

What changed:

- `config.report.stance: evidence_first`, `config.rating.emit` (set false for an evidence-only
  report), `recommendation_position: end`, page budget 12 → 14 — the extra pages go to evidence.
- `config.report.evidence_floors` makes "do not compromise the detail" checkable: 3 statement levels,
  horizontal+vertical analysis required in the xlsx, ≥6 independent external sources, ≥5 domestic
  peers with multiples actually pulled, ≥3 periods of operating KPIs, ≥20 exhibits.
  `tools/validate_state.py` checks the ones it can see and warns per unmet floor.
- `prompts/41`: page 1 is the business and its economics with **no rating**; the return decomposition
  appears early as *arithmetic* so a reader can discount our later view against it; the house view is
  §9, bounded to one page, omitted entirely when `rating.emit` is false. Template reordered to match
  ("Investment thesis" → "Key findings"; the must-be-true table reframed as the reader's checklist).
- `prompts/33`/`34` keep every obligation but are told plainly what they are for under this stance:
  quality control on the evidence, not authorship of a headline. 33 must never soften an
  `unestablished` status to make a rating easier to defend — the status is the deliverable and the
  rating the by-product. 34's findings are published, not merely filed, and a challenge it raises
  that 33 cannot resolve is the most honest output a run can produce.
- `prompts/31` is told it now carries a headline deliverable, with the peer-multiple floor named. The
  NALCO run's "domestic peer multiples not located" was its largest disclosed gap; under this stance
  that is a failed deliverable, not a footnote.
- The formatter skill: the ER `.docx` opens with the structural read and snapshot, and the **rating
  tombstone moves to the closing section** — or is dropped for the forensic "no recommendation"
  callout when the note carries no rating.

**What deliberately did NOT change.** Modules 33 and 34 still run, the 33→34→33 round trip is still
mandatory, and the citation gate is still binding. De-emphasising the verdict is not the same as
lowering the bar for it — the opposite, since a report that leads with evidence has nowhere to hide
a weak number.
