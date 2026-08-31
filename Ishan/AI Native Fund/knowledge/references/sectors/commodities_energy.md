# Commodities & Energy — Sector Playbook (metals, cement, oil & gas, power, CGD)

Synthesized superset of `registry/kpis/commodities_energy.yaml` and the
external ER project's commodities sector pack. KPI vocabulary:
`registry/kpis/commodities_energy.yaml`; deep KPI definitions:
`knowledge/data/kpis/micro/commodities_energy.yaml`. Sector cycle
indices: NIFTY METAL (primary), NIFTY ENERGY (secondary) — see
`config/settings.yaml -> sector_index_map`.

## Core truth

Players are price-takers; the only durable edge is cost-curve position.
Analyze the spread (realization - cost), not the price.

## Qualitative lenses

- **Cost-curve position**: global quartile (1st vs 3rd); what creates it
  (ore/coal captivity, energy mix, logistics, scale) and its durability;
  degree of integration (mine/well to finished product) against volatile
  intermediate Indian spot markets.
- **Integration**: captive mines/power quantified as a per-unit cost
  advantage vs peers; upstream/downstream balance.
- **Capital allocation**: peak-cycle behaviour — debt paydown vs
  expansion vs buybacks; count of cycle-top acquisitions in history (the
  imprudence marker).
- **Trade policy moat**: anti-dumping/safeguard duties, import-parity
  dynamics, and their expiry/renewal risk.
- **Demand linkage**: government capex/NIP for cement & steel; PPA terms
  and counterparty (SEB) quality for power; APM allocation vs market gas
  for CGD; Brent/cess sensitivity for upstream.
- **Cement specifically**: freight makes it hyper-local — regional
  pricing power, lead distances, clinker/grinding balance.
- **ESG/cost risk**: carbon-tax exposure, pollution-norm capex ahead and
  its impact on future cost structure.

## Cycle overlay

- **Valuation vs earnings cycle**: mid-cycle multiples on mid-cycle
  earnings, never peak-on-peak — the sector's biggest valuation trap.
  This sector is where the framework's commodity_cycle
  (`knowledge/data/cycles/catalog.yaml`) and sector_thematic_cycle
  overlap most directly; run both. NIFTY METAL / NIFTY ENERGY P/E history
  in `index_data` (2016-onward).
- **Parabolic Rule**: commodities are the asset class most prone to the
  Parabolic Return Compression Rule override — see
  `methodology/cycle_positioning_framework.md` section 3.
- **Credit/capex cycle**: expansion capex vs credit window; balance-sheet
  discipline (net debt/EBITDA trend) through the cycle.
- **Policy/profit cycle**: duty/tariff moat expiry risk, cess/windfall
  taxes for upstream.

## Niche pointers

- **City gas distribution**: impact of APM gas allocation (low-cost
  sourcing) on margins vs peers reliant on market gas.
- **Oil & gas upstream**: direct sensitivity of profitability to Brent
  and cess/tax regulatory changes; reserve replacement.

## Relative-valuation justifier

EV/EBITDA and P/B vs cost-curve position (EBITDA/unit) and balance-sheet
discipline (net debt/EBITDA) — mid-cycle multiples on mid-cycle earnings,
never peak-on-peak.

## Preferred sources

Exchange filings, PPAC/CEA/JPC industry stats, global price indices
(LME, Platts citations), company cost walks in decks.
