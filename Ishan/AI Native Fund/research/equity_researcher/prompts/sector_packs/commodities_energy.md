<!-- GENERATED from registry/kpis + knowledge/references + research/equity_researcher/config/sector_registry.yaml — edit sources, then re-run scripts/gen_sector_packs.py -->
# Sector Pack — Commodities, Energy & Utilities *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in `prompts/sector_playbooks/` carries the KPI table, the valuation convention, the divergence cases, the exhibit set and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the two differ.** Shared research rules: `prompts/31`. Routing source of truth: `config/sector_registry.yaml`.*

**Core truth:** Players are price-takers; the only durable edge is cost-curve position. Analyze the spread (realization - cost), not the price.

## What the whole family has in common
- **Cost-curve position**: global quartile (1st vs 3rd); what creates it (ore/coal captivity, energy mix, logistics, scale) and its durability; degree of integration (mine/well to finished product) against volatile intermediate Indian spot markets.
- **Integration**: captive mines/power quantified as a per-unit cost advantage vs peers; upstream/downstream balance.
- **Capital allocation**: peak-cycle behaviour — debt paydown vs expansion vs buybacks; count of cycle-top acquisitions in history (the imprudence marker).
- **Trade policy moat**: anti-dumping/safeguard duties, import-parity dynamics, and their expiry/renewal risk.
- **Demand linkage**: government capex/NIP for cement & steel; PPA terms and counterparty (SEB) quality for power; APM allocation vs market gas for CGD; Brent/cess sensitivity for upstream.
- **Cement specifically**: freight makes it hyper-local — regional pricing power, lead distances, clinker/grinding balance.
- **ESG/cost risk**: carbon-tax exposure, pollution-norm capex ahead and its impact on future cost structure.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Routes on | Unit lens | Status |
|---|---|---|---|
| `ferrous_non_ferrous_metals` | ebitda per tonne, cost of production per tonne, realisation per tonne | per tonne | authored |
| `cement` | clinker, grinding capacity, lead distance | per tonne | authored |
| `power_utilities` | plant load factor, power purchase agreement, merchant tariff | per mw | authored |
| `renewables` | capacity utilisation factor, solar module, wafer | per watt or per mw | authored |
| `oil_gas_cgd` | gross refining margin, crack spread, apm gas | per scm or per barrel | authored |

`Routes on` shows the first few routing keywords only; `config/sector_registry.yaml` carries the full list and is the source of truth. A company spanning two children is multi-segment: primary by largest EBIT, the other recorded as a `secondary_playbook`. If a child is ever marked `status: pending`, analyse on this pack plus the closest authored sibling, state in the note which convention you borrowed, and do **not** fall through to `generic`.

## Interpretation frame (family default)

Multiples: primary `ev_ebitda_midcycle`; secondary `ev_per_tonne`, `sotp`, `replacement_cost`; conditioned by `cycle_position`, `capital_intensity`, `earnings_base_quality`.

These are the family-level defaults; the child playbook overrides them and carries the sub-sector's `## Divergence cases`. A conditioner names *which variable* makes a given multiple expensive or cheap — the same P/E supports opposite readings depending on it (`docs/OPINION_VS_ANALYSIS.md` §7).

## Governed KPI floor

The fund's governed KPI vocabulary for this sector is `registry/kpis/commodities_energy.yaml` — 30 KPIs across 9 categories (Core Valuation, Core Profitability, Balance Sheet, Growth, Cash Flow, Cash Flow Quality, Cost Curve, Integration, Oil Gas). Read it via `registry.registry.Registry.load()`; it is never restated here, and the per-KPI detail belongs to the tier-2 playbook. `scripts/gen_sector_packs.py --check` reports any child playbook `signature_kpi` this vocabulary does not cover.

**Relative-valuation justifier:** EV/EBITDA and P/B vs cost-curve position (EBITDA/unit) and balance-sheet discipline (net debt/EBITDA) — mid-cycle multiples on mid-cycle earnings, never peak-on-peak.

**Preferred sources:** Exchange filings, PPAC/CEA/JPC industry stats, global price indices (LME, Platts citations), company cost walks in decks.
