# Sector Playbook — Defence manufacturing

*Tier 2. Family: `auto_engineering` (`prompts/sector_packs/auto_engineering.md`). Shared rules:
`prompts/31`.*
**Provenance:** corpus-grounded — Bharat Electronics (ICICI Securities, Jul-25 — an ADD initiation with
the order-book/execution and receivable-days detail this playbook is built on), Hindustan Aeronautics
(JM Financial, Apr-26), with Bharat Bijlee (Sushil Finance, Oct-22) and Thermax (JM Financial, Jan-26)
as engineering-order-book comparators and `epc_construction` as the authored sibling for order-book
conversion method.

## The economic engine
A defence manufacturer sells **a small number of very large, very long, technically complex contracts to
a single customer that is also its regulator, its financier and its majority shareholder in most cases.**
That produces an economic profile with no close analogue elsewhere in the registry:

`Revenue = order book × execution rate` — and the execution rate, not demand, is the binding variable

- **Demand is not the constraint; execution is.** The order pipeline is effectively guaranteed by the
  Ministry of Defence's indigenisation agenda. What limits revenue is the company's — and its vendors' —
  ability to convert. BEL's own disclosed risks name it exactly: "delay in awarding of orders" and
  "slower execution due to downstream partners unable to ramp-up adequately." **A defence thesis is an
  execution thesis, and the order book is the least uncertain part of it.**
- **Order book is not revenue, and the conversion period is long.** BEL's order book stood at
  **INR 748.6bn** with order inflow **>INR 100bn in YTD-FY26** — several years of revenue. Apply the
  company's own historical conversion rate rather than a uniform assumption, exactly as
  `epc_construction` requires.
- **The balance sheet carries the government's payment behaviour.** BEL's **receivable days run
  152 → 162 → 155** and inventory 153 → 140 days across the forecast years. Those are extraordinary
  numbers by any other sector's standard and they are structural, not a red flag in themselves — but they
  mean **the cash cycle is ~300 days and working capital is the real capital employed.** Advances from
  the customer are what make the model work; track them.
- **Margin comes from indigenous content, and is diluted by bought-out content.** BEL's disclosed margin
  risk is "margin compression due to higher proportion of bought-out components." An order won on a
  platform the company largely imports and integrates earns far less than one it designs and builds.
  **The indigenous-content ratio is the margin driver**, and it is also the policy objective — the two
  are aligned, which is unusual and worth stating.

Returns can be excellent despite this: BEL runs RoCE ~20-22%, RoE ~28-32% and **RoIC ~42-45%** — the gap
between RoE and RoIC being the customer advances funding the business.

## Analysis sequence
1. **Order book, decomposed** — by platform/programme, by customer arm (Army/Navy/Air Force/paramilitary/
   exports), by expected execution year, and by age. Then **book-to-bill** and the historical
   order-to-revenue conversion rate. BEL's programme-level disclosure (LRSAM ~INR 30bn, Himshakti
   ~INR 17bn, Akash and others in FY26 execution) is the granularity to demand.
2. **Order inflow pipeline against the award calendar** — Acceptance of Necessity (AoN) granted, RFPs
   issued, trials completed, L1 positions, and contracts at CCS (Cabinet Committee on Security) stage.
   **The Indian defence award process has named, trackable gates; use them rather than management
   guidance.**
3. **Execution capability and the vendor ecosystem.** Capacity, skilled headcount, and — critically —
   the tier-2/tier-3 vendor base's ability to ramp. BEL's own risk disclosure elevates this to first
   order, and it is the most common cause of slippage.
4. **Indigenous content ratio by programme**, and the bought-out/import share. Then margin by
   programme where obtainable. This is the margin bridge.
5. **The indigenisation policy stack** — positive indigenisation lists, Buy Indian-IDDM categories,
   offset obligations, and the strategic-partnership model. Then which of the company's programmes each
   one protects or threatens.
6. **Receivables, advances and the cash cycle.** Receivable days by customer arm, advances received
   against orders, and the net working-capital investment per rupee of revenue. Government payment
   behaviour is seasonal — it clusters around fiscal year-end.
7. **R&D and technology position** — in-house R&D spend, DRDO technology-transfer dependence, and
   engineer headcount (BEL adding 700-1,000 engineers to R&D is a capability investment that precedes
   revenue). Distinguish own IP from licensed production, because they have different margins and
   different durability.
8. **Exports and diversification** — export order book, non-defence revenue (BEL's civilian
   electronics, HAL's civil aviation work). Exports carry better margins and diversify the single-customer
   risk, and are the government's stated objective.
9. **Then execution-based earnings and the multiple.**

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **Order book** | value of unexecuted confirmed orders | INR cr | With the execution schedule and the age profile. BEL: INR 748.6bn. **A number without a conversion schedule is not visibility** — decompose by expected execution year and by programme | Company disclosure |
| **Book-to-bill** | order book / trailing revenue | x | The visibility measure. Very high ratios (3-5x) are normal here and are not automatically good — they can mean slow execution rather than strong demand. Read with the execution rate | Computed |
| **Execution rate** | revenue in the period / opening order book | % | **The binding variable in this playbook.** Compare against the company's own history; a forecast assuming an execution rate above anything it has achieved is the most common failure mode. BEL's own risk language points at the vendor base as the limiter | Computed |
| **Govt receivable days** | receivables from government/defence customers / revenue × 365 | days | Structurally high and seasonal (BEL: 152-162 days). Track alongside **customer advances**, which offset it — the net working-capital investment is the real number, and advances are what make the returns work | Balance sheet, decks |
| **EBITDA margin** | EBITDA / revenue | % | Bridge into programme mix and, above all, the **indigenous vs bought-out content** share — BEL names bought-out proportion as its margin risk. Also separate provision write-backs and liquidated damages | P&L |

## Supporting KPIs
Order inflow by year and by programme; orders at AoN / RFP / trials / L1 / CCS stage in the pipeline;
order book by customer arm and by expected execution year; order-book age profile; indigenous content %
by programme and overall; bought-out and import content share; programme-level margin where disclosed;
revenue from own-IP vs licensed/ToT production; export order book and export revenue share; non-defence
revenue share; capacity and capacity utilisation by facility; skilled/engineer headcount and R&D
headcount additions; in-house R&D as % of revenue and its capitalisation policy; DRDO technology-transfer
dependence per programme; inventory days split raw material / WIP / finished goods (WIP dominates on long
programmes); customer advances as % of order book; net working capital as % of revenue; cash and
treasury income (these companies often hold large net cash from advances — separate treasury income from
operating earnings); liquidated damages levied and provided; RoCE, RoE and **RoIC** (BEL: ~42-45%,
and the RoE-RoIC gap is the advance funding); fixed-asset turnover; dividend payout; offset obligations
outstanding.

## Standard exhibit set
Order book by programme with the expected execution year for each · order book by customer arm ·
order-book age profile · book-to-bill and execution rate over 5-10 years, with the forecast execution
rate marked against history (the exhibit that tests the thesis) · order-inflow pipeline by award-process
stage (AoN / RFP / trials / L1 / CCS) with expected award dates · **indigenous vs bought-out content by
programme, against margin** · revenue from own IP vs ToT production · **receivable days and customer
advances on one chart, with net working capital as % of revenue** · inventory split with WIP shown
separately · quarterly revenue seasonality (defence revenue is heavily Q4-weighted — show it, or the
quarterly model is wrong) · export order book and export share · non-defence diversification · R&D spend
and engineer headcount · capacity and utilisation · RoCE / RoE / RoIC with the advance-funding gap
explained · net cash and treasury income separated from operating earnings · P/E band against the
company's own history · peer table on execution rate, book-to-bill and indigenous content.

## Valuation convention
**P/E on forward *executed* earnings — the order book is not revenue, and must be converted at a
defensible historical rate before it reaches the multiple.** This is the registry's stated convention
and it is the discipline this sector most often abandons.

BEL is stated at **45x FY27E EPS** (ICICI Securities, ADD, TP INR 420). That is a high multiple by any
absolute standard, and the honest way to present it is as the market's assessment of a decade of
visible, policy-guaranteed demand plus ~45% RoIC — **not** as a normal industrial multiple. Two
disciplines follow:

1. **Say what growth rate and execution rate the multiple implies**, and compare both against the
   company's own record. A 45x multiple on a business whose execution rate has never exceeded X% is a
   bet on X improving; name it.
2. **Note that the sector's multiples are themselves cyclical with the policy cycle.** Indian defence
   multiples expanded substantially through the indigenisation push; a multiple set at that level embeds
   a policy environment. Apply `prompts/33`'s 40% rule — for most defence names in a re-rated market,
   a large share of expected return is the multiple holding rather than earnings compounding, and that
   should be stated rather than assumed.

A **DCF or explicit long-horizon model is more defensible here than in most sectors**, because the order
book gives genuine multi-year visibility — use it as a cross-check and publish the terminal assumptions.
Where the company has separable non-defence or export legs, consider SOTP; where it holds large net cash
from advances, value the operating business and add the cash rather than letting the P/E price it.

*Traps:* (i) **treating the order book as revenue** without the conversion rate — the sector's defining
error; (ii) assuming an execution rate the company has never delivered; (iii) capitalising a
policy-cycle multiple; (iv) valuing consolidated earnings that include treasury income on customer
advances at an operating multiple; (v) ignoring that revenue is Q4-heavy, so a nine-month run-rate
misleads; (vi) crediting AoN-stage or "pipeline" orders as order book; (vii) missing that a
ToT/licensed-production programme earns materially less than an own-IP one, so mix matters more than
volume.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at 45x FY27E EPS.**
- *Expensive by any absolute industrial standard* (`own_history_anchor`) — BEL is stated at
  exactly this (ICICI Securities, ADD, TP INR 420).
- *Not an industrial multiple* (`growth_durability`) — the honest framing is the market's
  assessment of a decade of visible, policy-guaranteed demand plus ~45% RoIC. Presenting it
  as a normal industrial multiple is what makes it look indefensible.
- *Discriminator* (`historical_distribution`) — say what growth rate and execution rate the
  multiple implies, and compare both against what the company has actually achieved.

**2. The order book is 4x revenue.**
- *Four years of visibility* (`growth_rate`).
- *Not revenue* (`earnings_base_quality`) — the order book must be converted at a defensible
  historical execution rate before it reaches the multiple. The same rule as
  `epc_construction`, and for the same reason.
- *Discriminator* (`historical_distribution`) — realised book-to-bill and the company's own
  record of execution slippage against original schedules.

## Forensic screens (sector-specific)
- **Order book including orders at AoN, LoI or MoU stage** rather than confirmed contracts; the order-book
  definition changed between periods; the same order counted at award and at contract signature.
- Execution rate assumed to improve with no capacity or vendor-base change to support it.
- Revenue recognised on percentage-of-completion with a cost-to-complete estimate that keeps being revised
  — check the revision history on long programmes, since POC accounting in defence is a genuine
  judgement area.
- **Provision write-backs and liquidated-damages reversals flattering the margin** — a recurring feature
  in this sector's reported profits, and it must be stripped before extrapolating.
- Liquidated damages *payable* by the company for its own delays not provided.
- Customer advances treated as operating cash flow generation rather than as customer funding; a falling
  advance balance masking a deteriorating cash cycle.
- Inventory and WIP building on a programme whose delivery schedule has slipped, without a
  provision for slow-moving or programme-specific stock that has no alternative buyer.
- Treasury/interest income on the advance float presented inside operating performance.
- Indigenous content percentage computed on a favourable basis, or the definition changed to meet a
  policy threshold; bought-out content share rising while margin guidance is held.
- Offset obligations outstanding and their penalty exposure undisclosed.
- Cost overruns on fixed-price development contracts absorbed without provision; development cost
  capitalised where the programme has not been ordered.
- Related-party arrangements with a foreign technology partner (royalty, licence fee) rising ahead of
  revenue; JV structures where the foreign partner controls the IP.
- Subsidiary or JV losses on new-vertical bets parked outside the reported segment.
- Government-shareholder actions — dividend or buyback demands, and OFS overhangs — treated as
  irrelevant to the equity story when they set the float and the capital policy.

## Dependencies to map
**The defence budget and, specifically, the capital-acquisition line** (not the total budget, most of
which is revenue/pension expenditure) and its year-on-year growth · the **award calendar and process
gates** — AoN, RFP, trials, L1, CCS approval — which are trackable public milestones · positive
indigenisation lists (the successive tranches barring imports of named items), Buy Indian-IDDM
categorisation under the Defence Acquisition Procedure, offset policy, and the strategic-partnership
model · DRDO's programme pipeline and technology-transfer terms · **geopolitical events**, which are the
sector's demand catalyst and its schedule risk simultaneously — BEL's own Q1FY26 disclosure notes
~INR 2bn of execution shifting a quarter "due to geopolitical issues" · export policy, end-user
agreements and the government's defence-export target · the tier-2/tier-3 vendor ecosystem's capacity,
which is the binding execution constraint · MSME and private-sector participation policy, which is both
competition and supply · import-content duty exemptions and their conditions · FDI limits in defence ·
government payment behaviour and its fiscal-year-end seasonality · foreign OEM partnerships and
technology-control regimes (ITAR and equivalents) · PSU disinvestment and OFS plans for the
government-owned names.

## Common archetypes here
`regulatory-tailwind` — the dominant and genuinely well-evidenced archetype, since indigenisation policy
directly creates the order book, but the tailwind's *pace* is the uncertainty and lists have
implementation timelines · `capex-to-cashflow` (capacity and vendor-base build-out against the order
book) · `margin-expansion` (indigenous-content mix — the defensible version, because BEL's own margin
risk statement identifies the mechanism) · `market-share-gainer` where private players take share from
the PSUs, or vice versa · `re-rating`, which deserves unusual prominence and the highest skepticism
weight here: **Indian defence multiples have already re-rated substantially on the policy narrative, so
for most names a large share of implied return is the multiple, and `prompts/33`'s 40% rule should be
applied explicitly rather than treated as a formality.** `quality-compounder` is arguable on the
strength of RoIC and demand visibility, but the claim must engage with single-customer concentration and
the execution constraint rather than ignore them. Be alert to `cyclical-peak` in the *multiple* even
where the earnings cycle is early.
