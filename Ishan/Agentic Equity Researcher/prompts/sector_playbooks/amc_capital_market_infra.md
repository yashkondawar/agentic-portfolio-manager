# Sector Playbook — AMCs & capital-market infrastructure

*Tier 2. Family: `bfsi` (`prompts/sector_packs/bfsi.md`). Shared rules: `prompts/31`.*
**Provenance:** corpus-grounded — ICICI Prudential AMC (ICICI Securities, Apr-26), HDFC AMC
(HDFC Securities, Oct-20), CAMS (HDFC Securities, Feb-21, registrar/transfer agent), NSDL
(ICICI Securities, Nov-25, depository), Angel One (JM Financial, Sep-25) and Angel Broking
(Jan-21) for the broking model, CRISIL (HDFC Securities, Mar-22) for the ratings/analytics
annuity.

## The economic engine
Every business in this playbook charges a **small fee on someone else's asset or transaction**,
and carries almost no capital and almost no marginal cost. That produces the sector's two
defining features:

`Revenue = pool × yield` — where the pool is AAUM, folios, or transaction volume
`Operating margin` rises with the pool because costs are largely fixed

- **Operating leverage is extreme.** ICICI Prudential AMC's core EBITDA margin ran ~76.5%, with
  opex pegged at ~13.2bps of AUM against 15.2/14.9/13.3bps in FY24/FY25/FY26 — costs falling as
  a share of a rising pool is the whole earnings model.
- **Yield compression is structural and permanent.** This is the sector's central analytical
  fact. IPRU AMC's note models ~1.1bps of cumulative MF yield decline across FY26-28E to a net
  yield of 94-95bps in FY27E/FY28E; blended yield including AIF, PMS and advisory sits far lower
  (51.5bps, down 108bps QoQ in one quarter). TER caps ratchet down with scale by regulation,
  direct plans keep growing, and passives price at a fraction of active.

So the thesis is always the same arithmetic: **does pool growth outrun yield compression, and
does operating leverage convert the difference into earnings?** A forecast that holds yield flat
is not a forecast.

**Sub-model note.** The four models here differ enough to name: **AMCs** (pool = AAUM, yield in
bps, mix-driven); **depositories/RTAs/exchanges** (pool = folios, demat accounts or
transactions — near-monopoly, regulated pricing, annuity-like); **brokers** (pool = daily
turnover and active clients — cyclical, F&O-regulation-exposed); **ratings/analytics** (pool =
debt issuance and subscriptions — annuity plus a cyclical issuance kicker). Identify which one
before applying the KPI table, and record it in `state/triage.json`.

## Analysis sequence
1. **The pool and its composition.** For an AMC: QAAUM/AAUM split into equity, debt, liquid,
   passive, and alternates (AIF/PMS). For infrastructure: demat accounts, folios, transaction
   counts, active clients. **Mix is more important than size** because yields differ by an order
   of magnitude across it.
2. **Yield by product, in bps** — equity, debt, liquid, passive, alternates. Then the blended
   yield, then the *direction* and the reason. Separate regulatory TER compression from mix
   compression from competitive repricing; they have different durabilities.
3. **Flow quality, not just flow size.** SIP flow and SIP count are the annuity; lump-sum equity
   flow is procyclical and leaves. SIP stoppage ratio is the leading indicator everyone
   under-reports. IPRU AMC's stated moat is exactly this: "higher share in equity, SIPs and
   alternates".
4. **Market-share trend, measured in the right currency** — equity-oriented AAUM share, not
   total AAUM share (a liquid-fund mandate wins share and earns almost nothing). IPRU AMC:
   equity-oriented AAUM share +31bps QoQ to 14.1%, total QAAUM share +25bps to 13.5%.
5. **Distribution economics** — direct vs regular plan mix, top-distributor concentration, B-30
   incentive economics, and for brokers the client-acquisition cost and payback.
6. **Investment performance**, which is the only durable driver of flow for an active AMC.
   Percentage of equity AUM beating benchmark over 3 and 5 years, and fund-manager tenure.
   A performance-led flow story is defensible; a distribution-led one is rentable.
7. **The cost line as bps of the pool** — opex/AAUM is the operating-leverage measure and the
   number to forecast, not absolute cost growth.
8. **Regulatory and competitive threat map** — TER slab changes, passive share gain, discount
   brokerage, F&O position limits and STT, direct-plan growth.
9. **Then the operating margin and the earnings bridge**: pool growth − yield compression +
   operating leverage.

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **AAUM** (average AUM) | average assets under management, quarterly (QAAUM) | INR cr | The pool. Always split by asset class — total AAUM is a vanity number when liquid and equity yield differ ~5x. Use QAAUM for comparability | Company/AMFI disclosure |
| **Yield** | revenue from operations / avg AUM | bps | The sector's central variable and structurally falling. Report by product and blended, and state how much of any decline is TER regulation, mix, or price competition | Computed |
| **Equity mix** | equity-oriented AAUM / total AAUM | % | The revenue-quality measure — equity carries multiples of the debt/liquid yield and is stickier. Track equity-oriented *market share* separately from total share | AMFI + company |
| **Operating margin** | core operating profit / revenue | % | Extreme operating leverage means this rises with the pool; the honest forecast is opex in bps of AUM (IPRU: ~13.2bps target vs 15.2bps FY24), not a cost-growth rate | P&L |
| **SIP flow** | monthly systematic-investment-plan inflow | INR cr | The annuity in an otherwise procyclical business. Pair with SIP count and the **stoppage ratio** — gross SIP flow alone hides churn | Company/AMFI disclosure |

## Supporting KPIs
QAAUM by asset class and its mix trend; passive AUM share; alternates (AIF/PMS/advisory) AUM and
its separate yield; unique investors and folio count; new-folio additions; B-30 share; direct vs
regular plan mix; top-10 distributor concentration; SIP AUM as % of equity AUM; SIP stoppage
ratio; % of equity AUM outperforming benchmark over 3/5 years; fund-manager tenure and attrition;
opex as bps of AUM; employee cost as % of revenue; other income and treasury book (AMCs hold
large own-balance-sheet investments — separate this from operating earnings); dividend payout;
RoE (structurally very high on a small capital base — do not read it as a quality signal).
*For infrastructure:* demat/folio counts, transactions, market share, revenue per account or per
transaction, regulated vs non-regulated revenue split. *For brokers:* active clients, ADTO
(cash/F&O split), revenue per client, client-acquisition cost and payback, margin-funding book.

## Standard exhibit set
QAAUM by asset class over time · mix trend with blended yield overlaid on the same axis (the
single most informative exhibit in this sector) · yield by product in bps · TER regulatory slabs
and the company's position in them · equity-oriented market share vs total market share ·
SIP flow, SIP count and stoppage ratio · flow decomposition: SIP vs lump-sum vs redemption ·
% of equity AUM beating benchmark, 3y and 5y · passive-share encroachment on the industry pool ·
direct vs regular mix · distributor concentration · opex in bps of AUM vs peers ·
operating-margin trend against AAUM (the operating-leverage chart) · treasury/own-investment
book separated from operating earnings · P/E band · valuation on both P/E and % of AAUM.

## Valuation convention
**P/E on forward earnings, cross-checked as a percentage of AAUM.** Both are needed: P/E prices
the earnings, % of AAUM prices the franchise and is the metric M&A actually transacts on. HDFC
AMC was valued at **33.3x FY22E earnings** and the note says so explicitly — "at a premium to
other AMCs and many other BFSI companies" — which is the right way to state a premium: named,
quantified, and against a peer set.

Because the balance sheet holds a large own-investment book, **value the operating business on
earnings and add the treasury/investment book separately** where it is material; otherwise the
P/E silently prices cash at an operating multiple. For depositories, exchanges and RTAs, the
near-monopoly annuity supports a higher multiple than an AMC — but the price is regulated, so
model the regulator, not the market.

*Traps:* (i) **holding yield flat** — the single most common error, and it makes any forecast
wrong in a knowable direction; (ii) valuing peak-market AAUM on a peak multiple: the pool is
marked to a bull market, so AAUM and the multiple peak together (the sector's peak-on-peak
problem, exactly as in `prompts/thesis_archetypes/cyclical-peak.md`); (iii) reading the very
high RoE as a quality signal when it is an artefact of a tiny capital base; (iv) crediting total
AAUM share gains won in liquid funds; (v) ignoring the passive threat because current passive
share is small; (vi) treating a broker's F&O revenue as annuity when a single SEBI circular can
remove it.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at 33.3x forward earnings, a premium to other AMCs and to many BFSI names.**
- *Overpriced* (`peer_set_choice`) — the premium is stated but not earned.
- *Mid-range on the metric that matters* (`peer_set_choice`) — % of AAUM prices the
  franchise and is what M&A actually transacts on; P/E only prices this year's earnings.
  HDFC AMC's note states the premium in the right form: named, quantified, and against a
  peer set.
- *Discriminator* (`peer_distribution`) — both P/E and % of AAUM against the same peer set,
  cross-checked against realised transaction multiples.

**2. Reported PAT includes treasury gains on the own-investment book.**
- *Earnings are earnings* (`earnings_base_quality`).
- *The P/E is pricing cash at an operating multiple* (`earnings_base_quality`) — value the
  operating business on earnings and add the treasury book separately wherever it is
  material.
- *Discriminator* (`disclosed_mechanism`) — the segment disclosure separating operating
  revenue from investment income.

**3. Equity AAUM is compounding at 25%.**
- *Structural financialisation of savings* (`growth_durability`).
- *Partly a bull market* (`growth_durability`) — SIP flows are the durable component;
  mark-to-market is not, and it reverses with the index.
- *Discriminator* (`disclosed_mechanism`) — decompose AAUM growth into net flows versus MTM.

## Forensic screens (sector-specific)
- Blended yield falling while the company attributes flat revenue to "mix" — decompose into TER
  regulation, mix and price, and check the arithmetic closes.
- AAUM growth driven by liquid or arbitrage mandates (low yield, institutional, fast-leaving)
  presented as franchise growth.
- SIP gross flow rising while the **stoppage ratio** rises faster — net SIP is deteriorating
  behind a growing headline.
- Other income / treasury gains carrying the PAT beat; own-investment book marked up in a rising
  market and presented inside operating performance.
- Distributor commissions moved between "revenue net of commission" and expense presentations,
  changing both the reported yield and the expense ratio without changing economics.
- Scheme-performance disclosures switched to a favourable benchmark or period; the underperforming
  scheme quietly merged into a better one (a real and common practice that resets the track record).
- Related-party distribution through a promoter bank or broker — the single largest structural
  conflict in Indian AMCs, and it must be sized as a share of flows.
- For brokers: revenue concentration in F&O ahead of a known regulatory change; client-acquisition
  cost capitalised; margin-funding book growth as a substitute for brokerage growth.
- For infrastructure: unregulated-revenue growth (data, KYC, value-added services) presented at
  the regulated franchise's multiple.
- Employee-cost containment ahead of a fund-manager exit; fund-manager attrition undisclosed.

## Dependencies to map
SEBI — TER slabs and their scale-linked ratchet, total-expense and commission rules, direct-plan
regime, categorisation norms, F&O position limits and lot sizes, and pricing oversight of
exchanges/depositories/RTAs · AMFI's monthly industry data (the only market-share source) ·
equity and debt market levels and volatility, which set the pool directly · household financialisation
and the SIP culture's durability through a drawdown (untested at current scale) · passive/ETF
share gain and global fee-compression precedent · STT and capital-gains taxation · NPS and EPFO
allocation policy · the promoter bank's or broker's distribution reach for parented AMCs ·
interest rates for debt-fund flows and for float income · competitive entry (new AMC licences,
discount brokers, fintech distributors).

## Common archetypes here
`quality-compounder` (the default claim in this sector, and it needs pool growth *net of* yield
compression to be real), `garp`, `margin-expansion` (operating leverage — usually the most
defensible archetype here because the mechanism is arithmetic), `market-share-gainer` (check it
is equity-oriented share, not total), `regulatory-tailwind` or its inverse, and
`special-situation` for listings, stake sales and demergers of AMC arms out of banks. Watch
carefully for `cyclical-peak` dressed as `quality-compounder`: a bull-market AAUM and a
bull-market multiple make the same business look structurally better than it is.
