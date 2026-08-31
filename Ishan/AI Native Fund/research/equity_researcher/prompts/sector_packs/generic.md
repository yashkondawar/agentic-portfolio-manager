<!-- GENERATED from registry/kpis + knowledge/references + research/equity_researcher/config/sector_registry.yaml — edit sources, then re-run scripts/gen_sector_packs.py -->
# Sector Pack — Generic / conglomerate / uncovered *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in `prompts/sector_playbooks/` carries the KPI table, the valuation convention, the divergence cases, the exhibit set and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the two differ.** Shared research rules: `prompts/31`. Routing source of truth: `config/sector_registry.yaml`.*

## What the whole family has in common
- **Competitive differentiation**: supply-chain/sourcing edges, proprietary tech, distribution (incl. Tier-2/3 penetration), regulatory positioning per key peer vs target.
- **Industry voice**: what competitor managements say about the industry's direction (latest transcripts/decks, tone noted) — cross-read with `knowledge/references/methodology/buyside_depth.md`'s tone bridge.
- **Moat (India-specific)**: regulatory (PLI, licensing, tariffs) vs distribution vs switching-cost moats; sustainability of each.
- **Porter's five forces**: for each force, gather 2-3 cited evidence points supporting a high/medium/low-pressure rating — evidence, not vibes.
- **Industry economics**: demand drivers (macro/demographic/policy) with data; pricing determinants (inputs, FX, tariffs); pass-through vs operating-leverage character; sensitivity estimates.
- **Headwinds/tailwinds**: 3-5 recent (<=6 months) credible forecasts; leading indicators relevant to the sector (PMI, freight, credit growth, etc.).
- **India risk overlay**: electoral/policy exposure (sudden tax/subsidy changes), government-counterparty receivables.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Routes on | Unit lens | Status |
|---|---|---|---|
| `generic` | — | — | authored |

`Routes on` shows the first few routing keywords only; `config/sector_registry.yaml` carries the full list and is the source of truth. A company spanning two children is multi-segment: primary by largest EBIT, the other recorded as a `secondary_playbook`. If a child is ever marked `status: pending`, analyse on this pack plus the closest authored sibling, state in the note which convention you borrowed, and do **not** fall through to `generic`.

## Interpretation frame (family default)

Multiples: primary `pe_forward`; secondary `ev_ebitda_forward`, `sotp`, `dcf`; conditioned by `peer_set_choice`, `own_history_anchor`, `earnings_base_quality`.

These are the family-level defaults; the child playbook overrides them and carries the sub-sector's `## Divergence cases`. A conditioner names *which variable* makes a given multiple expensive or cheap — the same P/E supports opposite readings depending on it (`docs/OPINION_VS_ANALYSIS.md` §7).

## Governed KPI floor

The fund's governed KPI vocabulary for this sector is `registry/kpis/generic.yaml` — 31 KPIs across 7 categories (Valuation, Profitability, Balance Sheet, Growth, Cash Flow, Cash Flow Quality, Sector Specific). Read it via `registry.registry.Registry.load()`; it is never restated here, and the per-KPI detail belongs to the tier-2 playbook. `scripts/gen_sector_packs.py --check` reports any child playbook `signature_kpi` this vocabulary does not cover.

**Relative-valuation justifier:** Cheapness/expensiveness vs ROCE stability and leverage — explain the multiple gap or flag it unexplained (unexplained gaps are findings, not conclusions).
