# Sector Pack — Infrastructure & Capital Goods *(tier 1 — routing family)*

*Tier 1 of two. **This pack routes; it does not analyse.** The tier-2 playbook in
`prompts/sector_playbooks/` carries the KPI table, the valuation convention, the exhibit set
and the forensic screens. Per `prompts/03`, **the playbook supersedes this pack wherever the
two differ.** Shared research rules: `prompts/31`. Routing source of truth:
`config/sector_registry.yaml`.*

**Family scope:** businesses that build, own or move infrastructure — EPC and construction,
electrical capital goods, real estate development, logistics, ports and aviation.

## What the whole family genuinely has in common

- **The balance sheet governs, not the P&L.** Reported revenue is a lagging, partly
  discretionary output of percentage-of-completion accounting. Working capital, mobilisation
  advances, retention money and contingent liabilities are where these businesses actually
  live or die. Read the balance sheet first, then the income statement — the reverse of the
  order that works for a consumer company.
- **Contracted future revenue is the asset, and its *quality* beats its size.** Order book,
  booking value, or a pipeline of concessions. In every child the same three questions apply:
  who is the counterparty and how fast do they pay, at what margin was it won, and how old is
  it. A large book of aged, low-margin, state-counterparty work is worse than a small clean one.
- **The government is customer, regulator and financier at once.** Budget capex, scheme
  pipelines, award rhythm around elections, and payment behaviour around fiscal year-end.
  Government-counterparty receivable days is a first-order variable, and it is seasonal.
- **Capital intensity and leverage cut both ways.** An asset-light claim must be verified in
  the balance sheet — contingent liabilities, SPV loans, equity commitments to concessions —
  not accepted from the strategy slide. Promoter pledging is chronic across this family and
  is a standing check.
- **Execution risk is the recurring failure mode.** Dates slip, costs overrun, and the whole
  thesis is often a commissioning or completion date. Compare the current plan against the
  company's own delivery record, not against its intentions.

## Child playbooks — select exactly one at triage (T2)

| Playbook | Covers | Unit lens |
|---|---|---|
| `epc_construction` | EPC contractors, HAM/BOT developers, construction | per project |
| `capital_goods_electrical` | transmission equipment, conductors, cables, transformers, switchgear | per tonne |
| `real_estate` | residential and commercial developers, annuity landlords | per square foot |
| `logistics` | road, rail, express, warehousing, ports, shipping, aviation | per tonne-km / per TEU |

**All four children are `status: authored`** (as of 2026-08-03), so triage resolves to a tier-2
playbook and that playbook governs. The degradation path survives only for future registry
additions: if a child is ever marked `status: pending`, analyse on this pack plus the closest
authored sibling, say in the note which convention you borrowed, and do **not** fall through to
`generic`.

## Preferred sources for this family

Company order-inflow and pre-sales disclosures, MoRTH/NHAI award data, Union and state budget
capex documents, CEA for power infrastructure, RERA filings for real estate, DGCA and port
throughput statistics, and rating-agency reports on group leverage. Per-child source notes
live in the playbook.
