<!-- Dossier skeleton — full spec in prompts/40_dossier_assembly.md. Anti-compression: complete
     tables, complete ledgers. The numbering here matches prompt 40's numbered structure 1:1 —
     add a section to one file and you add it to the other. (Before 2026-08-03 the two disagreed:
     the template ran 0-14 while the prompt ran 1-15, the template carried an "Open questions"
     section the prompt never mentioned, and neither carried the thesis or red-team ledger even
     though the final note surfaces a red-team verdict the dossier never recorded.) -->

# {Company} ({TICKER}) — Research Dossier (full audit document)
*Run date: {date} · Inputs: {n} documents (manifest below) · Basis: {consolidated/standalone} (reason: {…})*

## 1. Input manifest & run record
{table: file | classification | period | pages | notes} · {run_log summary: waves dispatched, loops used, why the order varied}

## 2. Executive summary
{Thesis, financial health, valuation synopsis, top 4 risks. No rating here — the rating lives only in the final note's rating box.}

## 3. Industry & market analysis
{DR2 in full: value chain & bottleneck · Porter's 0–10 with justifications · TAM build · **industry supply–demand balance** (deficit/surplus, named players) where the sector is commodity/cyclical · cycle-overlap checks · policy architecture}

## 4. Company deep-dive & value chain
{**Value-chain / asset map** from `state/business_model.json` — each node own/buy/sell-into with capacity/detail — and the net-long/short framing · segments & mix evolution · **operating-KPI trend tables** from `state/kpi_trends.md` · **per-unit economics** (revenue/EBIT/cost per unit by segment) with the cyclical-vs-structural read · **segment analytics** (EBIT-margin + %-contribution trends, the mix-shift story) · **capex / growth-project pipeline** (project | investment | status | completion) · cost buckets · moat matrix with evidence · competitive positioning}

{Name every signature KPI from `prompts/sector_playbooks/{slug}.md` that could **not** be computed, with the reason — `compute_kpis.py` emits a named skip for each unmet signature KPI.}

## 5. Historical financial performance
{All years IS/BS/CF rendered tables · adjusted margins · ROCE trajectory · capex & incremental returns · working capital · why-why on every margin move above threshold · the comprehensive statement from `state/comprehensive_statement.md` (full 3-level rendering if it fits the anti-compression budget, else levels 1–2 with a pointer to `state/comprehensive_statement.json`)}

## 6. Management & governance
{Leadership table · guidance ledger + credibility · direct-quotes bank (claims vs reality) · forensic scorecard /100 · governance chronology · shareholding & pledge trend}

## 7. Earnings quality & red-flag ledger (complete)
{Every flag: id | category | status | severity | why-chain | management story | confidence. Dismissed flags stay visible with their dismissal reasons — the auditability of what was checked and cleared.}

## 8. Valuation & peers
{Historical multiple bands · full peer tables (domestic + international, with comparability deltas) · premium/discount analysis · what's-priced-in · valuation insights}

## 9. Estimates & valuation mechanics
{Driver tree · assumption ledger rendered · sanity gates shown · scenarios · variant view vs guidance/consensus · **driver-assumption table** (swing drivers × periods) · **sensitivity table** (EBITDA/EPS to each swing driver ±5/10% with elasticities) · **valuation bridge** (FY+2E EBITDA → EV → equity → fair-value context) beside the peer-multiple table · any driver bridge held out of the base with its in/out flag}

## 10. Thesis ledger (complete)
*Source: `state/thesis.json`, owned by module 33. The note compresses this to a rating-box line; the dossier is where the whole derivation stays auditable.*

**10.1 Return decomposition** — expected return, the split between metric growth and multiple change, `multiple_share_pct` against the `rerate_share_threshold_pct` gate, the valuation base year and the un-rolled comparison.

**10.2 Archetype selection** — the archetype chosen, the alternatives considered and rejected with reasons, and the skepticism weight applied.

**10.3 Must-be-true checklist (full)** — every condition with its status and evidence refs. Unlike the note, nothing is dropped for space.

| # | Condition | Status (established / partial / unestablished) | Evidence | Refs |
|---|---|---|---|---|

**10.4 Pillars** — each pillar with its ≥2 independent evidence refs.

**10.5 Monitorables** — each falsifier converted to a thresholded, dated monitorable.

**10.6 Rating derivation, step by step** — expected return → skepticism weight → red-flag and governance haircut → data-gap widening → the scale in `config.rating.scale`. Show each step's effect on the range, not only the conclusion.

## 11. Red-team ledger (complete)
*Source: `findings/thesis_redteam.json`, owned by module 34, run in a separate context. **The dossier is the complete auditable record, so the challenges belong here — the note surfaces only the verdict and the high-severity resolutions.***

**11.1 Verdict and rounds** — verdict, `material_challenges_count`, and rounds completed against `config.thesis.redteam_min_rounds`.

**11.2 The 15-check opinion/analysis audit** — every check from `docs/OPINION_VS_ANALYSIS.md` §4 with its verdict and evidence; a `fail` names the offending sentence or exhibit.

| # | Check | Verdict (pass / fail / n/a) | Evidence or offending text |
|---|---|---|---|

**11.3 Banned-reasoning scan** — each pattern found, quoted, with where it appears.

**11.4 Archetype failure-mode attack** — the archetype's standard failure mode applied to this company, and whether it lands.

**11.5 Steel-manned opposite rating** — the best case for the opposite call, argued properly rather than strawmanned.

**11.6 Pre-mortem** — the most likely path to being wrong.

**11.7 Peer-comparability audit** — whether the peer set survives the economic-comparability test (minority/JV structures, lease accounting, business mix).

**11.8 Challenge resolution table** — every material challenge with its severity and resolution. **An unresolved high-severity challenge is recorded as unresolved; it is never dropped.**

| # | Challenge | Severity | Resolution | Where answered |
|---|---|---|---|---|

## 12. Future outlook & monitorables
{Sector-playbook checkpoints · catalyst calendar · what-would-change-the-view}

## 13. Risk factors
{Industry / operational / financial / governance — probability-impact + mitigants}

## 14. Analyst's concluding synthesis
{Strengths vs vulnerabilities; ≤1 structural metaphor; no new facts}

## 15. Annexure (verbatim, unabridged)
{Complete standalone & consolidated statements · horizontal/vertical analysis · FCF calculations · all ratio tables}

## 16. Global source legend
{Every SRC id → original source; generated from the registry; deduplicated. Never cite an intermediate module as a source.}

## 17. Open questions & gaps register
{Every question: status, answer ref or disclosure. Convergence per CLAUDE.md requires that no open question of severity ≥ medium is left unanswered *or* that it is explicitly disclosed here.}

---
{templates/disclaimer.md verbatim}
