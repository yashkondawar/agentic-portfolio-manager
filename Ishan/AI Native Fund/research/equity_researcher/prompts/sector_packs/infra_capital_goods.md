<!-- GENERATED from registry/kpis + knowledge/references + research/equity_researcher/config/sector_registry.yaml — edit sources, then re-run scripts/gen_sector_packs.py -->
# Sector Pack — Infrastructure & Capital Goods *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in `prompts/sector_playbooks/` carries the KPI table, the valuation convention, the divergence cases, the exhibit set and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the two differ.** Shared research rules: `prompts/31`. Routing source of truth: `config/sector_registry.yaml`.*

**Core truth:** The P&L is a lagging indicator; the balance sheet (working capital, mobilization advances, retention money, contingent liabilities) is where EPC companies live or die. Order book quality > order book size.

## What the whole family has in common
- **Execution moat**: completed-on-time track record, raw-material escalation clauses in contracts (commodity protection — verify presence AND effectiveness), site/labor mobilization scale.
- **Model check**: EPC (asset-light) vs BOT/HAM (capital-locked) mix — verify the *claimed* shift in the actual balance sheet (contingent liabilities, SPV loans, equity commitments to HAM projects). Hidden contingent liabilities from old BOT projects are the classic trap.
- **Order book quality**: counterparty split (central vs state vs private — state discoms/bodies are the slow payers), segment split (roads/power/water/rail), aging, margin cohort of recent wins — aggressive bidding cycles show up in margins 2 years later.
- **De-risking**: asset monetization (InvIT sales), debt trajectory, timely project commissioning, promoter pledge (chronic in this sector).
- **Government dependence**: budget capex trajectory, NIP/scheme pipelines, election-cycle award/execution rhythm; payment-cycle behaviour around fiscal year-end.
- **Counterparty risk**: SEB exposure on PPAs (power), MoD/railways payment terms — quantify receivable days by counterparty where disclosed.
- **Working-capital risk**: receivable days from slow-paying government bodies; price the working-capital lockup into the valuation, don't excuse it.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Routes on | Unit lens | Status |
|---|---|---|---|
| `epc_construction` | order book, order inflow, book to bill | per project | authored |
| `capital_goods_electrical` | transmission and distribution, conductor, transformer | per tonne | authored |
| `real_estate` | pre-sales, booking value, saleable area | per square foot | authored |
| `logistics` | tonne kilometre, fleet utilisation, warehousing space | per tonne km or per teu | authored |

`Routes on` shows the first few routing keywords only; `config/sector_registry.yaml` carries the full list and is the source of truth. A company spanning two children is multi-segment: primary by largest EBIT, the other recorded as a `secondary_playbook`. If a child is ever marked `status: pending`, analyse on this pack plus the closest authored sibling, state in the note which convention you borrowed, and do **not** fall through to `generic`.

## Interpretation frame (family default)

Multiples: primary `sotp`; secondary `pe_executed_earnings`, `nav_gav`, `ev_ebitda_forward`; conditioned by `balance_sheet_risk`, `earnings_base_quality`, `terminal_value_share`.

These are the family-level defaults; the child playbook overrides them and carries the sub-sector's `## Divergence cases`. A conditioner names *which variable* makes a given multiple expensive or cheap — the same P/E supports opposite readings depending on it (`docs/OPINION_VS_ANALYSIS.md` §7).

## Governed KPI floor

The fund's governed KPI vocabulary for this sector is `registry/kpis/infra_capital_goods.yaml` — 30 KPIs across 10 categories (Core Valuation, Core Profitability, Balance Sheet, Growth, Cash Flow, Cash Flow Quality, Execution Risk, Execution Visibility, Risk Management, Segment Specific). Read it via `registry.registry.Registry.load()`; it is never restated here, and the per-KPI detail belongs to the tier-2 playbook. `scripts/gen_sector_packs.py --check` reports any child playbook `signature_kpi` this vocabulary does not cover.

**Relative-valuation justifier:** Premium vs WC discipline (receivable days), execution moat (book-to-bill with on-time record), and de-risking progress (net debt/EBITDA trend) — apply a working-capital-lockup haircut mentally before comparing P/Es.

**Preferred sources:** Company order-inflow disclosures, MoRTH/NHAI award data, budget documents, CEA for power, rating-agency reports on group leverage.
