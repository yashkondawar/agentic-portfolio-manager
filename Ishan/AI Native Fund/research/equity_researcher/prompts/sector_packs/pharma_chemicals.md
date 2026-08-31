<!-- GENERATED from registry/kpis + knowledge/references + research/equity_researcher/config/sector_registry.yaml — edit sources, then re-run scripts/gen_sector_packs.py -->
# Sector Pack — Pharma, Healthcare & Chemicals *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in `prompts/sector_playbooks/` carries the KPI table, the valuation convention, the divergence cases, the exhibit set and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the two differ.** Shared research rules: `prompts/31`. Routing source of truth: `config/sector_registry.yaml`.*

**Core truth:** Commodity generics erode; value accrues to complexity (injectables, biosimilars, validated specialty molecules) and to compliance track record. NPPA/NLEM caps the domestic price umbrella; USFDA status caps the US one.

## What the whole family has in common
- **Complexity moat**: manufacturing-process complexity; mix shift toward complex generics/injectables/biosimilars; CDMO/CRAMS depth — client validation cycles are switching costs.
- **Backward integration**: KSM/API self-sufficiency %, PLI benefit capture, China-dependence of inputs.
- **Compliance**: USFDA/EDQM/DCGI history per facility (warning letters, import alerts, OAI/VAI), quantified revenue at risk per facility, remediation credibility and management commentary.
- **Pipeline**: ANDA stock/flow, Paragraph-IV filings and success rate, first-to-file value; for specialty chem — molecules under multi-year contracts, clients' patent-cliff calendar.
- **China+1**: evidenced share shifts in CDMO/API sourcing (not just narrative).
- **Domestic**: NLEM exposure % of revenue, chronic vs acute mix, MR productivity; key chronic therapies dominating domestic sales and their growth stability.
- **US generics**: price-erosion rate trend from peer commentary.
- **Specialty chemicals**: active-principles focus and the nature of multi-year client validation moats (high switching costs).

## Child playbooks — select exactly one at triage (T2)

| Playbook | Routes on | Unit lens | Status |
|---|---|---|---|
| `pharma_generics` | abbreviated new drug application, para iv, first to file | per molecule | authored |
| `cdmo_cramps` | contract development and manufacturing, custom synthesis, cramps | per molecule | authored |
| `specialty_chemicals` | specialty chemical, agrochemical, soda ash | per tonne | authored |
| `hospitals` | arpob, average length of stay, occupied bed | per bed | authored |
| `diagnostics` | test volumes, realisation per test, patient volumes | per test | authored |

`Routes on` shows the first few routing keywords only; `config/sector_registry.yaml` carries the full list and is the source of truth. A company spanning two children is multi-segment: primary by largest EBIT, the other recorded as a `secondary_playbook`. If a child is ever marked `status: pending`, analyse on this pack plus the closest authored sibling, state in the note which convention you borrowed, and do **not** fall through to `generic`.

## Interpretation frame (family default)

Multiples: primary `pe_forward`; secondary `ev_ebitda_forward`, `sotp`; conditioned by `peer_set_choice`, `earnings_base_quality`, `growth_durability`.

These are the family-level defaults; the child playbook overrides them and carries the sub-sector's `## Divergence cases`. A conditioner names *which variable* makes a given multiple expensive or cheap — the same P/E supports opposite readings depending on it (`docs/OPINION_VS_ANALYSIS.md` §7).

## Governed KPI floor

The fund's governed KPI vocabulary for this sector is `registry/kpis/pharma_chemicals.yaml` — 29 KPIs across 8 categories (Core Valuation, Core Profitability, Balance Sheet, Growth, Cash Flow, Segment Mix, Operational Moats, Pipeline Regulatory). Read it via `registry.registry.Registry.load()`; it is never restated here, and the per-KPI detail belongs to the tier-2 playbook. `scripts/gen_sector_packs.py --check` reports any child playbook `signature_kpi` this vocabulary does not cover.

**Relative-valuation justifier:** Premium vs compliance cleanliness + high-margin mix (CDMO/specialty share) + pipeline optionality — a clean-facility CDMO deserves different math than a commodity-generic exporter; never blend them silently.

**Preferred sources:** USFDA inspection classification database, company facility disclosures, NPPA/NLEM lists, PLI notifications, IQVIA citations for domestic market shares.
