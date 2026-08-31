# Sector Playbook — Ferrous & non-ferrous metals

*Tier 2. Family: `commodities_energy` (`prompts/sector_packs/commodities_energy.md`). Shared
rules: `prompts/31`.*
**Provenance:** corpus-grounded — NALCO (Emkay Global, Jan-16 — also the single note that
`docs/PROCESS_V2_REIMAGINED.md` was reverse-engineered from, and the ticker this repo's own
`workspace/NALCO/` run covers), Gravita India (ICICI Securities, May-24 and JM Financial, Mar-26
— secondary/recycled metals), Coal India (Anand Rathi, Apr-24).

## The economic engine
A metals producer is a **price-taker converting ore and energy into a globally priced commodity**.
It cannot influence its output price, so it has exactly one lever — the cost of making a tonne —
and one exogenous variable — the price of selling it:

`EBITDA = volume × (realisation per tonne − cash cost per tonne)`

Everything analytically important follows from that:

- **Cost-curve position is the only durable edge**, and it comes from integration rather than
  skill: captive ore, captive power, captive coal, plant vintage and logistics. NALCO's entire
  advantage in the Emkay note is structural — a 2.23 mtpa alumina refinery fed by a 6.8 mtpa
  captive bauxite mine and a 1,200 MW captive power plant, producing 36% RoCE (FY15) in alumina.
- **Being "net long" a product is a position, not a business quality — but it is the position
  that determines earnings.** The Emkay note's framing is worth copying exactly: NALCO is "net
  long in alumina, which has been its biggest advantage." State what the company is long and
  short, per unit, in the note.
- **The cycle is set by supply, and by China specifically.** Demand compounds slowly; capacity
  arrives in lumps. Any forecast must carry the global supply-demand balance including Chinese
  capacity and export behaviour.
- **Secondary (recycled) metal is a different business** with the same output price: the input is
  scrap, so the spread is a *procurement* advantage rather than an ore advantage, and the driver
  is regulation (Gravita's thesis runs on Battery Waste Management Rules and EPR shifting
  end-of-life accountability onto producers, formalising scrap flows toward organised recyclers).
  If the company is a recycler, analyse procurement network and EPR credits, not the cost curve.

## Analysis sequence
1. **Establish the physical chain and the integration ratio at each step.** Ore → intermediate →
   metal, with capacity at each stage and the captive share of each input (ore, power, coal). The
   gaps are the exposure; the surpluses are the optionality.
2. **Compute realisation, cash cost and the spread per tonne**, per product, for as many years as
   the data allows — and against the relevant LME/global index, not against last year.
3. **Place the company on the global cost curve** by quartile, and then ask the harder question:
   **what makes the position durable, and does it expire?** A cost advantage from a legacy coal
   linkage, a captive-mine lease with a renewal date, or a grandfathered power tariff is an
   annuity with a sunset, not a moat. Name the date.
4. **Volume and utilisation** — capacity, production, utilisation, and the expansion pipeline with
   commissioning dates and capex per tonne.
5. **Product mix and value-add** — the ratio of intermediate (alumina, billet, HRC) to
   value-added (foil, CRC, coated, alloy) output. Value-add is the only place where a metals
   company earns something other than the cycle.
6. **The supply-demand balance** — existing capacity + announced additions − curtailments,
   against demand, by region, with China separate. Then the company's position in that balance.
7. **Energy and freight**, which in aluminium and steel are the largest cost lines. Power cost per
   tonne, coal source and landed cost, and the carbon exposure ahead (CBAM for exporters).
8. **Balance sheet through a trough** — net debt/EBITDA at *mid-cycle* EBITDA and at trough, not
   at spot. This sector's equity risk is refinancing at the bottom.
9. **Then mid-cycle EBITDA, and only then the multiple.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **EBITDA per tonne** | segment EBITDA / volume sold | INR/t | The whole story, and the number that separates volume growth from spread expansion. Chart it against the LME price on a second axis — if it tracks price 1:1, there is no operating story to pay for | Segment note + volume disclosure |
| **Cost of production per tonne** | cash cost of production / tonnes produced | INR/t | Decomposed into ore, power/energy, conversion, freight and overhead. The only line management actually controls, and where the cost-curve claim is proved or refuted | Cost breakdown, AR, decks |
| **Realisation per tonne** | segment revenue / volume sold | INR/t | Against the relevant global index and against the domestic import-parity price. A persistent discount or premium needs a stated reason (grade, geography, contract) | Computed |
| **Capacity utilisation** | production / installed capacity | % | The operating-leverage variable. In a downcycle a producer holds utilisation and loses price; note which is being sacrificed | AR capacity table |
| **Captive RM %** | captive-sourced input / total input requirement | % | The integration measure — captive raw material (ore, coal, power) is the cost-curve position made numeric. **Get the lease/linkage expiry date for each**; an expiring captive source is a future cost step-up | AR, mining leases, decks |

## Supporting KPIs
Volume by product and by stage (intermediate vs value-added); value-added share of volume and of
EBITDA; power cost per tonne and captive-power share; coal source split (captive / linkage /
e-auction / imported) and landed cost; ore grade and stripping ratio; conversion cost;
freight per tonne and export share; realisation premium/discount to LME or the domestic
benchmark; net debt and net debt/EBITDA at spot, mid-cycle and trough EBITDA; interest cover;
capex per tonne of new capacity with commissioning dates; ROCE by segment (NALCO's alumina at 36%
RoCE, FY15, against a loss-making smelter is the reason segment ROCE matters); working-capital
days; inventory in tonnes as well as value; royalty and DMF/NMET cess per tonne; carbon intensity
per tonne and CBAM-exposed export share; mine life and reserve/resource statement.
*For recyclers:* scrap procurement volume and source mix (domestic/imported, organised/informal),
recovery/yield %, EPR credit realisation, and the spread between scrap cost and metal realisation.

## Standard exhibit set
Realisation, cash cost and the spread per tonne as three series (the sector's defining exhibit) ·
EBITDA per tonne against the LME/global price on a second axis · cost stack per tonne decomposed
into ore, energy, conversion, freight, overhead · global cost-curve position with the company
marked, and the expiry date of each cost advantage annotated · capacity, production and
utilisation by plant · integration map showing captive share at each stage · value-added share of
volume and EBITDA · global supply-demand balance with China shown separately · announced global
capacity additions by year · segment ROCE (intermediate vs metal vs value-added) · net
debt/EBITDA at spot, mid-cycle and trough · capex pipeline with capex per tonne and commissioning ·
EV/EBITDA band with cycle position marked on the same axis · replacement cost per tonne as a
valuation floor · peer table on EBITDA per tonne and cost-curve quartile, not just on multiples.

## Valuation convention
**EV/EBITDA on MID-CYCLE EBITDA, never peak-on-peak or trough-on-trough**, with **replacement cost
per tonne as a floor**. State explicitly, in the note, where in the cycle the earnings base sits
and what mid-cycle assumption was used — this is the family's single most common analytical
failure and `prompts/thesis_archetypes/cyclical-peak.md` exists for it.

The corpus's NALCO note demonstrates the discipline in the honest direction: "valuation looks cheap
at 8.7x FY18 PE and 3.0x FY18 EV/EBITDA" is stated alongside the condition that the upside needs
"a significant and sustained rise in LME towards US$2,000/tonne" — **the commodity-price
assumption is named as the thesis's dependency rather than buried in the model.** Copy that.
Publish the target's implied LME/commodity price assumption, always.

P/E is a weak secondary here (depreciation and leverage vary hugely with plant vintage), and
`EV/tonne of capacity` is the cross-check against both replacement cost and past transactions.
For a recycler, a P/E is more defensible because the business is a processing spread with low
capital intensity and a regulatory moat — Gravita is valued at **25x FY28E P/E** (JM Financial),
which would be indefensible for a primary smelter.

*Traps:* (i) peak-on-peak — a peak multiple on peak-spread earnings, the dominant error;
(ii) not publishing the commodity-price assumption the target implies; (iii) crediting a captive
cost advantage past its lease or linkage expiry; (iv) valuing announced capacity before
commissioning; (v) applying a recycler's or value-add multiple to primary smelting earnings;
(vi) ignoring that the balance sheet must survive a trough the multiple assumes away.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. The company is valued at 25x FY28E P/E.**
- *Indefensible* (`cycle_position`) — a P/E on a commodity producer capitalises a spread,
  and spreads mean-revert. For a primary smelter this multiple is not arguable.
- *Defensible* (`capital_intensity`) — for a **recycler** a P/E carries information, because
  the earnings are a conversion margin on a capital-light process rather than an LME print
  on a capital-heavy asset. Gravita is valued at 25x FY28E P/E (JM Financial); the identical
  multiple on a primary smelter would not survive.
- *Discriminator* (`disclosed_mechanism`) — is the spread structural (scrap-to-metal
  conversion economics, regulated feedstock access) or is it the commodity price? Same
  family, same multiple, opposite verdicts.

**2. It trades at 3.0x EV/EBITDA and 8.7x P/E — "cheap".**
- *Cheap* (`own_history_anchor`) — near the bottom of its own range.
- *A trough multiple on a peak earnings base* (`cycle_position`) — the classic trap, and
  `prompts/thesis_archetypes/cyclical-peak.md` exists for it. The corpus's NALCO note
  handles it honestly: it states the cheapness *alongside* the condition that upside needs
  "a significant and sustained rise in LME towards US$2,000/tonne" — the commodity
  assumption named as the thesis's dependency rather than buried in the model.
- *Discriminator* (`historical_distribution`) — where the EBITDA base sits in its own
  seven-to-ten-year range, with the mid-cycle assumption stated explicitly in the note.

**3. EV per tonne is below replacement cost.**
- *A floor* (`capital_intensity`).
- *Void for this asset* (`capital_intensity`) — replacement cost floors only assets someone
  would actually rebuild. Obsolete vintage, a stranded location or a captive-power
  disadvantage removes the floor entirely.
- *Discriminator* (`peer_distribution`) — realised transaction values per tonne for
  comparable vintage and location.

## Forensic screens (sector-specific)
- **Volume flat while revenue rises** — the growth is price, and price reverses.
- EBITDA per tonne rising exactly in step with the LME: there is no operating improvement to pay
  for, whatever the management commentary says.
- Cost per tonne improving because of a *falling input index* (coal, caustic, energy) rather than
  productivity — cyclical, and it reverses (see `margin-expansion.md` condition 5).
- Inventory build in a falling-price environment, or inventory valued above net realisable value.
- Capitalisation of mine-development, stripping or trial-run costs; capex reclassified between
  maintenance and growth.
- Segment reporting that nets an intermediate transfer price so the profitable stage's ROCE is
  hidden — insist on the transfer-price basis (NALCO's alumina-vs-smelter split is exactly this
  problem, and the Emkay note handles it correctly).
- Mine lease, environmental clearance or forest clearance renewals within the forecast horizon and
  not disclosed as a risk.
- Royalty, DMF and NMET provisions understated; retrospective mining-dues litigation.
- For recyclers: scrap procurement from informal sources with weak documentation; EPR credit
  income recognised before the credit is realisable; yield/recovery percentages unaudited.
- Related-party trading or offtake arrangements at non-market prices.
- Export incentive/duty-drawback income treated as operating margin.

## Dependencies to map
LME and regional premia; China's capacity, curtailment and export-rebate policy · coal and energy
markets (linkage auctions, e-auction premia, imported coal parity) · caustic soda and CP coke for
alumina; coking coal and iron ore for steel · mining law — lease auctions and renewals,
royalty/DMF/NMET, forest and environmental clearances · import duties, anti-dumping and safeguard
measures **with their expiry or review dates** · CBAM and domestic carbon pricing for exporters ·
freight (rail rates, ocean freight) · rupee (mostly import-parity-priced output and imported
inputs) · domestic demand drivers (construction, autos, packaging, power T&D) · for recyclers,
Battery Waste Management Rules, EPR credit pricing and scrap import policy.

## Common archetypes here
`cyclical-recovery` and `cyclical-peak` (the sector's native pair — decide which and defend it
with the supply-demand balance, not with sentiment), `capex-to-cashflow` (expansion commissioning),
`margin-expansion` where genuine integration is arriving, `deep-value-sotp` (replacement cost, or
a valuable stage inside a loss-making whole — the NALCO alumina case), `balance-sheet-repair`,
and `regulatory-tailwind` for recyclers and for duty protection. Treat `quality-compounder` claims
in primary metals with heavy skepticism: a price-taker's returns compound only if the cost-curve
position is permanent, which it rarely is.
