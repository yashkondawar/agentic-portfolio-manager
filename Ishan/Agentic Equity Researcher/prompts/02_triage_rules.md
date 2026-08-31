# Triage Rules — rule-based branching (run once after intake; re-run only if intake changes)

Purpose: make the "dynamic, not a flow" ordering **explainable**. Each decision below records: rule id, inputs examined, decision, reason — into `state/triage.json` and `state/run_log.md`.

## T1. Input inventory classification

Classify every file in `input/<TICKER>/` into: `annual_report`, `quarterly_result`, `transcript`, `presentation`, `deep_research_prior` (DR1/DR2-style outputs supplied by user), `peer_material`, `kpi_data`, `other_disclosure`. Extract fiscal period from content, not filename, when ambiguous.
- If prior deep research exists → mark corresponding research tasks `prefilled`; deep-researcher only validates freshness (> 6 months old → refresh headline numbers) and fills gaps. **Do not redo supplied research.**
- Ideal set is 5 ARs / 6 quarterlies / 5 transcripts / 5 presentations, but run with whatever exists; list shortfalls in `manifest.json.gaps` (they become report disclosures, not blockers).

## T2. Sector classification — family + playbook, with a confidence score

**Read `config/sector_registry.yaml`. It is the single source of truth for routing.** Do not
use a hardcoded keyword list; the registry's `families` and `playbooks` (with their
`keywords`, `signature_kpis` and `unit_denominator`) are what you classify against. Run
`python tools/validate_sector_registry.py` if anything looks inconsistent.

The registry carries only what a machine routes or checks on. The **valuation convention,
analysis sequence, exhibit set and forensic screens live in the playbook file**
(`prompts/sector_playbooks/<slug>.md`) — classification does not need them, and downstream
modules read them there.

From the latest AR business description + segment note, produce:

```json
{ "family": "<one of registry.families>",
  "playbook": "<one of registry.playbooks, or null>",
  "playbook_status": "authored | pending",
  "confidence": "high | medium | low",
  "matched_keywords": ["..."],
  "rejected_alternatives": [{"playbook": "...", "why_not": "..."}],
  "secondary_playbooks": ["..."] }
```

**Confidence rules.** `high` = ≥3 distinct registry keywords matched, all pointing to one
playbook. `medium` = 1–2 keywords, or matches across two playbooks within the same family.
`low` = no keyword match (falls to the family's generic handling) or matches spanning two
*families*. **Record `low` honestly** — a confidently wrong classification routes the whole
run down the wrong KPI tree, and the registry header documents how that happens.

**Playbook resolution.** If the matched playbook is `status: authored`, load
`prompts/sector_playbooks/<slug>.md` — it supersedes the family pack wherever the two
differ. If `status: pending`, fall back to the family pack and note the degradation; do
**not** fall through to `generic` merely because the deep playbook is unwritten.

**BFSI fork.** `family: bfsi` sets `bfsi_statements: true` → extraction uses the BFSI
addendum in `prompts/10`; `compute_ratios.py` skips the ratios named in the registry's
`skip_ratios`.

**Multi-segment company.** Primary = the playbook of the largest-EBIT segment; list the
others as `secondary_playbooks`. Deep research applies the primary playbook fully and pulls
only the KPI table from the secondaries.

**T2-RECHECK (mandatory).** After module 03 writes `state/business_model.json`, re-run this
classification against the value chain and revenue mix that module actually found, and
compare with the first pass. Previously the sector was decided once from a keyword scan and
never revisited, so a bad call was unrecoverable. If the recheck disagrees, or if the first
pass was `confidence: low`, adopt the recheck, log both decisions with reasons in
`state/run_log.md`, and mark the KPI tree stale so `compute_kpis.py` re-runs.

## T3. Research order (the architecture decision)

- **R-PURE**: exactly 1 reportable segment AND revenue mix stable (largest segment ≥ 85% of revenue in each of last 3 FYs) AND no M&A/demerger/large capex-driven new line in last 2 years → industry is already known ⇒ **launch DR2 (sector/peers) immediately, in parallel with extraction.** DR1 (company/management) launches with it.
- **R-SEGMENT**: segment count > 1 OR mix shift > 5pp YoY OR M&A/demerger/carve-out in last 2 years → **extraction first**, build the segment map, then branch DR2 per active segment (primary pack + secondary KPI pulls). DR1 can still start immediately (management background does not depend on segments).
- **R-PIVOT**: strategy pivot signals (new segment announced in transcripts, > 30% capex into a new line) → after extraction, run DR2 for BOTH legacy and target industry; weight by capital allocation, not current revenue.

## T4. Basis (standalone vs consolidated)

Both extracted when both published. Primary basis for analysis/valuation = consolidated when subsidiaries are material (subsidiary revenue > 10% of consolidated or explicit holding structure); else standalone. Record choice + reason; the standalone-vs-consolidated comparison table is mandatory either way.

## T5. Market data

If ticker resolvable → `tools/market_data.py` at intake (always; it feeds euphoria/panic signals, FY-average prices, mcap history for the historical-multiples table). Not resolvable/offline → open question `severity: high` routed to deep research with explicit warning that web-sourced prices are second-best evidence.

## T6. Peer seed list

Peers named in provided documents (AR competition section, presentations, prior research) → seed list with sources. DR2 extends to ≤ 8 domestic + ≤ 8 international comparable-by-business-model; every addition records query + source + retrieval date; business-model deltas vs target noted per peer.

## T7. Data mode (sparse vs normal)
Set `data_mode` from the manifest: `sparse` when the document set is thin (e.g. ≤2 annual reports, or only a few quarterlies, or a single AR + a deck, with no transcript history / peer material / prior DR); else `normal`. `sparse` selects the branch in `prompts/70_sparse_data_playbook.md` — same structure, more weight on the business-model spine + external anchoring, estimates published as a confidence-capped range. Record the trigger.

## T8. Dispatch the business-model map (module 03) — do this EARLY
Immediately after triage (before the deep analysis wave), dispatch `prompts/03_business_model_and_value_chain.md` → `state/business_model.json` (value-chain map + company-specific KPI tree + unit economics + swing drivers + net-long/short + research seeds). This artifact steers extraction depth, the `compute_kpis.py` KPI computer, DR2's research seeds, and the report's exhibits. It is the single highest-leverage step (see `docs/PROCESS_V2_REIMAGINED.md`); do NOT defer value-chain thinking to the research wave. It is cheap (~1 sonnet pass on the latest AR's business/segment/MD&A sections) and pays for itself downstream. In `sparse` mode it matters MORE, not less — it is built from first principles + one AR.
