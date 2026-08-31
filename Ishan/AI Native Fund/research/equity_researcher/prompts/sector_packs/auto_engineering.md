<!-- GENERATED from registry/kpis + knowledge/references + research/equity_researcher/config/sector_registry.yaml — edit sources, then re-run scripts/gen_sector_packs.py -->
# Sector Pack — Autos, Engineering & Manufacturing *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in `prompts/sector_playbooks/` carries the KPI table, the valuation convention, the divergence cases, the exhibit set and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the two differ.** Shared research rules: `prompts/31`. Routing source of truth: `config/sector_registry.yaml`.*

**Core truth:** Deeply cyclical with operating leverage — CV volumes proxy GDP/freight, PV volumes proxy consumer credit & sentiment, 2W volumes proxy rural cash flow. The margin story is utilization x commodity lag x mix.

## What the whole family has in common
- **Cycle position**: where each sub-segment is (CV/PV/2W/tractor), dealer inventory levels vs norms, registration (VAHAN) vs wholesale divergence — the classic early warning of channel stuffing.
- **Operating leverage**: plant utilization/capacity, break-even proxy, incremental margin history through the last cycle.
- **Commodity sensitivity**: steel/aluminum lag pass-through mechanics per peer (quarterly lag clauses vs spot exposure).
- **EV transition (mandatory sensitivity)**: ICE-exposure of the portfolio; EV content-per-vehicle delta (is the peer's part worth more or less in an EV?); credible EV wins vs press releases; FAME/PLI subsidy dependence of demand, especially 2W/3W; long-term impact on revenue mix and cost structure of component suppliers.
- **Defense/rail (if applicable)**: indigenization-list moat vs MoD receivable days; order-inflow lumpiness, execution ramp credibility.
- **Ancillaries**: platform concentration, export content, tooling amortization; scrappage-policy effect on replacement demand; component-localization policy effect on input costs and supply-chain resilience.
- **Macro linkage**: CV sales as GDP/freight proxy, PV sales linkage to consumer credit access and sentiment — this is a two-way street: the sector is also an input INTO the GDP/business cycle read.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Routes on | Unit lens | Status |
|---|---|---|---|
| `auto_oem` | society of indian automobile manufacturers, vahan portal, passenger vehicle volume | per vehicle | authored |
| `auto_ancillary` | content per vehicle, kit value, platform win | per vehicle | authored |
| `electronics_manufacturing` | electronics manufacturing services, original design manufacturer, printed circuit board assembly | per unit | authored |
| `defence_manufacturing` | indigenisation list, ministry of defence, offset obligation | per order | authored |

`Routes on` shows the first few routing keywords only; `config/sector_registry.yaml` carries the full list and is the source of truth. A company spanning two children is multi-segment: primary by largest EBIT, the other recorded as a `secondary_playbook`. If a child is ever marked `status: pending`, analyse on this pack plus the closest authored sibling, state in the note which convention you borrowed, and do **not** fall through to `generic`.

## Interpretation frame (family default)

Multiples: primary `pe_forward`; secondary `ev_ebitda_forward`, `sotp`, `peg`; conditioned by `cycle_position`, `growth_durability`, `incremental_roce`.

These are the family-level defaults; the child playbook overrides them and carries the sub-sector's `## Divergence cases`. A conditioner names *which variable* makes a given multiple expensive or cheap — the same P/E supports opposite readings depending on it (`docs/OPINION_VS_ANALYSIS.md` §7).

## Governed KPI floor

The fund's governed KPI vocabulary for this sector is `registry/kpis/auto_engineering.yaml` — 30 KPIs across 9 categories (Core Valuation, Core Profitability, Efficiency, Growth, Cash Flow, Cash Flow Quality, Volume Mix, Ancillary, Receivables Debt). Read it via `registry.registry.Registry.load()`; it is never restated here, and the per-KPI detail belongs to the tier-2 playbook. `scripts/gen_sector_packs.py --check` reports any child playbook `signature_kpi` this vocabulary does not cover.

**Relative-valuation justifier:** Premium vs cycle timing (leading vs lagging volume growth), operating-leverage headroom (utilization), and EV-transition hedge (CPV in EVs) — cyclicals get peak multiples on trough earnings, not the reverse; state where we are.

**Preferred sources:** SIAM/FADA/VAHAN data, company monthly volume disclosures, MoD/MoRTH announcements, steel/aluminum indices.
