# Sector Playbook — Oil & gas, refining, marketing & city gas

*Tier 2. Family: `commodities_energy` (`prompts/sector_packs/commodities_energy.md`). Shared
rules: `prompts/31`.*
**Provenance:** **domain-derived.** The 165-note corpus contains **no oil, gas, refining or CGD
initiation** — Reliance, ONGC, the OMCs, GAIL, IGL/MGL/Gujarat Gas and Petronet are all absent. The
only adjacent files are Engineers India (2018-01, an oil-and-gas *EPC and consultancy* contractor,
which belongs to `epc_construction`) and InterGlobe Aviation (Anand Rathi, Oct-25; BOB Capital,
Sep-20), where crack spreads and ATF appear as an airline's *input cost*. Nothing below may be cited
as corpus practice. **Raise an open question to add refining, CGD and upstream notes to
`reference/er_corpus/seeds/`** — with `microfinance` and `qsr`, this is one of the registry's three
largest coverage holes. The nearest authored siblings in method are `ferrous_non_ferrous_metals`
(spread-per-unit, mid-cycle discipline) and `power_utilities` (regulated-return and
subsidy/receivable mechanics).

## The economic engine
**Four distinct businesses share this playbook, and the first act is to say which one — they have
different units, different regulators and different valuation conventions.**

1. **Upstream (E&P)** — produces oil and gas at a cost against a global price. `EBITDA = volume ×
   (realisation − opex − royalty/cess)`. Value is a depleting reserve base: the analysis is reserves,
   production decline and reserve replacement, and the correct method is NAV/DCF per barrel of
   reserves, not a multiple of a single year's earnings.
2. **Refining** — converts crude into products and earns the **crack spread**. A pure processing
   spread business, analytically identical to a metals converter: `EBITDA = throughput × (GRM −
   opex)`. The edge is complexity (the ability to run cheap heavy/sour crude and still make light
   products), captured by the Nelson complexity index.
3. **Marketing (retail fuel)** — earns a per-litre marketing margin on volume through a retail
   network. In India this margin is **administratively influenced rather than free**: state-owned
   OMCs absorb price shocks for policy reasons, so marketing margin is a political variable, not a
   market one. This is the most important single fact about Indian downstream and it must be stated
   in any note on it.
4. **City gas distribution (CGD)** — a **licensed regional monopoly** with exclusivity for a defined
   period, selling gas per standard cubic metre to CNG, domestic PNG, commercial and industrial
   customers. `EBITDA = volumes (mmscmd) × EBITDA per scm`. This is the closest thing in the family
   to an annuity, and it is valued accordingly.

**The unifying discipline: analyse the spread, never the price.** A refiner can prosper as crude
falls and suffer as it rises; a CGD's economics turn on the *gap* between its gas cost (APM /
domestic / imported LNG) and the alternative fuel it displaces (petrol, diesel, LPG, propane, furnace
oil), not on the absolute gas price.

## Analysis sequence
1. **Classify the business** and, for an integrated company, split revenue and EBITDA across the four
   segments. An integrated refiner-marketer is naturally hedged; a standalone refiner is not.
2. **For refining: throughput, complexity and the crude slate.** Capacity, utilisation (Indian
   refiners routinely run above 100% of nameplate), Nelson complexity, and the heavy/sour share of
   the slate. Then GRM against the **Singapore benchmark** — the premium or discount to benchmark is
   the operating story, and it is the number to forecast.
3. **Product slate and its netbacks** — petrol, diesel, ATF, LPG, naphtha, petchem feedstock,
   bitumen. Diesel and petrol dominate Indian volumes; petrochemical integration is where a refiner
   escapes the pure spread.
4. **For marketing: the network and the margin.** Retail outlets, throughput per outlet, market
   share, and the marketing margin per litre — with an explicit statement of whether prices are
   being set commercially or held. **Under-recovery is not a footnote; it is the earnings.**
5. **For CGD: the license, then the volumes.** Geographical areas won, the **exclusivity end-date for
   each** (infrastructure and marketing exclusivity run on different clocks), minimum work programme
   commitments (CNG stations and domestic PNG connections promised to PNGRB) and the penalty for
   missing them. Then volumes by segment: CNG, domestic PNG, commercial, industrial.
6. **For CGD: the gas-sourcing stack and the pass-through.** APM allocation (cheap, priority,
   allocated for CNG and domestic PNG), HP-HT domestic gas, term LNG and spot LNG, with the blended
   cost. **APM allocation cuts are the sector's single largest earnings risk**, because the
   replacement is imported LNG at multiples of the price and the pass-through to CNG is
   competitively capped by petrol/diesel parity.
7. **For upstream: reserves and decline.** 1P/2P reserves, reserve life, reserve replacement ratio,
   production decline rate, opex per barrel, and the royalty/cess regime.
8. **Regulatory position** — PNGRB tariff orders, the unified tariff structure for pipelines, and
   any pending review.
9. **Then the segment-appropriate valuation, and sum.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Gross refining margin (GRM)** | (product realisation − crude cost) / throughput | US$/bbl | Against the Singapore complex benchmark — **the premium to benchmark is the company's skill; the benchmark itself is the cycle.** Report both, and separate inventory gains/losses from operating GRM | Company disclosure, Platts/Argus |
| **EBITDA per scm** | CGD segment EBITDA / volumes in scm | INR/scm | The CGD annuity's unit economics. Read against the CNG-to-petrol and PNG-to-LPG discount, which is what the customer actually responds to | Segment note + volume |
| **Volumes** | gas throughput | mmscmd | By segment (CNG / domestic PNG / commercial / industrial) — the segments have very different margins and very different price elasticities. Industrial volume is the swing item and the most price-elastic | Decks, PNGRB data |
| **Marketing margin** | retail realisation − (refinery transfer price + duties + dealer commission) | INR/litre | For Indian OMCs, state whether this reflects commercial pricing or administrative absorption. A margin held through a crude spike is a subsidy in disguise; a margin expanded through a crude fall is a policy window | Derived; company/PPAC data |
| **Reserve replacement ratio** | reserves added / production, over the period | x | Upstream only. **Below 1.0x sustained means the company is liquidating itself**, however good the current earnings look. Read with reserve life and the 1P/2P basis | Reserve statement, AR |

## Supporting KPIs
*Refining:* nameplate and effective capacity; utilisation; Nelson complexity index; crude slate by
grade with the heavy/sour share; distillate yield; fuel-and-loss %; energy-intensity index;
inventory gain/loss separated from operating GRM; export share; refinery opex per barrel; petchem
integration share and petchem spreads.
*Marketing:* retail outlet count and additions; throughput per outlet; market share by product;
lubricants and non-fuel retail income; inventory days; under-recovery / subsidy receivable from
government.
*CGD:* geographical areas and their exclusivity end-dates; CNG stations and domestic PNG connections
against the minimum work programme; volumes and margin by customer segment; gas-sourcing mix (APM /
HP-HT / term LNG / spot) and blended gas cost; CNG-petrol and PNG-LPG price differential; connection
capex per household; compressor utilisation; pipeline length; the PNGRB tariff order in force.
*Upstream:* 1P/2P reserves and reserve life; production by field with decline rates; opex and
finding-and-development cost per barrel; royalty, cess and profit-petroleum share; nomination vs
NELP/HELP/OALP block terms; abandonment provision.
*All:* net debt/EBITDA at mid-cycle; forex exposure (crude and LNG are dollar-denominated, revenue
mostly rupee); capex pipeline; ROCE by segment.

## Standard exhibit set
Segment revenue and EBITDA split across upstream / refining / marketing / CGD · GRM against the
Singapore benchmark with the premium shown separately, and operating GRM separated from inventory
effects · crude slate composition and the heavy/sour share vs complexity · product yield and netbacks
· throughput and utilisation · marketing margin per litre against the crude price, with any
administered-pricing periods shaded (the exhibit that makes Indian downstream legible) · retail
network and throughput per outlet · **CGD: geographical areas with exclusivity end-dates** ·
volumes by customer segment · EBITDA per scm trend · gas-sourcing mix with blended cost and the APM
allocation share · CNG-vs-petrol and PNG-vs-LPG price differential (the demand driver) · minimum
work programme progress vs commitment · upstream reserves, reserve life and reserve replacement
ratio · production decline by field · capex pipeline with commissioning · segment ROCE ·
EV/EBITDA band with cycle position marked · the SOTP table.

## Valuation convention
**SOTP, valuing each segment on its own convention — mandatory for any integrated name.**

- **Refining and marketing: EV/EBITDA on mid-cycle GRM and a normalised marketing margin, never on
  spot.** Publish the GRM and marketing-margin assumptions the target implies, exactly as
  `ferrous_non_ferrous_metals` requires the LME assumption to be published.
- **CGD: DCF over the exclusivity period plus a terminal value**, with an explicit view on what
  happens when exclusivity ends and third-party access begins. This is the correct method because the
  asset *is* a time-limited licence; an EV/EBITDA multiple silently assumes perpetuity, which the
  licence does not grant. Cross-check on EV/EBITDA and on EV per scm of volume.
- **Upstream: NAV/DCF on 2P reserves** at a stated long-run crude deck, with EV per barrel of
  reserves as the cross-check. A P/E on a depleting asset is a category error.

*Traps:* (i) **valuing a CGD on a perpetual multiple while its exclusivity expires inside the
forecast horizon** — the sector's defining error; (ii) capitalising a peak GRM (the 2022 window is
the cautionary case) or a policy-window marketing margin; (iii) treating inventory gains as
operating GRM; (iv) applying one blended multiple to an integrated company whose segments deserve
2-3x different ones; (v) forecasting CGD volumes without the APM-allocation and CNG-parity
constraint; (vi) upstream valued on earnings rather than reserves; (vii) ignoring the
government-receivable/subsidy line in OMC balance sheets.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. Refining is valued at 6x EV/EBITDA.**
- *Cheap* (`own_history_anchor`).
- *On spot, not mid-cycle* (`cycle_position`) — the convention is EV/EBITDA on a mid-cycle
  GRM and a normalised marketing margin, never on spot.
- *Discriminator* (`historical_distribution`) — GRM against its own band, with the GRM and
  marketing-margin assumptions the target implies published in the note, exactly as
  `ferrous_non_ferrous_metals` requires the LME assumption to be published.

**2. The CGD business is valued at 18x EV/EBITDA.**
- *A growth asset deserves a growth multiple* (`growth_rate`).
- *The multiple assumes something the licence does not grant* (`terminal_value_share`) — an
  EV/EBITDA multiple silently assumes perpetuity, and the asset *is* a time-limited
  exclusivity licence. The correct method is a DCF over the exclusivity period plus a
  terminal value, with an explicit view on what happens when third-party access begins.
- *Discriminator* (`disclosed_mechanism`) — the exclusivity end date and the access regime
  that follows it. Cross-check on EV/EBITDA and EV per scm of volume.

## Forensic screens (sector-specific)
- **Inventory gains presented inside GRM** without separate disclosure — the most common
  presentational issue in refining, and it reverses.
- GRM quoted on a different basis between periods (gross vs net of fuel-and-loss, with or without
  petchem).
- Under-recovery or subsidy receivable from government growing while reported margins look normal —
  the earnings are being financed by the balance sheet.
- CGD volume growth carried by low-margin industrial customers presented as franchise growth; the
  segment mix not disclosed.
- Minimum-work-programme shortfalls (CNG stations, PNG connections) and the associated performance-
  bond risk not disclosed.
- Exclusivity expiry dates absent from the disclosure entirely — check PNGRB filings directly.
- Connection capex for domestic PNG capitalised against customers who have not yet consumed;
  connection charges recognised upfront.
- APM allocation reduction announced but the forecast still built on the old blended gas cost.
- Upstream: reserve *revisions* (rather than discoveries) driving the reserve replacement ratio;
  a switch from 1P to 2P reporting; abandonment provisions understated or undiscounted.
- Capitalisation of dry-hole and exploration costs (successful-efforts vs full-cost accounting —
  check which, it changes reported earnings materially).
- Refinery turnaround/shutdown costs capitalised rather than expensed; deferred maintenance.
- Related-party crude sourcing, product offtake or shipping arrangements within a promoter group.
- Excise/duty changes absorbed rather than passed through, with the absorption not quantified.

## Dependencies to map
Brent/Dubai crude and the light-heavy differential; Singapore complex GRM · Henry Hub, JKM LNG spot
and term-contract slopes; APM gas price formula and the government's allocation policy (the single
largest CGD earnings variable) · PNGRB — geographical-area bidding, exclusivity periods, unified
pipeline tariffs, minimum work programmes, and the third-party-access regime · excise duty, VAT and
the recurring GST-on-fuel debate; windfall taxes on upstream and on exports (the 2022 special
additional excise duty is the template) · government fuel-pricing policy and OMC compensation, which
in practice sets marketing margin · petrol/diesel/LPG retail prices, because they set the CNG and PNG
ceiling · EV adoption and its long-run threat to CNG and to petrol/diesel retail · biofuel and
ethanol-blending mandates · vehicle-scrappage and CNG-vehicle OEM support · rupee-dollar (inputs are
dollar-priced) · NELP/HELP/OALP fiscal terms and block-award rounds · refinery capacity additions
globally, which set the crack cycle · India's city-gas expansion rounds and the resulting competition
for industrial customers at the boundary of adjacent areas.

## Common archetypes here
`cyclical-recovery` and `cyclical-peak` for refining and upstream (the family's native pair — decide
which and defend it with the global capacity balance), `regulatory-tailwind` or its inverse — this
playbook's most consequential archetype, because APM allocation, windfall taxes and administered
pricing can each reset earnings without any operating change · `capex-to-cashflow` for CGD network
build-out and refinery expansion · `deep-value-sotp`, common for integrated names the market prices
on the worst segment · `quality-compounder` is defensible **only** for CGD inside its exclusivity
period, and the claim must then carry the expiry date. Treat `margin-expansion` claims in refining
with heavy skepticism: the spread is set by the global cycle, not by the company.
