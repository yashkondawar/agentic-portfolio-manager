# Sector Playbook — Power generation, transmission & distribution

*Tier 2. Family: `commodities_energy` (`prompts/sector_packs/commodities_energy.md`). Shared
rules: `prompts/31`.*
**Provenance:** corpus-grounded — NTPC (Axis Capital, Jan-24, 19pp, 33 exhibits — the corpus's
model regulated-utility SOTP), with Adani Green (JM Financial, Nov-25) for the contracted-IPP
comparison and Coal India (Anand Rathi, Apr-24) for the fuel chain. Transmission and distribution
content is domain-derived; the corpus has no standalone T&D-utility initiation (the T&D *equipment*
makers are covered by `capital_goods_electrical`).

## The economic engine
**This playbook covers three different businesses and the first analytical act is to say which one
you are looking at**, because they are valued on different metrics entirely:

1. **Regulated generation / transmission** — earns a **CERC-determined return on equity** (currently
   15.5% for generation, plus incentives) on an approved **regulated equity** base. Fuel and most
   costs pass through. **The business is not a commodity business at all; it is a growing annuity,
   and the driver is regulated-equity growth, not power prices.** Revenue ≈ regulated equity ×
   allowed RoE + incentives, subject to availability.
2. **Contracted IPP (merchant with PPAs)** — sells under long-term power purchase agreements at a
   fixed or indexed tariff. Earnings are contracted; the risks are counterparty payment, plant
   performance and refinancing.
3. **Merchant generation and distribution** — genuinely exposed to spot tariffs (IEX/DAM) or to
   retail-distribution economics (AT&C losses, tariff orders, subsidy receipt).

NTPC is the worked regulated case: thermal capacity "largely backed by long-term PPAs (usually up
to 25 years)", regulated equity growing at a **9% CAGR over FY23-26E**, RoE of 14.3-15.8%, and a
funding advantage of ~6% cost of debt against 7-9% for private peers on the back of its sovereign
rating. Note what is *absent* from that thesis: any view on the price of electricity.

**Availability, not output, drives regulated revenue.** Under the availability-based tariff, fixed
(capacity) charges are earned on declared availability; PLF drives only the variable/incentive
component. This is the single most misunderstood fact in the sector — **a regulated plant can have
low PLF and full fixed-cost recovery.** State which regime applies before treating PLF as the
revenue driver.

## Analysis sequence
1. **Classify every asset** into regulated / contracted-PPA / merchant, with capacity (MW) in each
   bucket. Then treat the company as a portfolio, because it is one.
2. **For regulated assets: the regulated-equity build.** Opening regulated equity, capitalisation
   added, the allowed RoE, incentives earned, and the growth pipeline. This is the entire earnings
   model and it is a capex schedule, not a market forecast.
3. **For contracted assets: the PPA book** — counterparty, tenure, tariff and its indexation,
   and the termination/change-in-law provisions. Adani Green's 81% of capacity under 25-year PPAs
   is the disclosure to look for.
4. **Counterparty and receivables.** This is where power investments actually fail. Receivable days
   from discoms, the ageing, LPS (late-payment surcharge) accrual, and participation in any
   central dues-clearance scheme. A regulated return you cannot collect is not a return.
5. **Plant performance** — availability/declared capacity first, then PLF, heat rate, auxiliary
   consumption, and forced-outage rate. NTPC's pithead plants running PLF above the all-India
   average is what converts into PLF-linked incentives.
6. **The fuel chain** — coal linkage vs e-auction vs imported, landed cost per tonne and per kWh,
   inventory in days, and the pass-through mechanism *and its lag*. Pass-through protects margin
   but not working capital.
7. **The renewable transition inside the company** — RE capacity built and targeted (NTPC: 60 GW
   by FY32), the capex, and whether it is funded by the regulated business's cash flow. This is
   usually where the multiple argument lives.
8. **Regulatory cycle position** — where the current CERC/SERC tariff period sits, what the next
   order could change, and any pending true-up or disallowance.
9. **Then value each bucket on its own convention, and sum.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **PLF** (plant load factor) | actual generation / maximum possible generation | % | **Read it against the tariff regime**: under ABT, fixed charges follow *availability*, and PLF drives incentives and variable recovery. NTPC's above-all-India PLF at pithead plants is an incentive story, not a revenue-existence story | CEA data, company decks |
| **Tariff** | revenue / units sold | INR/kWh | Split into fixed (capacity) and variable (energy) components; for merchant, against the IEX/DAM clearing price. A blended tariff hides the regulated/merchant mix | Tariff orders, P&L + volume |
| **Regulated equity** | approved equity base on which RoE is allowed | INR cr | **The earnings driver for a regulated utility.** Forecast it as a capitalisation schedule; NTPC's 9% CAGR (FY23-26E) *is* its earnings growth. Reconcile to the balance sheet's equity | CERC orders, company disclosure |
| **Receivable days from discoms** | receivables from distribution utilities / revenue × 365 | days | The sector's central credit risk. Read with the ageing and with the state discoms' own ACS-ARR gap. Improvement driven by a central liquidity scheme is not structural improvement | Balance sheet, decks |
| **PPA tenure** | weighted-average remaining life of power purchase agreements | years | The annuity's length, and the re-contracting cliff. A 25-year PPA at year 22 is a different asset from one at year 3 | PPA disclosures, AR |

## Supporting KPIs
Installed and commissioned capacity (MW) by asset, fuel and regime; capacity under construction
with commissioning dates; declared availability / plant availability factor; heat rate
(kcal/kWh); auxiliary power consumption %; specific coal consumption; forced-outage and planned-
outage rates; coal source mix and landed cost per tonne and per kWh; coal stock days; fuel cost
per kWh vs the pass-through allowed; allowed RoE and incentives earned vs allowed; capitalisation
added per year; capex per MW by technology; net debt and net debt/EBITDA; cost of debt (NTPC ~6%
vs 7-9% private peers — a genuine, quantified, sovereign-rating-derived advantage); interest cover;
LPS income; regulatory-deferral-account balances and pending true-ups; AT&C losses, billing and
collection efficiency for distribution; ACS-ARR gap and subsidy receivable for discoms;
transmission-line-availability % and elements commissioned for transmission utilities; RE capacity
and its share of total; ROE and ROCE by bucket; dividend payout (regulated utilities are yield
instruments and the payout is part of the return).

## Standard exhibit set
Capacity by asset, fuel and regime (regulated / contracted / merchant) · regulated-equity build
with capitalisation added by year · allowed vs earned RoE with incentives · PLF and availability
against the all-India average, by plant · tariff decomposed into fixed and variable · fuel cost
per kWh against the allowed pass-through · coal source mix and stock days · **receivable days from
discoms with ageing, plus the state-wise exposure** · PPA book by counterparty, tenure and tariff ·
capacity pipeline with capex per MW and commissioning dates · RE capacity trajectory against the
target · cost of debt vs private peers · net debt/EBITDA and interest cover · regulatory
true-up/deferral balances · P/B against regulated equity for the regulated bucket · EV/EBITDA and
EV per MW for the merchant/IPP bucket · **the SOTP table itself** · dividend yield vs bond yield.

## Valuation convention
**SOTP, valuing each bucket on its own metric — this is the sector's correct default and the
corpus's worked example.** NTPC (Axis Capital) values "the company's conventional thermal business
at **1.8x P/BV on its FY26 consolidated regulated BV**" and "its RE business at **EV/EBITDA of 12x**
on FY26 EBITDA", summing to a TP of INR 345.

That structure is right for a reason worth stating in the note: **a regulated asset is a bond-like
annuity whose value is a function of the allowed RoE against the cost of equity**, so P/B on
*regulated* book (not reported book) is the natural metric — a plant earning an allowed 15.5% RoE
against a ~12% cost of equity is worth roughly 1.3x its regulated equity, and any premium beyond
that must come from growth in the regulated base or from incentives. A merchant or RE asset, by
contrast, has no allowed return and is valued on cash flow: DCF or EV/EBITDA, with EV per MW as
the cross-check against replacement cost.

For distribution, value on the regulatory-asset-base and the tariff-order trajectory, and treat
AT&C-loss reduction as the only real operating lever.

*Traps:* (i) **applying one multiple to a mixed portfolio** — the single biggest error here;
(ii) treating PLF as the revenue driver under an availability-based regime; (iii) using reported
book value where regulated book is the base — they differ, sometimes materially; (iv) capitalising
a merchant tariff spike (the IEX summer peaks are not a run-rate); (v) crediting regulated-equity
growth from a capex plan whose clearances or funding are not in place; (vi) ignoring the discom
receivable, which is the difference between an accounting return and a cash one; (vii) valuing an
RE arm at a growth multiple while it is funded by the regulated business's dividends.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. The thermal business is valued at 1.8x P/BV.**
- *Expensive for a thermal generator* (`peer_set_choice`) — a declining asset class.
- *Arithmetically anchored* (`sustainable_roe`) — a regulated asset is a bond-like annuity
  whose value is the allowed RoE against the cost of equity. A plant earning an allowed
  15.5% against a ~12% cost of equity is worth roughly 1.3x its *regulated* equity, so 1.8x
  is a claim that needs the excess explained — incentives, availability, untied capacity.
  NTPC (Axis Capital) is published this way.
- *Discriminator* (`disclosed_mechanism`) — the allowed RoE, the regulated equity base (not
  reported book), and the incentive and plant-availability adders.

**2. A single blended P/B is applied to the company.**
- *One company, one multiple* (`peer_set_choice`).
- *Two different assets* (`terminal_value_share`) — NTPC values conventional thermal at 1.8x
  P/BV on FY26 consolidated regulated BV and the RE business at 12x EV/EBITDA on FY26
  EBITDA, summing to a TP of INR 345. A regulated annuity and a growth platform do not share
  a metric, let alone a multiple.
- *Discriminator* (`disclosed_mechanism`) — segment-level regulated equity and segment
  EBITDA, each anchored to its own peer set.

## Forensic screens (sector-specific)
- **Receivable days improving because of a central liquidity/dues scheme** rather than discom
  health — check whether the improvement is a one-time settlement.
- Regulatory deferral accounts and unbilled revenue growing — revenue recognised ahead of a tariff
  approval that may be disallowed or trued-up down.
- Late-payment-surcharge income booked as revenue while the underlying principal remains
  uncollected.
- Capitalisation of a project (and therefore entry into regulated equity) claimed before the
  CoD/commissioning certification, or interest-during-construction capitalised past CoD.
- Capital cost claimed above the CERC norm, pending disallowance, not disclosed as a risk.
- PLF or availability quoted on a favourable subset of plants; forced outages excluded.
- Fuel cost under-recovery accumulating where the pass-through lags, presented as a timing item
  when it is a disallowance risk.
- Coal stock days falling to critical levels — a production risk hidden in working capital.
- Merchant sales in a spike quarter extrapolated; merchant and regulated revenue not separated.
- Subsidiary/SPV debt and equity commitments to under-construction assets kept off the parent's
  net-debt discussion; contingent liabilities on SPV guarantees.
- Related-party EPC or O&M contracts with the promoter group (endemic in private power).
- Renewable capacity announced in GW with no land, evacuation or PPA tie-up disclosed.

## Dependencies to map
CERC and state SERC tariff regulations — the allowed RoE, the tariff-period cycle, incentive and
availability norms, and any pending true-up · CEA data for national capacity, PLF and demand ·
coal availability: Coal India production and dispatch, linkage auctions, e-auction premia, imported
coal parity and rail logistics · discom financial health (ACS-ARR gap, UDAY/RDSS scheme
performance) and state subsidy behaviour — the receivable's ultimate driver · Electricity Act
amendments and the recurring distribution-privatisation debate · renewable purchase obligations,
ISTS waiver timelines and their expiry, ALMM · IEX/DAM and real-time-market prices, plus price
caps · carbon pricing, the Carbon Credit Trading Scheme, and emission-norm (FGD) capex mandates
and their repeatedly extended deadlines · interest rates (these are levered annuity assets, so the
equity is rate-sensitive) · land acquisition and environmental clearance for the pipeline.

## Common archetypes here
`capex-to-cashflow` (the regulated-equity growth story — the sector's dominant and most defensible
archetype, because the driver is a capitalisation schedule rather than a price forecast),
`regulatory-tailwind` or its inverse (a tariff order can make or unmake the thesis),
`balance-sheet-repair` and `turnaround` for stressed IPPs, `re-rating` where a thermal utility is
argued to deserve a higher multiple for its renewable pivot — **apply the 40% rule, because this is
usually a multiple argument dressed as a growth argument** — and `deep-value-sotp` where the market
prices a mixed portfolio on the worst bucket's multiple. `cyclical-peak` applies to merchant
exposure only.
