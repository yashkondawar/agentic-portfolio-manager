# Generic — Sector Playbook (fallback for unclassified / conglomerate / niche sectors)

Synthesized superset of `registry/kpis/generic.yaml` and the external ER
project's generic sector pack. KPI vocabulary:
`registry/kpis/generic.yaml`; deep KPI definitions:
`knowledge/data/kpis/micro/generic.yaml`. Sector cycle index: NIFTY 500
(broad-market fallback) — see `config/settings.yaml -> sector_index_map`.

Use when no specialized playbook fits; borrow lenses and KPI rows from
the closest dedicated playbook for any sub-segment.

## First job: classify the business economically

Figure out what kind of business this economically is — asset-heavy
price-taker? brand/distribution compounder? contract/order-book executor?
regulated utility? platform/network? — then apply the matching lenses and
borrow the KPI rows from the corresponding sector playbook. State the
classification and why; the classification itself is a finding.

## Qualitative lenses

- **Competitive differentiation**: supply-chain/sourcing edges,
  proprietary tech, distribution (incl. Tier-2/3 penetration), regulatory
  positioning per key peer vs target.
- **Industry voice**: what competitor managements say about the
  industry's direction (latest transcripts/decks, tone noted) — cross-read
  with `methodology/buyside_depth.md`'s tone bridge.
- **Moat (India-specific)**: regulatory (PLI, licensing, tariffs) vs
  distribution vs switching-cost moats; sustainability of each.
- **Porter's five forces**: for each force, gather 2-3 cited evidence
  points supporting a high/medium/low-pressure rating — evidence, not
  vibes.
- **Industry economics**: demand drivers (macro/demographic/policy) with
  data; pricing determinants (inputs, FX, tariffs); pass-through vs
  operating-leverage character; sensitivity estimates.
- **Headwinds/tailwinds**: 3-5 recent (<=6 months) credible forecasts;
  leading indicators relevant to the sector (PMI, freight, credit growth,
  etc.).
- **India risk overlay**: electoral/policy exposure (sudden tax/subsidy
  changes), government-counterparty receivables.

## Cycle overlay

- **Valuation vs earnings cycle**: is the multiple gap vs peers explained
  by ROCE stability and leverage, or unexplained? Unexplained gaps are
  findings, not conclusions. Broad-market cycle read: NIFTY 500 P/E
  percentiles (`index_data`, full 2016-2026 history available).
- **Credit/capex cycle**: funding needs vs the credit window; FCF
  constraints and debt risk.
- **Policy/profit cycle**: regulatory-moat sustainability and
  government-receivable exposure.

## Sector-specific KPI discovery

Find at least 3 KPIs the industry itself tracks (ARPU, SSSG,
EBITDA/tonne, occupancy, realization/unit, ASK-CASK for airlines, ...) —
from company decks and industry reports; define each before using it.
This mirrors `registry/kpis/generic.yaml`'s `industry_specific_ratio_1-3`
placeholder slots.

## Relative-valuation justifier

Cheapness/expensiveness vs ROCE stability and leverage — explain the
multiple gap or flag it unexplained (unexplained gaps are findings, not
conclusions).
