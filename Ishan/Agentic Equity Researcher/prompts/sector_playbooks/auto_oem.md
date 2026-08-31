# Sector Playbook — Auto OEMs (PV, CV, 2W, tractors)

*Tier 2. Family: `auto_engineering` (`prompts/sector_packs/auto_engineering.md`). Shared rules:
`prompts/31`.*
**Provenance:** corpus-grounded — Tata Motors Commercial Vehicles (Ambit, Dec-25 — SOTP, the
GVW-mix-vs-volume argument, and the peer-discount framing against Ashok Leyland), Tata Motors (JM
Financial, Jan-26), Ola Electric (Ambit, Sep-24 — the EV 2W model), with LG Electronics India (ICICI
Securities, Oct-25) as a comparator for consumer-durable channel mechanics.

## The economic engine
A vehicle maker is a **fixed-cost assembler with a dealer channel between it and the customer.** Two
facts dominate:

`EBITDA = volume × (realisation per vehicle − variable cost per vehicle) − fixed cost`

- **Operating leverage is brutal in both directions.** A 5% volume miss can move EBITDA margin by
  100-200bps because the plant, tooling and engineering cost are fixed. Every forecast in this
  playbook is a volume forecast with a margin consequence attached.
- **The company sells to dealers, not to consumers.** Reported volume is *wholesale* (dispatches to
  dealers); actual demand is *retail* (registrations). The gap is dealer inventory, and it can
  flatter a quarter and then reverse hard. **VAHAN registrations versus company wholesale is the
  single most important cross-check in this playbook**, and it is public.

**Mix is usually worth more than volume, and the corpus shows how to say so.** Ambit's Tata Motors CV
note makes the argument precisely: higher gross-vehicle-weight (GVW) mix "will boost ASPs &
profitability" *despite* a −5% volume CAGR, and — the line worth copying — **~35% of volume forms 68%
of the revenue pool.** A volume-weighted view of a CV or PV portfolio is misleading; the analysis must
be revenue- and margin-weighted by segment.

## Analysis sequence
1. **Volume by segment, wholesale and retail.** PV (hatch/sedan/UV, and price band), CV (LCV/ICV/MHCV,
   tipper/haulage/tractor-trailer, bus), 2W (motorcycle/scooter, engine cc), tractors (HP band). Then
   **wholesale vs VAHAN registrations** and the implied dealer inventory.
2. **Weight the portfolio by revenue and margin, not by units** (the 35%-of-volume/68%-of-revenue
   point). Get ASP and, where possible, contribution per vehicle by segment.
3. **Realisation per vehicle, decomposed** into price, mix (segment, variant, trim), and discount.
   **Discount per vehicle is the honest demand indicator** and it is disclosed only in transcripts and
   channel checks — chase it.
4. **Market share by segment, with the direction and the reason.** Ambit's note quantifies ~10% market
   share loss in TMCV alongside the mix gain — losing share while improving mix is a coherent strategy
   and must be assessed as one, not as a contradiction.
5. **The cost stack and its pass-through** — steel, aluminium, copper, rubber, resins, plus
   bought-out electronics. Then the *mechanism*: quarterly indexed clauses vs spot vs annual
   negotiation. Margin gained purely from a falling input reverses.
6. **Product cycle and capex/R&D.** New-model pipeline with launch dates, platform strategy,
   capitalised product-development spend, and the ageing of the current portfolio. **An OEM's share
   follows its launch cadence with a lag**, so a stale portfolio is a forward risk regardless of
   current numbers.
7. **The powertrain transition, quantified.** EV/CNG/hybrid share of volume, the contribution margin
   of each, the capex committed, and the PLI or FAME/subsidy dependence. Ask whether the company's
   content and margin per vehicle rise or fall in the new architecture.
8. **Exports and international operations**, separately — different cycle, different currency,
   different margin (Ambit values IVECO separately from India TMCV for exactly this reason).
9. **Channel and financing health** — dealer count and profitability, dealer inventory days,
   captive-finance penetration and its loss experience, and the availability of retail credit. In
   India, retail finance availability is often the binding demand constraint.
10. **Then mid-cycle margin, the SOTP if there are separable businesses, and the multiple.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Volume growth** | YoY growth in units, by segment | % | **Wholesale and retail (VAHAN) both.** A wholesale-led beat with rising dealer inventory is borrowed from next quarter. Weight segments by revenue, not units | Company monthly disclosure, VAHAN/SIAM |
| **Realisation per vehicle** | segment revenue / units sold | INR | Decompose into price, mix and discount. Ambit's GVW-mix argument shows realisation rising on a falling volume base — a legitimate and common pattern that must be attributed correctly | Computed |
| **EBITDA per vehicle** | segment EBITDA / units sold | INR | The unit economic, and the cleanest way to compare an OEM against itself across a cycle. Splits operating leverage from mix from cost | Computed |
| **Market share** | company volume / industry volume, by segment | % | **By segment, never blended** — a blended share number across PV/CV/2W is meaningless. State the direction and whether it was traded for mix or margin (TMCV: ~10% MS loss with mix gain) | SIAM/VAHAN, FADA |
| **Dealer inventory days** | dealer stock / retail run-rate | days | The channel-health tell and the wholesale-vs-retail gap made numeric. Rising inventory with rising wholesale volume is a correction waiting to happen | Transcripts, FADA, channel checks |

## Supporting KPIs
Volume and ASP by segment and price band; contribution margin per vehicle by segment; discount per
vehicle; GVW/HP/cc mix; variant and trim mix; export volume and realisation by geography; capacity by
plant and utilisation; break-even utilisation; new-model launch pipeline with dates; average portfolio
age; R&D spend as % of revenue and the **capitalised** share; product-development capex; powertrain mix
(ICE/EV/CNG/hybrid) with contribution margin each; battery cost per kWh and localisation % for EVs;
PLI/FAME/subsidy accrual; raw-material cost per vehicle and the indexation mechanism; bought-out
content share; dealer count, additions and dealer profitability; captive-finance penetration, AUM and
credit cost (if a captive NBFC exists, its book is a lender — apply `nbfc_diversified` to it
separately); spare-parts/aftermarket revenue share and its margin (a high-margin annuity that often
carries a third of profit); warranty provision as % of revenue; net cash/debt and the auto-business
net cash excluding the finance arm; free cash flow per vehicle.

## Standard exhibit set
Volume by segment, wholesale vs VAHAN retail, with the implied dealer-inventory gap · **revenue and
EBITDA weighted by segment against volume weighting** (the 35%/68% exhibit) · realisation per vehicle
decomposed into price, mix and discount · discount per vehicle against industry · EBITDA per vehicle
across a full cycle · market share by segment with the launch calendar overlaid · GVW/variant mix
trend · cost per vehicle against the key input indices with the pass-through mechanism annotated ·
capacity, production and utilisation with the break-even level marked · new-model pipeline with launch
dates and portfolio age · powertrain mix with margin by powertrain · export volume and realisation by
geography · dealer count, inventory days and dealer profitability · captive-finance penetration and
credit cost · aftermarket revenue and margin · warranty provisioning · net cash excluding the finance
arm · **the SOTP table** where international or finance subsidiaries exist · P/E band on mid-cycle EPS ·
peer table on EBITDA per vehicle and segment share, not on multiples alone.

## Valuation convention
**P/E on MID-CYCLE EPS, or EV/EBITDA — and where there are separable businesses, SOTP.** The Tata
Motors CV note is the corpus's worked example and its structure is the right one: value **India TMCV
and IVECO separately, at 13.5x and 2.5x one-year-forward EV/EBITDA**, summing to a TP of ₹430 which the
note also expresses as **24.5x FY27E P/E** — two multiples published against one target, so the reader
can sanity-check the parts against the whole. That is the same discipline `specialty_chemicals` applies
to SOTP and it should be standard here, because almost every Indian OEM has an international arm, a
captive financier, or both.

**The cardinal cyclical rule: cyclicals get high multiples on trough earnings and low multiples on peak
earnings — never the reverse.** State where in the cycle the earnings base sits. Ambit's note does this
by observing TMCV "is yet to reach FY19 volume peak", which locates the base without asserting a
forecast. Publish the volume and margin assumptions the target implies.

Peer-relative framing is standard and legitimate — TMCV "trades at ~6% discount to AL due to slower
volume growth, LCV MS loss and PV drag" **names the reasons for the discount**, which is what separates
a defensible relative argument from the circular discount-narrowing the corpus is full of
(`docs/ER_CORPUS_FINDINGS.md` §6). If our note argues the discount closes, name the mechanism and the
falsifier.

*Traps:* (i) peak multiple on peak earnings — the family's defining error; (ii) valuing consolidated
earnings when the finance arm should be valued on P/B and the auto business on P/E or EV/EBITDA;
(iii) capitalising a margin lifted by a falling commodity; (iv) crediting a wholesale-led volume beat
that is dealer inventory; (v) valuing EV ambition with committed capex but no contribution margin;
(vi) using a global OEM peer set on Indian mix and growth; (vii) forgetting that aftermarket profit is
higher-quality than vehicle profit and deserves separate treatment.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at 9x P/E, the lowest in a decade.**
- *Cheap* (`own_history_anchor`).
- *The cardinal cyclical rule, inverted* (`cycle_position`) — cyclicals get high multiples
  on trough earnings and low multiples on peak earnings. A decade-low P/E on a peak-cycle
  EPS is the trap, not the opportunity, and the convention is P/E on **mid-cycle** EPS for
  exactly this reason.
- *Discriminator* (`historical_distribution`) — EPS against its own ten-year band, and where
  industry volumes sit in the cycle.

**2. One consolidated P/E is applied.**
- *It is one company* (`peer_set_choice`).
- *It is three* (`peer_set_choice`) — almost every Indian OEM has an international arm, a
  captive financier, or both. Tata Motors CV is valued as India TMCV at 13.5x and IVECO at
  2.5x one-year-forward EV/EBITDA, summing to a TP of INR 430 which the note *also* expresses
  as 24.5x FY27E P/E — two multiples published against one target, so the reader can
  sanity-check the parts against the whole.
- *Discriminator* (`disclosed_mechanism`) — segment EBIT, and separately listed or
  separately valued subsidiaries at their own economics.

## Forensic screens (sector-specific)
- **Wholesale dispatches running ahead of VAHAN registrations** for two or more quarters — channel
  stuffing, and the correction is arithmetic.
- Discounts rising while realisation is presented as improving on mix.
- Product-development cost capitalised aggressively, or the capitalisation rate rising as margins come
  under pressure; capitalised development not amortised over a realistic model life.
- Warranty provisioning flat or falling while volumes, complexity or EV content rise — EV and new-tech
  warranty exposure is materially higher and under-provisioning here is a multi-year liability.
- Recall costs or field-service campaigns treated as exceptional.
- **The captive finance arm's credit cost rising while penetration rises** — the OEM is buying volume
  with its balance sheet, and the loss shows up two years later. Consolidated numbers hide this;
  demand the finance arm separately.
- PLI, FAME or export-incentive accruals recognised before eligibility is certain, and presented inside
  operating EBITDA.
- Export sales to a related distributor or a group entity; international subsidiary losses parked
  outside the reported segment.
- Inventory build at the company (not just at dealers) ahead of a model change or an emission-norm
  transition (BS-VI-type deadlines force pre-buys and then a cliff).
- Spare-parts revenue reclassified into vehicle revenue, or vice versa, changing apparent margin.
- Vendor-financing arrangements or supplier payables stretched to flatter working capital;
  bill-discounting facilities for dealers that are effectively company credit risk.
- Emission-norm or safety-regulation compliance capex deferred.

## Dependencies to map
**Segment-specific demand clocks** — CV volumes track freight rates, e-way-bill volumes, mining and
infrastructure activity; PV tracks consumer credit, income and fuel prices; 2W tracks rural cash flow,
monsoon and financing availability; tractors track monsoon, MSP and rural credit. Never blend them ·
SIAM, FADA and **VAHAN registration data** (the wholesale-vs-retail check) · steel, aluminium, copper,
rubber, resin and precious-metal (catalyst) prices, plus the indexation mechanism · semiconductor and
electronic-component availability · emission and safety regulation with dates (CAFE norms, BS
transitions, ADAS mandates) — each forces a pre-buy and a subsequent cliff · **EV policy**: FAME/PM
E-DRIVE, state EV policies, GST differentials, battery-cell PLI and localisation requirements, plus
charging infrastructure · scrappage policy · interest rates and retail-credit availability, which is
often the binding demand constraint · fuel and CNG prices and their relative economics · export-market
cycles and tariffs (link to `auto_ancillary`) · used-vehicle prices, which set the trade-in economics
underpinning new-vehicle demand.

## Common archetypes here
`cyclical-recovery` and `cyclical-peak` (the native pair — locate the base against the last peak and
trough, as the TMCV note does), `margin-expansion` (mix and operating leverage — test against the
commodity cycle), `market-share-gainer` (must be by segment, and check whether share was bought with
discount), `turnaround` (the Tata Motors template), `capex-to-cashflow` for capacity and EV
investment cycles, `regulatory-tailwind` (PLI, EV subsidy) and its inverse, and `deep-value-sotp`
where an international arm or finance subsidiary is mispriced inside the consolidated entity. Treat
`re-rating` with the standard skepticism weight — in this sector it is usually a peer-discount argument,
and the corpus shows those are defensible only when the reasons for the discount are named and
addressed. `quality-compounder` is rarely appropriate for a cyclical assembler.
