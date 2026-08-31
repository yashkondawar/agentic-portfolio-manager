# Sector Playbook — Private / scheduled commercial banks

*Tier 2. Family: `bfsi` (`prompts/sector_packs/bfsi.md`). Shared rules: `prompts/31`.*
**Provenance:** corpus-grounded — Karur Vysya Bank (BOB Capital, Sep-25, 21pp, 45 exhibits),
Equitas Small Finance Bank (Nirmal Bang, Oct-21), a large-banks sector note (Kotak
Institutional, Sep-23, 27pp), ICICI Bank (Apr-19).

## The economic engine
A bank borrows retail deposits at a price it partly controls and lends at a price the market
mostly sets. Unlike an NBFC, **the liability side is a franchise rather than a purchase** — a
current account costs nothing and a savings account costs less than wholesale funding, so the
deposit mix *is* the competitive advantage:

`RoA = (NIM + fee income/assets − opex/assets − credit cost) × (1 − tax) → RoE = RoA × leverage`

Deposits are also the growth constraint. A bank cannot lend what it has not raised, so
**loan growth above deposit growth is a liability-side promise, not an asset-side achievement**
— check the credit-deposit ratio before crediting any growth forecast.

## Analysis sequence
1. **The deposit franchise first, and in this order:** CASA ratio, the savings rate being paid
   to get it, deposit granularity (retail vs bulk vs certificate of deposit), and the
   credit-deposit ratio. Equitas raised CASA from 25% to ~45% — but paid the highest savings
   rate among the top three SFBs to do it, which is a purchased franchise, not an inherited
   one. Always pair the CASA ratio with its price.
2. **Loan-book composition** by segment (corporate / SME / retail / agri) with yield and
   secured share for each, and the *direction of travel*. KVB's whole re-rating is a mix shift:
   corporate exposure down to 14% (Jun'25) from 37% (Mar'15), unsecured held at 2.1% of net
   loans (FY25).
3. **Underwriting quality across a full cycle, using forward-looking measures.** Reported GNPA
   is a lagging outcome. The leading indicators are slippage ratio, the rated mix of the
   corporate book, and **stressed assets as a % of CET-1** — KVB's improved to 8.9% (Q1FY26)
   from 50.3% (FY21), which says far more than GNPA falling to 0.66% from 7.8%.
4. **Provisioning adequacy** — PCR, the unprovided residue, and whether write-offs are doing
   the work that provisions should. This determines whether book value is real.
5. **Fee income and its quality.** Granular retail fees (cards, distribution, forex) deserve a
   multiple; lumpy corporate and treasury gains do not. Split them.
6. **Capital and dilution risk** — CET-1, the growth it funds at the current RoE, and the
   date at which a raise becomes necessary. State the dilution in the target price.
7. **Then the RoA tree**, and RoE from leverage. Only now is the multiple discussable.

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Net interest margin** | NII / avg interest-earning assets | % | Decompose into yield on advances and cost of deposits; never read the net alone. Corpus notes chart the two as separate exhibits for exactly this reason | P&L + balance sheet |
| **CASA ratio** | (current + savings) / total deposits | % | The franchise measure — but always beside the savings rate paid. A high CASA bought with a high rate is not a moat | Deposit schedule |
| **Credit cost** | provisions / avg advances | % | Against the bank's own 10-year average, not the last three years. Slippages below ~90bps sustained (KVB, FY23-25) is genuinely good | P&L + advances |
| **Cost-to-income** | opex / (NII + other income) | % | Falling C/I via revenue growth is operating leverage; via cost suppression it is deferred investment. Distinguish them | P&L |
| **GNPA (with NNPA and PCR)** | gross NPA / gross advances | % | A lagging measure. Report it, but lead with slippages and stressed-assets-to-CET-1 | Asset-quality disclosure |
| **RoA** | PAT / avg total assets | % | The leverage-neutral profitability measure — the only one comparable across banks | Computed |
| **Advances growth** | YoY growth in gross advances | % | Against system credit growth *and* against the bank's own deposit growth. Growth funded by bulk deposits is rented | Balance sheet |

## Supporting KPIs
Yield on advances; cost of deposits; credit-deposit ratio; CET-1 and total CAR; slippage
ratio; write-offs as % of slippages; restructured and ECLGS residue; PCR; provision coverage
excluding technical write-offs; BB-and-below rated corporate exposure (KVB: 31% in Q1FY26 vs
55% in FY21); priority-sector-lending shortfall and RIDF deposits; branch and ATM count with
urban/semi-urban/rural split; deposits and advances per branch; employee productivity;
BVPS and **adjusted** BVPS; opex/assets; fee income as % of total income; treasury gains as %
of PBT; digital-transaction share; SMA-1/SMA-2 pools.

## Standard exhibit set
CASA ratio trend and vs peers · savings rate paid vs peers · deposit mix (retail/bulk/CD) ·
credit-deposit ratio · advances mix by segment with direction of travel · yield on advances vs
cost of deposits (two lines, one chart) · NIM walk · slippage ratio by year · GNPA/NNPA/PCR
trend · stressed assets as % of CET-1 · BB-and-below corporate exposure · credit cost vs own
decade average · cost-to-income trend · fee-income composition · RoA tree bridge · RoE
decomposition · CET-1 and the capital-raise trigger · P/ABV one-year-forward band · valuation
vs peers on P/ABV against RoE.

## Valuation convention
**Target P/ABV × forward adjusted BVPS, anchored to sustainable RoE.** Note the corpus writes
**ABV, not BV** — adjusted book value nets off net NPAs (and sometimes other unprovided
items), and for a bank with an asset-quality history the distinction is the whole valuation.
Worked examples: KVB at **1.5x Jun'27E ABV** → TP 251 (BOB Capital); Equitas SFB at
**2.25x Sept'23 P/ABV** → TP 89 against 1.6x trading (Nirmal Bang). P/E is secondary and
leverage-contaminated.

Where the bank owns material subsidiaries (AMC, insurance, broking), value the **core bank on
P/ABV and add the stakes separately**, at a holdco discount, and publish the implied blended
multiple as a sanity check — the pattern `specialty_chemicals` uses for SOTP.

*Traps:* (i) using BV where ABV is warranted — this silently capitalises unprovided stress;
(ii) applying a peer P/B without matching *both* sustainable RoE and credit-cost volatility;
(iii) the rolled-forward base — `Jun'27E ABV` embeds a year of book accretion, so state the
base year and show the un-rolled target (see `docs/ER_CORPUS_FINDINGS.md` §4); (iv) valuing
pre-dilution book when the capital plan requires a raise; (v) crediting a CASA-led NIM story
without checking the savings rate that bought it.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. The bank trades at 1.2x book; the peer trades at 2.4x.**
- *Cheap* (`peer_set_choice`) — half the peer multiple for the same deposit franchise.
- *Correctly priced* (`sustainable_roe`) — it earns 9% RoE against the peer's 17%. P/ABV
  scales with sustainable RoE, so 1.2x on 9% and 2.4x on 18% are the same price for a
  rupee of return.
- *Discriminator* (`peer_distribution`) — regress P/ABV on sustainable RoE across the peer
  set and read where this bank sits against the line. A residual is the argument; the raw
  multiple gap is not.

**2. GNPA is 3.1%, down from 6.2% three years ago.**
- *Asset quality repaired* (`own_history_anchor`) — halved off its own peak.
- *Flattered* (`earnings_base_quality`) — the fall came from write-offs and ARC sales, not
  recoveries; the slippage ratio is flat.
- *Discriminator* (`disclosed_mechanism`) — the opening-to-closing NPA bridge: slippages,
  upgrades, recoveries, write-offs. Only recoveries and upgrades evidence repair.

**3. Book value per share is the book value per share.**
- *Take it as stated* (`earnings_base_quality`) — reported net worth, audited.
- *It overstates* (`earnings_base_quality`) — the corpus writes **ABV, not BV** for a
  reason: adjusted book nets off net NPAs and other unprovided items, and for a bank with
  an asset-quality history that gap is the whole valuation.
- *Discriminator* (`historical_distribution`) — provision coverage against the bank's own
  realised loss-given-default across the last cycle.

## Forensic screens (sector-specific)
- Loan growth persistently above deposit growth, funded by CDs or refinance — rented growth.
- Write-offs large as a share of slippages → GNPA is being managed, not resolved.
- SMA-2 pool rising while GNPA falls — the stress is queued, not gone.
- Restructured/ECLGS pool ageing out of reported GNPA on a known schedule.
- Interest income accrued on stressed accounts not yet classified NPA.
- Treasury gains or one-off recoveries carrying the PAT beat (KVB's own recovery from
  technically-written-off accounts is disclosed and must be stripped before extrapolating).
- PSL shortfall parked in RIDF deposits — a real yield drag that hides in "other assets".
- Fee income lumpiness dressed as annuity; related-party distribution arrangements with a
  group insurer or AMC.
- Divergence between the bank's own asset classification and an RBI risk-assessment report
  (the AQR-style divergence disclosure) — a direct measure of management's optimism.

## Dependencies to map
RBI — repo path, CRR/SLR, risk weights (the Nov-23 unsecured-lending change is the template),
PSL norms, licensing and branch-expansion rules · the deposit-competition environment (system
credit-deposit ratio) · the corporate credit cycle and, separately, the retail/unsecured cycle ·
DICGC premium · government recapitalisation and merger policy for PSU comparators · MFIN/CRIF
bureau data for the retail book · sector-specific stress channels — for KVB, US tariff exposure
of borrowers ("exposure at impact", 1.2% of gross loans) is a worked example of a
macro-transmission screen worth replicating.

## Common archetypes here
`cyclical-recovery` (credit-cost normalisation — the most common), `turnaround`
(asset-quality repair; KVB is the corpus's cleanest instance), `quality-compounder` (a genuine
deposit franchise), `re-rating` where P/ABV is argued to move — apply the 40% rule from
`prompts/33` — and `balance-sheet-repair`. Be alert to `market-share-gainer` claims that are
really a rented-liability story.
