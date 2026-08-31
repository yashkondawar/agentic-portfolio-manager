# Sector Playbook — Hospitals

*Tier 2. Family: `pharma_chemicals` (`prompts/sector_packs/pharma_chemicals.md`). Shared
rules: `prompts/31`.* **Not covered by any pack before this file.**
**Provenance:** corpus-grounded — Max Healthcare (Nuvama, Sep-25, 40pp), Yatharth Hospital
& Trauma Care (Nuvama, Dec-25), plus a healthcare sector initiation (Nov-25).

## The economic engine
A hospital is a fixed-asset business selling bed-days, where profitability is driven by
**how much revenue each occupied bed generates** and **how many beds are occupied**. New
capacity is dilutive for 2-4 years, then highly accretive — so the whole analysis is
about the maturity profile of the bed base.

`Revenue = operational beds × occupancy × ALOS-adjusted admissions × ARPOB`

## Analysis sequence
1. **Bed inventory by maturity.** Mature clusters (>4 years), ramping (1-4 years), and
   under construction. Blended margins are meaningless without this split — a company
   adding 30% to its bed base will show falling consolidated margins while every
   individual asset improves.
2. **ARPOB and its drivers** — case mix (oncology, cardiac, transplant vs general),
   payor mix (cash/insurance/corporate/government scheme), and price. Rising ARPOB from
   case-mix upgrade is durable; from tariff increases it is capped by competition and
   scheme rates.
3. **Occupancy and ALOS together.** Falling ALOS with flat occupancy means throughput is
   improving (good); rising ARPOB with falling occupancy may mean pricing out volume.
4. **Payor mix and receivables.** Government schemes (Ayushman Bharat, CGHS, state
   schemes) pay low and pay late. Their share drives both ARPOB and working capital.
5. **Cluster economics.** Hospitals are local; a dominant cluster in one city beats
   scattered single assets. Map beds by city and estimate local share.
6. **Expansion pipeline** — beds, capex per bed, commissioning dates, and the ramp
   assumption. Then apply the maturity split from step 1.
7. **Doctor model** — employed vs visiting-consultant vs revenue-share. This determines
   cost structure rigidity and the risk of a franchise walking out.

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **ARPOB** | IP+OP revenue / occupied bed-days | INR/bed/day | The pricing and case-mix variable. Max's note explicitly flags ARPOB growth *moderating*, with volume as the driver — the right honest split | Company decks |
| **Occupancy** | occupied bed-days / available bed-days | % | Mature assets 70-80%; new assets ramp from ~40% | Decks |
| **ALOS** | patient-days / discharges | days | Falling ALOS raises throughput per bed — a genuine efficiency gain that *reduces* revenue per admission but raises revenue per bed | Decks |
| **EBITDA per bed** | EBITDA / operational beds | INR mn/yr | The unit economic; compare mature clusters only | Computed |
| **Operational beds and additions** | count; net adds by year | beds | The growth engine and the margin drag | Decks, capex plan |

## Supporting KPIs
Payor mix %; case mix by specialty; IP/OP revenue split; doctor cost as % of revenue;
consumables and pharmacy as % of revenue; capex per bed; receivable days by payor;
occupancy by cluster; international-patient share; % revenue from top 3 hospitals;
pre-Ind-AS vs post-Ind-AS EBITDA where properties are leased.

## Standard exhibit set
Bed count by hospital and maturity bucket · occupancy trend by cluster · ARPOB trend with
case-mix overlay · ALOS trend · EBITDA per bed, mature vs ramping · payor mix ·
specialty revenue mix · expansion pipeline (beds, capex, commissioning) · capex per bed vs
peers · receivable days by payor · cluster market share · EV/EBITDA band vs peers.

## Valuation convention
**EV/EBITDA on a forward year**, usually 1.5-2 years out, cross-checked with a **DCF**.
Max Healthcare: ~36x H1FY28E EV/EBITDA (an ~18% premium to 1-year forward peer multiples),
"aligning with our DCF (6% terminal growth, ~11% WACC)". EV per bed is the third anchor. This is
the corpus's model case of **DCF triangulation** — two independent methods agreeing is real
evidence, and it ranks second of the four justification families in
`docs/ER_CORPUS_FINDINGS.md` §4.2.

*Traps:* (i) applying a mature-portfolio multiple to a company mid-expansion, whose
consolidated EBITDA is depressed by ramping assets — value the mature and ramping books
separately or use a forward year far enough out that the ramp has happened; (ii) Ind-AS
116 makes leased-hospital operators look better on EBITDA than owned-asset peers;
(iii) premium multiples justified by "quality" without the ROCE to support it.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at ~36x H1FY28E EV/EBITDA, an ~18% premium to one-year-forward peers.**
- *Expensive* (`peer_set_choice`).
- *Corroborated independently* (`terminal_value_share`) — Max Healthcare's note aligns the
  multiple with its DCF (6% terminal growth, ~11% WACC). Two independent methods agreeing is
  real evidence, and DCF triangulation ranks second of the four justification families.
- *Discriminator* (`disclosed_mechanism`) — the DCF assumptions published alongside the
  multiple, so a reader can move the terminal growth and see what survives.

**2. Consolidated EBITDA margin is 22% against a mature peer at 27%.**
- *Operationally weaker* (`peer_set_choice`).
- *Mid-expansion* (`capital_intensity`) — ramping beds depress consolidated margin by
  construction. Value the mature and ramping books separately; applying a mature-portfolio
  multiple to a company mid-expansion is the sector's standard trap.
- *Discriminator* (`disclosed_mechanism`) — the bed-maturity profile and mature-hospital
  margins disclosed separately.

**3. ARPOB rose 11%.**
- *Pricing power* (`growth_durability`).
- *Case mix* (`earnings_base_quality`) — a shift toward tertiary and quaternary work raises
  ARPOB without any tariff increase, and it consumes different capital.
- *Discriminator* (`disclosed_mechanism`) — ARPOB decomposed by specialty mix versus tariff.

## Forensic screens
- ARPOB rising while occupancy falls → pricing out volume, not premiumising.
- Receivable days rising with government-scheme share → the growth is being funded by the
  balance sheet.
- Capitalisation of pre-operative expenses on new hospitals.
- EBITDA reported pre-Ind-AS 116 in one period and post in another.
- Doctor revenue-share renegotiations, or a specialty head's exit, in a cluster carrying
  disproportionate revenue.
- "Beds" quoted as capacity rather than *operational* beds.

## Dependencies to map
Ayushman Bharat / state scheme rates and coverage · NPPA price caps on stents,
implants and consumables · insurance penetration and TPA behaviour · clinical talent
supply · state-level land and licensing · medical-tourism visa policy · competing
capacity in the same catchment.

## Common archetypes here
`capex-to-cashflow` (bed additions maturing), `margin-expansion` (mix and maturity),
`quality-compounder` (dominant mature clusters), `garp`. Watch for `re-rating` claims
resting on "premium to peers is justified" without the ROCE differential shown.
