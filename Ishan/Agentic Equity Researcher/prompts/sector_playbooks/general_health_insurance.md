# Sector Playbook — General & health insurance (non-life)

*Tier 2. Family: `bfsi` (`prompts/sector_packs/bfsi.md`). Shared rules: `prompts/31`.*
**Provenance:** corpus-grounded — an insurance sector initiation covering the non-life and
standalone-health segments in depth (JM Financial, Oct-24, 70pp, 103 exhibits; Star Health, motor
and health industry structure, GDPI and loss-ratio series), with supporting insurance sector
notes from Kotak Institutional (Jan-23) and ICICI Securities (Oct-20, Aug-21). Note the corpus
has no standalone motor-insurer initiation; the motor content below leans on the sector note's
industry exhibits rather than a company file.

## The economic engine
A non-life insurer is two businesses bolted together, and **they must be analysed separately
before being combined**:

1. **Underwriting** — collect premium, pay claims and expenses. `Combined ratio = loss ratio +
   expense ratio`. Below 100% is an underwriting profit; above 100% means the underwriting
   business loses money.
2. **Float investment** — premium is collected before claims are paid, so the insurer invests
   other people's money. `Investment income` on the float is what turns a combined ratio of
   105% into a positive RoE.

`RoE ≈ [(1 − combined ratio) × net earned premium + investment income] / net worth`

Unlike life insurance, **the accounting is short-cycle and largely honest** — claims are settled
within a year or two — so P/B against RoE works here, and embedded value does not apply. The
judgement moves from actuarial assumptions to **reserving adequacy**.

**Segment economics differ so much that a blended view is useless.** From the JM sector note's
industry series: health has been the growth engine (industry health GDPI ~19% CAGR FY19-24,
retail health ~39% of total health), while motor growth has slowed with the underlying vehicle
cycle; "commercial lines and health have grown at the expense of motor and crop". Industry GDPI
compounded ~14.1% over FY14-24, with private players and standalone health insurers (SAHIs)
taking share from the PSUs — whose poor loss ratios are the reason.

## Analysis sequence
1. **Segment the book by GDPI**: motor OD, motor TP, retail health, group health, fire/property,
   marine, crop, engineering, liability. Then get the **loss ratio for each line**, because the
   mix explains the combined ratio entirely.
2. **Retail vs group within health** — retail health is the prize: higher margin, renewable,
   and priced by the insurer. Group health is frequently written at a loss to win a corporate
   relationship. Star Health's position rests on retail: FY24 leader with 33.1% of retail-health
   industry premiums, 41.8% among private players, and 13.8% of total health GDPI.
3. **Motor TP is a regulated, long-tail line.** Prices are set by IRDAI, claims settle over
   years through the courts, and reserving is where the judgement sits. Treat motor TP reserving
   as a forensic item, not an operating one.
4. **Combined ratio decomposed** into loss ratio and expense ratio, then the expense ratio
   against IRDAI's expenses-of-management (EoM) cap. Track both over at least five years.
5. **Distribution mix and its cost** — agency, broker, bancassurance, direct/online, motor
   dealer. Dealer-sourced motor business carries high commission; direct-online carries the
   lowest cost and the best retention. This is the expense-ratio driver.
6. **Reserving adequacy** — IBNR/IBNER development triangles, prior-year reserve movements, and
   the actuary's history. **Favourable prior-year development flattering the current combined
   ratio is the sector's classic quality issue.**
7. **The float and its yield** — investment book size, asset mix (mostly government and
   corporate debt under IRDAI rules), and realised vs unrealised gains.
8. **Solvency ratio** against the 1.5x floor and the growth it funds.
9. **Then RoE, decomposed into underwriting and investment contribution** — state which one is
   carrying the return.

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Combined ratio** | loss ratio + expense ratio | % | The quality gate: **below 100% is an underwriting profit**, and an insurer that needs investment income to be profitable is a leveraged bond fund with claims risk. Report on a net-earned basis and state the basis | Computed from P&L |
| **Loss ratio** | net incurred claims / net earned premium | % | Per line of business, never blended. The PSUs' poor loss ratios are the structural reason private players and SAHIs keep taking share | Segment reporting |
| **Expense ratio** | (commission + operating expenses) / net written premium | % | Against the IRDAI EoM cap and against the distribution mix that produces it. Falling expense ratio with rising direct/online share is real leverage | P&L |
| **GWP / GDPI growth** | gross written (direct) premium, YoY | % | Against the industry line-by-line — health ~19% CAGR FY19-24 vs motor slowing. Growth above industry in a *loss-making* line is not good news | Company + IRDAI/GI Council data |
| **Investment yield** | investment income / avg investment assets | % | The float return. Separate realised gains from accrual income; only the accrual is repeatable | Investment schedule |

## Supporting KPIs
GDPI by line and its mix trend; retail vs group health split; motor OD vs TP split; claims
settlement ratio and turnaround time; incurred-but-not-reported (IBNR) as % of reserves;
prior-year reserve development; net retention ratio (premium retained after reinsurance);
reinsurance commission; float size and float/net-worth multiple; solvency ratio; RoE split into
underwriting and investment; policy count and lives covered; renewal/retention rate in retail
health; average premium per policy; hospital-network size and cashless-claim share; fraud-detection
savings; distribution mix by channel with commission cost each; agent and broker counts;
combined ratio excluding one-off catastrophe or crop losses.

## Standard exhibit set
GDPI by line with growth and loss ratio side by side · industry GDPI growth vs the company's,
by line · retail vs group health mix · combined ratio decomposed into loss and expense over
5-10 years · loss ratio by line vs private peers and PSUs · expense ratio vs the EoM cap ·
distribution mix with commission cost by channel · reserve development triangles / prior-year
development · net retention and reinsurance structure · float size and investment yield ·
solvency ratio vs the 1.5x floor · RoE split into underwriting vs investment contribution ·
market share by line vs private peers, SAHIs and PSUs · retail-health renewal rate ·
P/B one-year-forward band · P/B vs RoE scatter against peers.

## Valuation convention
**Target P/B against sustainable RoE, with the combined ratio as the quality gate.** This is the
one BFSI child where the underwriting-profitability screen precedes the multiple: an insurer
with a combined ratio consistently below 100% deserves a materially higher P/B than one at 110%
earning the same RoE, because the former's return does not depend on the float or on rates.

For standalone health insurers with high growth and low current profitability, P/E on a
normalised year or a multiple of *retail* GDPI can be used as a cross-check — but state the
normalisation. **Embedded value does not apply here** (contracts are annual); anyone importing
it from life insurance has made a category error worth flagging.

*Traps:* (i) accepting a combined ratio flattered by **favourable prior-year reserve
development** — strip it and restate; (ii) blending motor TP's long-tail reserving risk into a
health-led growth story; (iii) capitalising a soft-market pricing cycle (commercial lines and
crop are cyclical in price, not just in loss); (iv) valuing group-health growth on retail-health
economics; (v) treating realised investment gains as recurring income; (vi) comparing combined
ratios across companies using different bases (net vs gross, EoM treatment) without adjusting.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. The combined ratio is 104%.**
- *A loss-making underwriter* (`earnings_base_quality`) — it pays out more than it takes in.
- *Profitable overall* (`sustainable_roe`) — investment income on float more than covers
  the underwriting loss and RoE is 14%.
- *Discriminator* (`historical_distribution`) — the CR trend over a full pricing cycle, and
  whether the investment yield carrying the RoE is itself rate-cycle dependent.

**2. Two insurers earn the same 15% RoE.**
- *Same P/B* (`sustainable_roe`) — identical returns, identical price.
- *Materially different P/B* (`earnings_base_quality`) — the one at a 97% combined ratio
  deserves more than the one at 110%, because the first's return does not depend on the
  float or on rates. This is the one BFSI child where the underwriting-profitability screen
  precedes the multiple.
- *Discriminator* (`peer_distribution`) — decompose RoE into underwriting and investment
  contribution across the peer set.

**3. A note imports an embedded-value multiple from life insurance.**
- *Consistent with BFSI practice* (`peer_set_choice`).
- *A category error* (`accounting_basis`) — health contracts are annual, so there is no
  in-force book to capitalise. Worth flagging wherever it appears.
- *Discriminator* (`disclosed_mechanism`) — contract tenor. This one resolves cleanly.

## Forensic screens (sector-specific)
- **Prior-year reserve releases** improving the current combined ratio — the single most
  important screen in non-life. Read the development triangles, not the headline.
- Motor TP reserving below the industry's own severity-inflation trend; TP claims inflation
  running ahead of the reserving assumption.
- Growth concentrated in group health at a loss ratio above 100%, presented as market-share gain.
- Expense ratio managed by reclassifying commission as "other outgo", or by pushing costs into
  a distribution subsidiary — check against the EoM cap and any related-party distributor.
- Claims settlement ratio high while claim *repudiation* and turnaround time worsen; grievance
  volumes rising at IRDAI.
- Crop-insurance participation swinging the loss ratio between years — separate it and show the
  book both ways.
- Reinsurance used to cede loss-making business at commission terms that flatter the net ratio;
  falling net retention alongside improving reported ratios.
- Health-portfolio price increases taken on renewal (which regulators and customers resist)
  presented as premium growth rather than as price.
- Hospital-network tariff arrangements with related parties; cashless-claim denial rates.
- Investment book taking credit risk to lift the float yield — check the rating distribution.

## Dependencies to map
IRDAI — motor TP tariff orders, EoM limits, product filing (use-and-file), solvency norms and
the risk-based-capital transition · the General Insurance Council's industry data (the only
line-level market-share source) · vehicle sales and the VAHAN registration series, which drive
motor OD/TP volume directly (link to `auto_oem`) · hospital tariff inflation and NPPA price caps
on consumables, which are the health loss ratio's cost side (link to `hospitals`) · Ayushman
Bharat and state schemes as both competitor and channel · PMFBY crop-scheme design and state
participation · GST on insurance premium and the Feb-25/Sep-25 policy debate · interest rates
and the yield curve for float income · catastrophe exposure and global reinsurance pricing ·
motor third-party claims inflation and MACT court behaviour · PSU insurer recapitalisation and
pricing discipline, which sets the market's price floor.

## Common archetypes here
`market-share-gainer` (private and SAHI share gain from PSUs — the sector's structural story,
and the one archetype here with genuine industry evidence behind it), `margin-expansion`
(combined-ratio improvement — demand the loss/expense split), `regulatory-tailwind` or its
inverse, `garp`, and `quality-compounder` for insurers with a durable retail franchise and a
sub-100% combined ratio. `cyclical-recovery` applies to commercial lines' pricing cycle. Treat
`re-rating` claims with the standard skepticism weight, and note that in this sector a
re-rating argument is often really a reserving argument in disguise.
