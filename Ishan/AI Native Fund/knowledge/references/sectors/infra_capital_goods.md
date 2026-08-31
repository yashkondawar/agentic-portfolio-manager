# Infrastructure & Capital Goods — Sector Playbook (EPC, construction, power equipment, rail/road)

Synthesized superset of `registry/kpis/infra_capital_goods.yaml` and the
external ER project's infra sector pack. KPI vocabulary:
`registry/kpis/infra_capital_goods.yaml`; deep KPI definitions:
`knowledge/data/kpis/micro/infra_capital_goods.yaml`. Sector cycle index:
NIFTY INFRASTRUCTURE — see `config/settings.yaml -> sector_index_map`.

## Core truth

The P&L is a lagging indicator; the balance sheet (working capital,
mobilization advances, retention money, contingent liabilities) is where
EPC companies live or die. Order book quality > order book size.

## Qualitative lenses

- **Execution moat**: completed-on-time track record, raw-material
  escalation clauses in contracts (commodity protection — verify presence
  AND effectiveness), site/labor mobilization scale.
- **Model check**: EPC (asset-light) vs BOT/HAM (capital-locked) mix —
  verify the *claimed* shift in the actual balance sheet (contingent
  liabilities, SPV loans, equity commitments to HAM projects). Hidden
  contingent liabilities from old BOT projects are the classic trap.
- **Order book quality**: counterparty split (central vs state vs private
  — state discoms/bodies are the slow payers), segment split
  (roads/power/water/rail), aging, margin cohort of recent wins —
  aggressive bidding cycles show up in margins 2 years later.
- **De-risking**: asset monetization (InvIT sales), debt trajectory,
  timely project commissioning, promoter pledge (chronic in this sector).
- **Government dependence**: budget capex trajectory, NIP/scheme
  pipelines, election-cycle award/execution rhythm; payment-cycle
  behaviour around fiscal year-end.
- **Counterparty risk**: SEB exposure on PPAs (power), MoD/railways
  payment terms — quantify receivable days by counterparty where
  disclosed.
- **Working-capital risk**: receivable days from slow-paying government
  bodies; price the working-capital lockup into the valuation, don't
  excuse it.

## Cycle overlay

- **Valuation vs earnings cycle**: is the premium justified by execution
  track record and WC discipline, or capex-cycle euphoria? Run the
  eight-phase read on NIFTY INFRASTRUCTURE P/E percentiles (`index_data`,
  2016-onward).
- **Capex/investment cycle**: this sector IS the capex cycle's
  idiosyncratic expression (`capex_investment_cycle` in
  `knowledge/data/cycles/catalog.yaml` anchors on order-book growth) —
  long and lumpy (~5-7yr cycles), lags GDP recovery, leads the next
  industrial-earnings cycle.
- **Credit/capex cycle**: funding needs vs the credit window; group
  leverage and promoter pledge as the credit-cycle stress channels.
- **Policy/profit cycle**: government-capex dependence is the direct
  policy-cycle exposure; election-cycle award rhythm.

## Niche pointers

- **Power / renewables**: SEB (discom) exposure and PPA counterparty risk
  as the single biggest operational risk.
- **Defense / railways**: predictable order flow vs slow payment /
  capital-intensity trade-off.

## Relative-valuation justifier

Premium vs WC discipline (receivable days), execution moat (book-to-bill
with on-time record), and de-risking progress (net debt/EBITDA trend) —
apply a working-capital-lockup haircut mentally before comparing P/Es.

## Preferred sources

Company order-inflow disclosures, MoRTH/NHAI award data, budget
documents, CEA for power, rating-agency reports on group leverage.
