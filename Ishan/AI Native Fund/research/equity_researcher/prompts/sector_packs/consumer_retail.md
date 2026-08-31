<!-- GENERATED from registry/kpis + knowledge/references + research/equity_researcher/config/sector_registry.yaml — edit sources, then re-run scripts/gen_sector_packs.py -->
# Sector Pack — Consumer, Retail & Hospitality *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in `prompts/sector_playbooks/` carries the KPI table, the valuation convention, the divergence cases, the exhibit set and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the two differ.** Shared research rules: `prompts/31`. Routing source of truth: `config/sector_registry.yaml`.*

**Core truth:** The moat is distribution + brand; the P&L tell is gross-margin stability through input cycles (pricing power) and the split of growth between volume and premiumization.

## What the whole family has in common
- **Pricing power**: GM expansion/hold through commodity cycles; price-hike absorption evidence; consumer elasticity by category.
- **Distribution moat**: rural reach, direct-coverage outlets, last-mile efficiency; Q-commerce/DTC success and cannibalization risk vs GT/MT; sustainability of the moat as channels shift.
- **Volume vs premiumization**: which is driving value growth per peer; new-category success rates.
- **Monsoon & rural**: correlate FMCG peer sales with Southwest Monsoon data, MSP/farm-income, and consumption sentiment where the mix is rural-heavy.
- **Rivalry read (Porter's)**: A&P intensity trend, discounting behaviour, private-label/D2C insurgent pressure; bargaining power of suppliers (agri-commodities, crude derivatives) on COGS.
- **Brand strength / DTC**: DTC success and cannibalization risk between online and traditional retail channels.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Routes on | Unit lens | Status |
|---|---|---|---|
| `fmcg` | general trade, modern trade, direct reach | per case | authored |
| `apparel_grocery_retail` | same store sales growth, like for like sales, revenue per square feet | per store | authored |
| `qsr` | average daily sales, same store sales growth, dine-in | per store | authored |
| `hotels` | average room rate, revpar, room nights | per key | authored |

`Routes on` shows the first few routing keywords only; `config/sector_registry.yaml` carries the full list and is the source of truth. A company spanning two children is multi-segment: primary by largest EBIT, the other recorded as a `secondary_playbook`. If a child is ever marked `status: pending`, analyse on this pack plus the closest authored sibling, state in the note which convention you borrowed, and do **not** fall through to `generic`.

## Interpretation frame (family default)

Multiples: primary `pe_forward`; secondary `ev_ebitda_forward`, `dcf`; conditioned by `growth_durability`, `incremental_roce`, `accounting_basis`.

These are the family-level defaults; the child playbook overrides them and carries the sub-sector's `## Divergence cases`. A conditioner names *which variable* makes a given multiple expensive or cheap — the same P/E supports opposite readings depending on it (`docs/OPINION_VS_ANALYSIS.md` §7).

## Governed KPI floor

The fund's governed KPI vocabulary for this sector is `registry/kpis/consumer_retail.yaml` — 31 KPIs across 9 categories (Core Valuation, Core Profitability, Working Capital, Cash Flow, Cash Flow Quality, Growth, Consumption, Retail Qsr, Durables Discretionary). Read it via `registry.registry.Registry.load()`; it is never restated here, and the per-KPI detail belongs to the tier-2 playbook. `scripts/gen_sector_packs.py --check` reports any child playbook `signature_kpi` this vocabulary does not cover.

**Relative-valuation justifier:** Premium/discount vs GM stability (pricing power) and distribution-driven ROCE stability.

**Preferred sources:** Company decks/transcripts, NielsenIQ/Kantar citations in press, IMD monsoon data, state excise policies (liquor), Screener/Tickertape for peer financials.
