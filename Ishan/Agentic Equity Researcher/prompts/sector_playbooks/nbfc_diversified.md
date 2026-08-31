# Sector Playbook — Diversified retail NBFC

*Tier 2. Family: `bfsi` (`prompts/sector_packs/bfsi.md`). Shared rules: `prompts/31`.*
**Provenance:** corpus-grounded — HDB Financial Services (ICICI Securities, Mar-26, 66pp,
103 exhibits), Capri Global (Nuvama, Jul-25), Bajaj Housing Finance (JM, Mar-26),
MAS Financial (Anand Rathi, Dec-24), Cholamandalam (Jan-17).

## The economic engine
A lender earns the spread between what it pays for money and what it charges for risk,
minus what the risk actually costs and what it costs to originate. Every KPI below is a
term in that identity:

`RoA = (yield − cost of funds − credit cost − opex/assets) × leverage → RoE`

The whole analysis is deciding which of those four terms is durable and which is a
cycle.

## Analysis sequence
1. **Liability franchise first, not the loan book.** Cost of funds versus peers is the
   most durable competitive variable in Indian lending, and it is usually parentage,
   rating or deposit access rather than skill. Establish it before anything else.
2. **Decompose the book** by product, and for each: yield, ticket size, tenor, secured
   share, and who the customer is. Product mix explains most of the yield differential.
3. **Underwriting record across a full cycle** — credit cost per year for 10 years
   against the through-cycle average. One good vintage proves nothing.
4. **Sourcing and distribution** — direct vs DSA vs digital; branch count, productivity
   and geographic tier. This drives opex and, over time, credit quality.
5. **Asset-quality plumbing** — GNPA, NNPA, PCR, slippages, write-offs as a share of
   slippages, restructured pool, and the seasoning of recent growth.
6. **Capital and growth capacity** — CAR/CET-1, leverage, and how much growth the current
   capital funds before a raise.
7. **Then the RoA tree**, assembled from the above, and RoE from leverage.

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Cost of funds** | interest expense / avg borrowings | % | vs peers; the single most durable edge. HDB's advantage is the whole first pillar of its thesis | P&L + borrowings note |
| **Credit cost** | provisions / avg AUM (or avg advances) | % | Always against the company's own 10-year average. HDB: ~2% decade average, 2.5% current, 2.2% forecast — the entire RoE recovery | P&L + AUM |
| **NIM / spread** | NII / avg earning assets | % | Decompose into yield and cost of funds; do not read the net alone | P&L |
| **RoA** | PAT / avg assets | % | The comparable profitability measure across differently-levered lenders | Computed |
| **Average ticket size & tenor, by product** | disbursement / accounts; weighted tenor | INR, months | Explains yield and credit cost differences between apparently similar books. Rarely in the financials — comes from decks and RHPs. HDB's product-level ATS *and* tenor, plus ~80% direct sourcing and the tier-4+ branch share, are the corpus's benchmark for KPI granularity (`docs/ER_CORPUS_FINDINGS.md` §7.5) | Presentations, RHP |

## Supporting KPIs
AUM growth; product mix %; secured/unsecured split; direct-sourcing share; GNPA/NNPA/PCR;
slippage ratio; write-offs as % of slippages; opex/avg AUM; cost-to-income; branch count
and % in tier-3/4+ towns; customers; state concentration (largest state % of AUM);
borrowing mix (NCD/bank/CP %); external credit rating; CAR/CET-1; BVPS.

## Standard exhibit set
Cost of borrowings vs peers · AUM mix by product · AUM growth vs system · credit cost vs
own decade average · GNPA/NNPA trend and vs peers · slippages and write-offs · opex/AUM
vs peers · product-wise ATS and tenor · sourcing mix · branch count and tier
distribution · state concentration · borrowing mix and rating table · secured/unsecured ·
cross-cycle RoE · P/B 1-year forward band · P/E 1-year forward band · valuation vs peers.

## Valuation convention
**Target P/B × forward BVPS**, with the multiple justified by sustainable RoE. HDB: 3x
Sep'27E BVPS → TP 900. The P/B–RoE relationship is the sector's cross-sectional anchor;
a lender earning 16% RoE and one earning 11% should not trade at the same P/B.

*Traps:* (i) applying a peer P/B without matching RoE **and** credit-cost volatility;
(ii) the rolled-forward base — `Sep'27E BVPS` quietly adds a year of book growth, so
state the base year and show the un-rolled target; (iii) P/E is nearly useless here
because leverage differs.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at 3x forward BVPS against a sector median of 1.8x.**
- *Expensive* (`peer_set_choice`) — 67% above the median lender.
- *Justified* (`sustainable_roe`) — 18% RoE against a peer set averaging 12%; a lender
  earning 16% and one earning 11% should not trade at the same P/B.
- *Discriminator* (`peer_distribution`) — the P/B-to-RoE line across the peer set, and
  whether that 18% has survived a full credit cycle or only this one.

**2. Credit cost is 1.1%, the lowest in five years.**
- *Underwriting has structurally improved* (`disclosed_mechanism`).
- *The book is young* (`cycle_position`) — a fast-growing book always prints a low credit
  cost because the denominator outruns the numerator; the losses arrive on a lag.
- *Discriminator* (`historical_distribution`) — static-pool or vintage loss curves by
  disbursement cohort. Portfolio-level credit cost cannot separate the two; cohort curves
  can.

**3. Cost of funds fell 60bps.**
- *Permanent* (`disclosed_mechanism`) — a rating upgrade re-priced the whole liability
  stack.
- *Temporary* (`cycle_position`) — the rate cycle turned and will turn back.
- *Discriminator* (`disclosed_mechanism`) — the dated rating action, and the incremental
  borrowing mix versus the back book.

## Forensic screens (sector-specific)
- Growth concentrated in unsecured or new products → credit cost is *unseasoned*, not low.
- Write-offs running high as a share of slippages → GNPA is being managed by write-off.
- Restructured/ECLGS pool ageing out of the reported GNPA.
- Yield rising while credit cost is flat → risk is being taken and not yet recognised.
- Opex/AUM falling purely through denominator growth (fast AUM growth) rather than
  productivity.
- Related-party BPO or sourcing arrangements with a parent (HDB provides BPO services to
  HDFC Bank — a real item that distorts the opex comparison and which ICICI's note
  correctly adjusts for).

*Disconfirming-exhibit benchmark:* the same HDB note publishes an exhibit showing the company
grew **slower** than peers over three years, inside a BUY (`docs/ER_CORPUS_FINDINGS.md` §7.3).
That is the standard `prompts/34` check #10 holds our own note to.

## Dependencies to map
Parent/promoter (rating and funding access) · RBI regulation (upper-layer NBFC norms,
digital-lending rules, risk weights) · rate cycle · the underlying asset cycle per product
(CV freight rates, property prices for LAP, rural cash flow for MFI) · co-lending partners
· credit-bureau data availability.

## Common archetypes here
`quality-compounder` (franchise + cost-of-funds moat), `cyclical-recovery` (credit-cost
normalisation), `market-share-gainer` (rare; check the denominator), and `re-rating` where
P/B is argued to move — apply the 40% rule.
