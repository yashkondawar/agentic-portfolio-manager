# Sector Playbook — Housing finance companies

*Tier 2. Family: `bfsi` (`prompts/sector_packs/bfsi.md`). Shared rules: `prompts/31`.*
**Provenance:** corpus-grounded — Bajaj Housing Finance (JM Financial, Mar-26, 44pp, 67
exhibits), an affordable-housing-finance sector initiation (Nirmal Bang, Apr-24, 50pp, 49
exhibits, covering HomeFirst / Aavas / AHFC peer set), HUDCO (Nirmal Bang, Jul-24).

## The economic engine
A mortgage is the longest-tenor, lowest-yield, best-secured asset in Indian lending. That
combination defines everything:

`RoA = (spread + fees − credit cost − opex/AUM) × leverage → RoE`

Because the yield is low, **the spread is thin and leverage is high** — so an HFC's RoE is far
more sensitive to cost of funds and to opex than an NBFC's is, and far less sensitive to credit
cost. And because the tenor is 15-20 years while the liability is 3-5, **the business is
structurally short duration risk and long prepayment risk**. Two consequences the analysis must
carry:

- **Prepayment (balance-transfer) is the sector's hidden leak.** A book with 15% annual
  run-off needs to originate 15% just to stand still; disclosed AUM growth understates
  origination effort. Always find the run-off rate.
- **Spread compression is structural, not cyclical, as an HFC scales.** The Nirmal Bang
  affordable-housing note states it directly: "as AHFCs grow in size, we expect spreads to
  decline" — larger books attract cheaper funding *and* competitive pricing pressure, and the
  second usually outruns the first. A forecast holding spreads flat through a doubling of AUM
  needs a defence.

## Analysis sequence
1. **Cost of funds and the borrowing mix** — NHB refinance (cheapest, quota-limited), bank term
   loans, NCDs, ECB, deposits where permitted; plus the external rating and its history.
   Parentage often *is* the answer (Bajaj Housing).
2. **Spread, decomposed** into yield and cost of funds as separate series, plus the share of
   the book on floating vs fixed rates and the repricing lag in each direction. Lenders
   reprice assets down faster than liabilities in a cutting cycle; the asymmetry is the margin.
3. **Product mix and its true risk order** — pure home loans (lowest yield, lowest loss),
   loan-against-property / LAP, developer finance (highest yield, cycle-correlated),
   MSME/non-housing. The affordable-housing note flags the standard drift: AHFCs "gradually
   increasing their share of non-housing loans (developer/MSME) to maintain profitability…
   these loans are high-yielding and likely to help in sustaining margins, they are also
   riskier." Treat a rising non-housing share as spread bought with risk.
4. **Customer segment and ticket size** — salaried vs self-employed vs informal-income, and
   average ticket size. Affordable HFCs run ~INR 1mn average ticket; below INR 1.5mn dominates
   by volume. Self-employed/informal underwriting is a genuine capability or a genuine hole.
5. **LTV, and LTV at origination vs current** — plus the appraisal basis and geographic
   concentration of the collateral. Recovery is a function of title quality and SARFAESI
   timelines, not of the LTV number alone.
6. **Asset quality with the tenor in mind.** A 20-year book seasons for a decade; three good
   years prove nothing. Look at vintage curves, 1+ DPD, and the restructured residue.
7. **Prepayment / run-off rate, opex/AUM and branch productivity**, then the RoA tree.

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Spread** | yield on advances − cost of funds | % | The core economic; charted as two lines, not one. Assume it compresses with scale unless the funding mix demonstrably improves | P&L + borrowings note |
| **Cost of funds** | interest expense / avg borrowings | % | The most durable edge in the sector, and mostly parentage/rating rather than skill. NHB refinance share is the swing item | Borrowings schedule |
| **GNPA (with 1+ DPD and vintage curves)** | gross stage-3 / AUM | % | Low absolute levels mean little on an unseasoned long-tenor book — read it against origination vintage | Asset-quality disclosure |
| **LTV** | sanctioned amount / appraised value | % | At origination *and* current; plus the appraisal basis. High-LTV affordable lending is a different business from prime | Sanction disclosure, decks |
| **AUM growth** | YoY growth in assets under management | % | Net of run-off. Disbursement growth minus prepayment is the honest series | Balance sheet + decks |
| **RoA** | PAT / avg assets | % | Leverage-neutral profitability; the comparable across differently-geared HFCs | Computed |

## Supporting KPIs
Disbursements; run-off / prepayment rate; salaried vs self-employed mix; average ticket size;
non-housing (LAP/developer/MSME) share; fixed vs floating mix; NHB refinance share; borrowing
mix and external rating; opex/AUM and cost-to-income; branch count and productivity; state
concentration; ALM gap by bucket; PCR; restructured residue; CRAR (HFC-specific NHB norms);
leverage; BVPS; incremental spread on new business vs book spread; fee and insurance
cross-sell income.

## Standard exhibit set
Yield, cost of funds and spread as three series · borrowing mix and rating history · NHB
refinance share · AUM and disbursement growth with run-off overlay · product mix trend
(housing vs non-housing) · ticket-size distribution · salaried/self-employed split · LTV
distribution · vintage-wise delinquency curves · GNPA and 1+ DPD trend · state concentration ·
ALM buckets · opex/AUM vs peers · branch productivity · RoA tree · leverage and CRAR · P/B
one-year-forward band · P/B vs RoE scatter against peers.

## Valuation convention
**Target P/B × forward BVPS, justified by sustainable RoE.** Bajaj Housing Finance: ADD, TP
INR 88 at **2.5x FY28E BVPS** (JM Financial) — note the note itself shows the stock at 4.5x
falling to 2.3x across the forecast years, i.e. the target multiple sits below the entry
multiple and the return comes from book accretion, not re-rating. That is the honest structure
for a thin-spread, high-leverage lender.

Because the credit loss is small and the spread is thin, **the sensible sensitivity is on cost
of funds and spread, not on credit cost** — the reverse of the NBFC convention in
`nbfc_diversified`. A 25bps spread change moves RoE materially at 8-10x leverage; publish that
elasticity.

*Traps:* (i) capitalising a peak spread — see the structural-compression point above;
(ii) applying a prime HFC's multiple to an affordable lender with a rising non-housing book;
(iii) the rolled-forward base (`FY28E BVPS` from an FY26 vantage adds two years of accretion —
state the base year and show the un-rolled target); (iv) treating parentage-derived cost of
funds as permanent when the parent's own rating or support intent could change; (v) P/E, which
is leverage-contaminated here as everywhere in BFSI.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. The target is 2.5x FY28E BVPS while the stock trades at 4.5x.**
- *The target implies de-rating, so this is a sell* (`own_history_anchor`).
- *This is the honest structure* (`sustainable_roe`) — for a thin-spread, high-leverage
  lender the multiple compresses as book compounds, and the return comes from book
  accretion rather than re-rating. Bajaj Housing Finance is published exactly this way
  (JM Financial, ADD): 4.5x falling to 2.3x across the forecast years.
- *Discriminator* (`historical_distribution`) — where HFC multiples actually settled after
  comparable book-growth phases.

**2. The spread is 1.9%.**
- *Fragile* (`balance_sheet_risk`) — a 25bps move in cost of funds wipes out a tenth of it.
- *Adequate* (`sustainable_roe`) — RoE is spread times leverage, and at 8-10x leverage a
  1.9% spread supports a competitive RoE. Because credit loss is small and the spread is
  thin, the sensible sensitivity here is on cost of funds and spread, not on credit cost —
  the reverse of the NBFC convention.
- *Discriminator* (`peer_distribution`) — spread times leverage against realised RoE across
  HFCs, plus the ALM gap that decides whether the leverage is safe to carry.

## Forensic screens (sector-specific)
- Non-housing (developer/LAP/MSME) share rising while headline spread holds — margin is being
  bought with credit risk that has not seasoned.
- Disbursement growth far exceeding AUM growth — the book is leaking to balance transfer, and
  the origination cost of standing still is being capitalised into "growth".
- Developer-finance exposure not separately disclosed, or moved between segments.
- Restructured/one-time-restructuring pool ageing out of reported GNPA on a known schedule.
- Interest capitalisation on under-construction / subvention loans (moratorium-period interest
  added to principal) — real income today, elevated LTV tomorrow.
- ALM gaps in the short buckets funded by commercial paper — the 2018-19 sector template.
- Fee income from insurance cross-sell booked upfront rather than over tenor.
- Sharp fall in opex/AUM driven purely by AUM denominator growth rather than productivity.
- Title/valuation panel concentration; related-party developer exposure.

## Dependencies to map
NHB (refinance quota and pricing, CRAR norms) and RBI's HFC framework · the repo/rate cycle
and its asymmetric repricing · property prices and registration volumes by state ·
PMAY/CLSS-type subsidy schemes and their sunset dates · SARFAESI and DRT recovery timelines ·
stamp duty changes · the parent's rating for parented HFCs · competitive intensity from banks,
which is the direct cause of both balance-transfer run-off and spread compression.

## Common archetypes here
`quality-compounder` (a genuine funding-cost and underwriting franchise), `garp`,
`capex-to-cashflow` is *not* applicable here, `market-share-gainer` (common in affordable
housing — check whether the share is bought with LTV or with non-housing yield), and
`re-rating` where P/B is argued to move. `cyclical-recovery` applies mainly to developer-finance
books. Be sceptical of `margin-expansion` theses in this sector: the structural direction of
spread is down.
