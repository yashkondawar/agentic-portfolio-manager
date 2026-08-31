# Sector Playbook — Microfinance (JLG / MFI)

*Tier 2. Family: `bfsi` (`prompts/sector_packs/bfsi.md`). Shared rules: `prompts/31`.*
**Provenance:** **domain-derived**, with partial corpus support. The 165-note corpus contains
**no dedicated MFI initiation** — CreditAccess, Fusion, Spandana and Satin are all absent. The
MFI-adjacent notes that do exist and were read for this file: Northern Arc Capital (Ambit,
Dec-25, 34pp — MFI is one of its exposure segments, and it supplies the through-cycle credit-cost
framing), Equitas Small Finance Bank (Nirmal Bang, Oct-21 — a microfinance-origin book
transitioning to a bank, and the collection-efficiency treatment), Ugro Capital (Elara, Feb-26)
and Bajaj Finance (ICICI Securities, Apr-24) for the retail-credit-cycle overlay. Everything
KPI-specific below is domain-derived and must not be cited as corpus practice. **Raise an open
question to add an MFI note to the corpus seeds** (`reference/er_corpus/seeds/`) — this is the
largest single coverage hole in the registry.

## The economic engine
An MFI lends small, unsecured, short-tenor amounts to joint-liability groups of low-income
borrowers, at a regulated-but-high yield, and collects in person at weekly or fortnightly
meetings. Two features dominate everything:

`RoA = (yield − cost of funds − credit cost − opex/AUM) × leverage → RoE`

- **Opex is the largest cost line, not credit cost.** Collections are physical. Opex/AUM runs
  several multiples of a mortgage lender's, so **borrower density and loan-officer productivity
  are the real economics** — this is a distribution business that happens to lend.
- **Credit loss is bimodal, not a rate.** For years it is near zero because joint liability and
  the borrower's need for the next loan enforce repayment; then a shock (demonetisation 2016,
  Covid 2020, the Karnataka/ordinance episodes, an over-leveraging cycle) takes a double-digit
  share of the book. **Never model MFI credit cost as a smooth average.** The correct
  presentation is a loss-event history with dates and magnitudes, and an explicit statement of
  where in that cycle the current year sits.

Because losses are event-driven and unsecured, **the equity is the shock absorber** — capital
adequacy and provisioning buffers are thesis-critical, not housekeeping.

## Analysis sequence
1. **Collection efficiency, first and at the right granularity.** Current-month collections
   excluding arrears, by state and by vintage — not the blended number including prior-period
   recoveries, which flatters. This is the sector's single leading indicator.
2. **Borrower-level leverage and the over-indebtedness picture** — from CRIF/Equifax bureau
   data: number of lenders per borrower, total borrower indebtedness vs the MFIN/RBI cap, and
   the share of the company's book to borrowers with 3+ lenders. Sector blow-ups are always
   preceded by rising lenders-per-borrower.
3. **Geographic concentration by state and district.** MFI risk is political and monsoonal, so
   it is spatially correlated. Largest-state share above ~25-30% is a concentrated risk;
   name the districts.
4. **Loan-officer productivity and branch economics** — borrowers per officer, AUM per branch,
   opex/AUM. This is where the RoA is won.
5. **PAR buckets and the write-off policy.** PAR-30/60/90 with the write-off lag, plus how many
   times the book has been "cleaned". Restructured and rescheduled pools separately.
6. **Cost of funds and liability access** — MFIs are wholesale-funded and lose funding exactly
   when they need it. Bank term-loan share, direct-assignment/securitisation reliance, rating,
   and undrawn lines.
7. **Regulatory posture** — post-2022 RBI harmonisation removed the interest-rate cap but
   imposed household-income and repayment-capacity limits (50% of household income). Check
   compliance headroom and the board-approved pricing policy.
8. **Then the RoA tree**, with credit cost shown as a cycle, not a point.

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Collection efficiency** | current-month collections / current-month demand | % | Exclude arrear recoveries or it flatters. Sustained below ~98% on the current bucket is an early warning; report by state | Monthly/quarterly decks |
| **Credit cost** | provisions + write-offs / avg AUM | % | Present as a loss-event history, never a smooth average. State explicitly where the current year sits in the cycle | P&L + AUM |
| **PAR-30** | principal at risk >30 days past due / gross AUM | % | The honest early bucket; PAR-90 is already a realised loss in an unsecured weekly-collection book | Asset-quality disclosure |
| **Borrowers per loan officer** | active borrowers / field officers | count | The productivity engine and the risk control at once — too high and underwriting/collection discipline decays | Decks, AR |
| **Yield** | interest income / avg AUM | % | Against the board-approved pricing policy and the RBI household-income cap. A rising yield in this sector invites regulatory and political attention | P&L |

## Supporting KPIs
Active borrowers; AUM and disbursement growth; average ticket size and tenor; branch count and
district spread; largest-state and top-3-state share; lenders-per-borrower from bureau data;
share of book to borrowers with 3+ lenders; opex/AUM and cost-to-income; cost of funds and
borrowing mix; direct-assignment / securitisation share of AUM; CRAR; PCR by PAR bucket;
write-offs as % of opening AUM; restructured pool; employee attrition (a genuine leading
indicator of collection quality); non-MFI (secured/MSME/gold) diversification share; BVPS.

## Standard exhibit set
Collection efficiency by month and by state · PAR-30/60/90 stack · credit cost by year across
a full history with the loss events dated and labelled · lenders-per-borrower trend from bureau
data · state and district concentration map · borrowers per loan officer and AUM per branch ·
opex/AUM vs peers · yield, cost of funds and spread · borrowing mix and undrawn lines ·
CRAR and the buffer above the regulatory minimum · disbursement and AUM growth ·
write-off history · non-MFI diversification mix · cross-cycle RoE · P/B band with the loss
events marked on the same axis · P/B vs RoE against peers.

## Valuation convention
**Target P/B × forward BVPS, discounted for credit-cycle volatility.** The discipline this
sector requires above all others: **never capitalise a peak-cycle P/B on peak-cycle RoE.** An
MFI at 22% RoE two years after a cleanup is at a cyclical high in both the multiple and the
metric, and the 40% rule in `prompts/33` will usually show most of the implied return coming
from the multiple.

Preferred presentation: a **through-cycle RoE** (averaged across at least one loss event) and
the P/B that RoE supports, alongside the spot-year figures — then state which one the target
uses. Where the company has a material secured/MSME leg, value it separately; the two deserve
different multiples.

*Traps:* (i) peak-on-peak, as above — the dominant error in this sector; (ii) treating a
post-cleanup year's near-zero credit cost as the run-rate; (iii) ignoring the equity dilution
a loss event forces at exactly the worst price; (iv) reading a national collection-efficiency
number when the risk is district-level; (v) P/E, which is meaningless across a loss cycle.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. RoE is 22%.**
- *A high-quality franchise* (`sustainable_roe`) — deserving a premium P/B.
- *A cyclical high in both terms* (`cycle_position`) — an MFI two years after a cleanup is
  at a peak in the multiple and in the metric simultaneously. Never capitalise a peak-cycle
  P/B on a peak-cycle RoE; the 40% rule in `prompts/33_thesis_synthesis.md` will usually
  show most of the implied return coming from the multiple.
- *Discriminator* (`historical_distribution`) — a through-cycle RoE averaged across at
  least one loss event, and the P/B that RoE supports, published alongside the spot figures
  with a statement of which one the target uses.

**2. AUM grew 40%.**
- *Penetration* (`growth_durability`) — new borrowers in under-served districts.
- *Household leverage* (`earnings_base_quality`) — the same borrowers at a larger ticket,
  often with multiple lenders. That is not market expansion; it is the mechanism that
  produces the next loss event.
- *Discriminator* (`disclosed_mechanism`) — decompose AUM growth into borrower count versus
  average ticket, and read credit-bureau overlap on the incremental book.

## Forensic screens (sector-specific)
- Collection efficiency quoted **including** arrear recoveries, or without stating the basis —
  the single most common presentational flatter in the sector.
- Growth concentrated in a small number of districts, or in states with recent political
  intervention on lending.
- Lenders-per-borrower rising in the company's core geographies while it grows faster than the
  district's total MFI credit — buying growth from the marginal borrower.
- Repeated "clean-up" write-offs that reset GNPA without a change in origination practice;
  write-offs large relative to opening AUM.
- Rapid AUM growth immediately after a loss event, on an unseasoned book, presented as recovery.
- Securitisation / direct assignment used to move stressed vintages off book — check retained
  risk, credit enhancement and the servicing obligation.
- Ticket size rising faster than borrower income evidence, pushing against the household-income
  cap.
- Employee attrition rising among field officers while collections are reported as stable.
- Non-MFI diversification announced but the disclosure not segment-separated.
- Insurance cross-sell income booked upfront; fees charged outside the disclosed all-in rate.

## Dependencies to map
RBI's microfinance directions (household-income and 50%-of-income repayment-capacity limits;
the removal of the rate cap and the board-approved-pricing regime) · MFIN self-regulation and
its lender-count guidance · CRIF/Equifax bureau data availability and quality · state politics
and loan-waiver rhetoric (Andhra 2010, Karnataka 2025-type ordinances) · monsoon and rural
wage/MGNREGA data · agricultural cash-flow cycles · bank willingness to lend to MFIs (funding
is procyclical and vanishes in a shock) · SFB licensing as an exit/transition path for scale
MFIs · gold-loan and moneylender competition at the borrower level.

## Common archetypes here
`cyclical-recovery` (post-loss-event normalisation — the most common and the most often
mispriced), `market-share-gainer` (check the denominator and the marginal borrower),
`turnaround`, `regulatory-tailwind` (post-2022 pricing freedom), and `re-rating`, which carries
the highest skepticism weight here because the multiple and the metric peak together. Be
especially alert to `quality-compounder` claims: compounding requires surviving a loss event
with the franchise intact, so the claim needs a dated cycle to point at, not three good years.
