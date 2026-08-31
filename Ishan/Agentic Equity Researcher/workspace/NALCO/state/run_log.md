# NALCO run log — initiated 2026-07-15

Orchestrator: Claude (native mode). User request: full initiation-of-coverage note + dossier + valuation handoff, followed by an explicitly requested buy-side analysis (2-3 pages). Constraints from user: unbiased recommendation, minimal tokens, prefer small interleaved searches over monolithic research, leave an SOP note for future opus-orchestrated runs.

## Wave 0 — INTAKE (2026-07-15)
- Trigger: user dropped 13 UUID-named PDFs in `Outputs/Trial 1 (NALCO)`.
- Classified deterministically (pypdf first-page scan + keyword pass, zero LLM tokens on doc bodies) → copied/renamed into `input/NALCO/` per convention. Originals untouched.
- Result: 5 ARs FY2021-FY2025, 4 FY2026 transcripts, 4 FY2026 presentations. Gaps recorded in manifest (notably: no FY2026 audited annual statements; FY2026 numbers will come from presentations).
- Market data: `tools/market_data.py NATIONALUM.NS` → 55 facts, OK.
- Bug hit & fixed: `markitdown` not installed → `pip install -r tools/requirements.txt`. Logged for SOP.
- Encoding bug (Windows): printing PDF text to console needs `sys.stdout.reconfigure(encoding="utf-8")` — cp1252 crashes on Devanagari. Logged for SOP.

## Wave 0.5 — CONVERT (2026-07-15)
- Trigger: intake complete. `python tools/convert_docs.py NALCO` running in background (~1,560 pages, zero tokens).

## Wave 1 — TRIAGE (2026-07-15)
- Trigger: manifest complete. Rules T1-T6 applied → `state/triage.json`.
- Key scheduling decision: DR2 deferred until after extraction (R-SEGMENT), scoped to ONE aluminium-value-chain pass, not per-segment; DR1 runs alongside the analysis wave; small targeted WebSearches allowed between waves (user preference, bounded by research_loops_max=3).
- SRC-id ranges reserved for parallel extraction (collision prevention):
  - orchestrator/market data: SRC-001..099
  - AR_FY2021: SRC-100..199 · AR_FY2022: SRC-200..299 · AR_FY2023: SRC-300..399 · AR_FY2024: SRC-400..499 · AR_FY2025: SRC-500..599
  - PPT Q1: SRC-600..629 · PPT Q2: SRC-630..659 · PPT Q3: SRC-660..689 · PPT Q4: SRC-690..719
  - TR Q1: SRC-720..749 · TR Q2: SRC-750..779 · TR Q3: SRC-780..809 · TR Q4: SRC-810..839
  - analysis/derived: SRC-840..899 · research/external: SRC-900..999

## Wave 0.5 complete (2026-07-15 ~11:57)
- CONVERT finished: 13 docs, ~1,590 pages, 2,323 table JSONs. First run failed (`markitdown` missing) → deps installed → rerun OK.

## Wave 2 — EXTRACT (2026-07-15, dispatched ~12:00)
- Trigger: conversion cache complete.
- Dispatched 13 parallel haiku extractors: doc-extractor × 5 (AR FY2021-FY2025, both bases, notes to 3 levels), narrative-extractor × 8 (4 transcripts, 4 presentations).
- Presentations flagged CRITICAL as sole source of FY2026 quarterly/full-year financials (no Q_*.pdf filings in input; AR FY2026 unpublished).
- Outputs: facts → facts/fragments/facts_<docid>.json; quotes/guidance → facts/quotes/; registry fragments → state/registry_fragments/ (merged post-wave; merge_facts.py globs *.json so quotes are kept OUT of fragments dir).

## Wave 2a — EXTRACT partial failure + recovery (2026-07-15)
- 11 of 13 extractors killed mid-run by the Claude session token limit (reset 2:30pm IST). Clean completions: TR_2026-01-30 quotes/guidance, PPT_FY2026Q3 (all files).
- Disk triage: kept TR_2025-08-08 (complete after deterministic registry repair), PPT_FY2026Q1 (all files valid), PPT_FY2026Q3.
- Deterministic bug fix: haiku wrote `"page": 3-4` (unquoted range) in TR_2025-08-08 registry → regex patch script quoted it; JSON now valid. All future extractor dispatches carry an explicit "page must be a single integer" instruction. SOP item.
- Re-dispatched 10 agents: full redo AR_FY2021/22/23/24/25 + TR_2025-11-07; registry-repair-only for TR_2026-01-30 (6/30 entries present) and TR_2026-04-30 (registry never written); completion tasks for PPT_FY2026Q2 (quotes/guidance/registry missing) and PPT_FY2026Q4 (quotes empty, registry 6 entries).
- Lesson for SOP: subagents should write registry fragments INCREMENTALLY (or first), not at the end — an interrupted agent leaves quotes without citable sources; the repair cost is an extra dispatch.
- RANGE AMENDMENT: TR_2026-04-30 extractor legitimately needed 87 SRC ids and used SRC-810..896, overflowing its 30-id block into the old analysis range. Rather than renumber 87 records, analysis/derived range moves to SRC-1000..1099 and research/external to SRC-1100+. Reserve ≥100 ids per transcript in future runs (SOP item).

## Wave 2b — deterministic validation + normalization (2026-07-15)
- Wrote validate_extraction.py (scratchpad): JSON validity, cross-doc SRC collisions, orphaned src refs, duplicate record ids.
- Defects found & fixed deterministically (normalize_extraction.py, fix_ar21.py — zero LLM tokens):
  - facts_AR_FY2021.json: one unclosed source object (`{"src_id": "SRC-111",` missing brace) → regex patch; 181 records valid.
  - 7 record files object-wrapped (keys facts/quotes/entries/registry_entries) → unwrapped to plain arrays; 3 registry fragments normalized to flat SRC-keyed dicts.
  - AR_FY2023 used SRC-300..479 (overflow into AR_FY2024's 400-block) → SRC-4xx remapped to SRC-34xx across its 3 files.
  - TR_2025-11-07 used SRC-750..800 (overflow into TR_2026-01-30's block) → remapped to SRC-1750..1800.
  - facts_AR_FY2024.json: 3 duplicate ids with differing content → suffixed -dup2.
- Post-normalization: 0 SRC collisions, 0 dup ids, single orphan cluster: AR_FY2024 facts reference SRC-415..499 never registered (agent under-registered) → repair agent dispatched.
- Content gaps queued (extraction is cheap): AR_FY2025 deeper pass (consolidated L1, CF line detail, RPT, borrowings, ageing, segment completion, MD&A guidance → facts_AR_FY2025_pass2.json, SRC-2500..2599); AR_FY2022 consolidated L1 (facts_AR_FY2022_cons.json, SRC-212..240).
- Corpus at this point: ~981 facts, 325 quotes, 179 guidance records across 13 documents.

## Waves 3-8 — COMPUTE through BUY-SIDE (2026-07-15/16, summary)
- COMPUTE: merge (1,203 canonical facts, 1,058-entry registry after all repairs), 82 derived facts, comprehensive statement, EPS-bridge 1P/1F/7NA, xlsx export. 16 merge conflicts → red-flag candidates.
- ANALYZE (4 sonnet + DR1 parallel; one full re-dispatch after session-limit wipeout): fundamental (FY2025 = cyclical peak, 1,966bps margin expansion cyclical), forensic (EQ 75, ledger closed 14 dismissed/7 disclosed/2 confirmed — both guidance-quality), guidance (volumes credible, timelines low-credibility: refinery slip Jan-2025-original→Jun-2026, capex overrun ~20%), governance (Green 78.5 → revised Amber 73.3 after DR1-B found LODR fine + CBI probe — staleness loop worked).
- RESEARCH: DR1 (18 searches), DR2 (18 searches — mgmt price guidance ≈ World Bank central; cost-leadership claim only stale-verified), DR1-B follow-up (LODR fine ₹10.86 lakh, CBI probe, refinery commissioning unconfirmed as of Jul-2026), extraction-answers pass (CFO collapse = payables swing; lease dates contradict mgmt claim). 27 questions consolidated; all high/medium answered or disclosed.
- SYNTHESIZE: peer-valuation (CMP ~2x own 5y PE band, no evidenced catalyst, BQ 6.05/10), estimates (FY27E ₹32.76 / FY28E ₹31.05, spread -18/+16%), thesis (5 pillars, all ≥2 refs) → rating REDUCE with explicit not-SELL/not-HOLD reasoning.
- RENDER: opus dossier (9,425 words, 225 citations) + final note (~9pp, rating once, banned words 0).
- VERIFY: round 1 FAIL (registry linkage ~70 orphans, basis mixup, estimates uncited, promoter unverified) → fixes: deterministic registry fold-in (external files register sources under source_registry_additions — merge script must glob that key), estimates SRC-1384..1397 via SendMessage, report fix pass, promoter verified primary via one orchestrator WebSearch (51.28% Q4 FY26). Round 2 residue was schema drift in DR fact files (source_ids/sources vs source.src_id) — fixed by script; final mechanical gate PASS (all 44+66 S-tokens resolve).
- BUY-SIDE (explicit user request): AVOID at CMP, conviction 0.72, doctrine-fair value ₹248 (7.58x × FY27E), re-engage ₹250-270 or on confirmed 5th-stream ramp. Independent from but directionally consistent with the sell-side REDUCE.
- Deliverables: report/dossier.md, report/final_note.md, report/buy_side_note.md, handoff/valuation_handoff.json (schema-valid), exports/NALCO_financials.xlsx, report/verification_report.json (gate PASS).
