# Sector Playbook — Internet platforms, marketplaces & SaaS

*Tier 2. Family: `it_technology` (`prompts/sector_packs/it_technology.md`). Shared rules:
`prompts/31`.*
**Provenance:** corpus-grounded — Meesho (JM Financial, Jan-26 and Choice Broking, Dec-25 — the
corpus's most complete marketplace build, including the GMV→NMV funnel and cohort-retention
exhibits), Urban Company (JM Financial, Feb-26 — services marketplace, margins on NTV), IndiaMART
(Axis Capital, Mar-22), Info Edge (BOB Capital, Mar-20 and Apr-19), ixigo / Le Travenues (JM
Financial, Jan-25), Pine Labs (Emkay Global, Nov-25), Affle (ICICI Securities, Sep-25 and JM
Financial, Mar-23), Zaggle (Equirus, Apr-24).
*SaaS and software-product businesses route here per the family pack; their recurring-revenue
metrics are called out separately below.*

## The economic engine
A platform does not own the inventory or perform the service — **it takes a cut of a transaction it
enables.** So the P&L that matters is not the statutory one; it is a funnel, and the sector has its
own vocabulary for each stage. Getting the vocabulary right *is* the analysis:

```
GMV        gross value transacted on the platform          (not revenue — the platform never owns it)
  ↓ minus returns, cancellations, discounts
NMV / NTV  net merchandise / transaction value             (the honest volume base)
  ↓ × take rate
Net revenue                                                (what the platform actually books)
  ↓ minus variable cost to serve (logistics, payment, support, seller/partner incentives)
Contribution margin                                        (the unit economics)
  ↓ minus marketing (customer acquisition) and fixed cost
Adjusted EBITDA → EBITDA
```

**Two conventions from the corpus that must be carried, not paraphrased:**

- **GMV is not revenue and NMV is not GMV.** Meesho's marketplace GMV runs INR 344.9bn (FY23) →
  1,064.0bn (FY28E) while NMV runs 192.3bn → 616.6bn — the gap is returns, cancellations and
  discounts, and it is roughly 40%. A note quoting GMV growth as "revenue growth" has overstated the
  business by that factor.
- **Margins are expressed as a % of NMV/NTV, not of net revenue.** Both Meesho and Urban Company are
  modelled this way (Urban Company: adjusted EBITDA margin as % of NTV reaching 9.9% by FY30 in one
  segment and 7.1% in another). **State the denominator every time.** A margin on net revenue and a
  margin on NMV differ by the take rate — often 5-10x — and the two are silently interchanged in
  market commentary.

**Growth must be decomposed into the funnel's own drivers.** Meesho's 24% GMV CAGR (FY25-30E) is
built as 30% order CAGR = 17% transacting-user CAGR + 12% order-frequency CAGR — *while average
order value is deliberately being reduced* to improve affordability. That is a complete, checkable
growth statement, and it is the standard to hold a note to: **users × frequency × AOV, with the
direction of each stated.**

## Analysis sequence
1. **Draw the funnel with numbers** — GMV, NMV/NTV, net revenue, contribution, adjusted EBITDA — for
   every disclosed year, and compute the conversion at each step. The GMV-to-NMV conversion and its
   trend is the first quality signal (a widening gap means returns or discounting are rising).
2. **Decompose volume growth into users × frequency × AOV**, each as its own series, and say which
   one the thesis rests on. A thesis resting on frequency is stronger than one resting on user adds,
   because user adds cost marketing money and frequency does not.
3. **Cohort analysis — the single most important and most-skipped step.** Retention and spend by
   *acquisition cohort*, for both sides of the marketplace. Meesho's note carries NMV retention per
   *user* cohort **and** per *seller* cohort plus orders-per-seller-cohort; Urban Company carries
   category-adoption cohorts and repeat-user NTV contribution. **A platform whose older cohorts spend
   more each year is compounding; one that replaces churn with new acquisition is renting growth**,
   and only cohort curves distinguish them. If cohorts are not disclosed, that is a material gap and
   must be reported as one.
4. **Take rate, by category and over time**, with the direction and the reason. A rising take rate on
   flat volume means monetisation pressure on the supply side and invites disintermediation; a
   falling take rate may be a deliberate share purchase. Both need saying.
5. **Contribution margin, and its bridge** — logistics/fulfilment cost per order, payment cost,
   customer-support cost, seller and buyer incentives. **Incentives and discounts are the line that
   distinguishes a business from a subsidy**: get them as a % of GMV and watch whether growth
   survives their reduction.
6. **Customer acquisition cost and payback** — CAC, blended vs paid, and the LTV/CAC ratio computed
   on *contribution* margin (not gross revenue) and on a stated horizon. Then marketing as % of GMV.
7. **Competitive structure and the platform's actual position** — Meesho at 7-8% of Indian e-commerce
   GMV with 234mn annual transacting users is a scale-and-share statement that frames everything;
   quick-commerce entry, category overlap and the incumbents' cross-subsidy capacity are the threats.
8. **The path to profitability, dated.** Which segment is contribution-positive, which is
   adjusted-EBITDA-positive, and when the loss-making ones cross over. Urban Company's disclosure — one
   segment profitable at contribution and adjusted-EBITDA level as of 3QFY26, another still
   loss-making — is the granularity to demand.
9. **Then the multiple, and the transition rule** (below).

## Signature KPIs
| KPI | Formula | Unit | How to read it | Source |
|---|---|---|---|---|
| **GMV** | gross value of transactions on the platform | INR cr | **Not revenue.** Always report NMV/NTV beside it and the conversion between them (Meesho's gap is ~40%). Decompose growth into users × frequency × AOV | Company disclosure, DRHP |
| **Take rate** | net revenue / GMV (or / NMV — state which) | % | The monetisation lever and the disintermediation risk. Report by category; a blended take rate hides a mix shift. State the denominator | Computed |
| **Contribution margin** | (net revenue − variable cost to serve) / NMV or net revenue | % | The unit economics, and the only margin that proves the model works before scale. **State the denominator**, and show incentives/discounts as a separate line | Company disclosure, derived |
| **MTU** (monthly transacting users) | unique users transacting in the month | mn | The demand base. Note the variants — MTU, MAU, and *annual* transacting users (Meesho: 234mn ATU) are different denominators; do not compare across them. Pair with frequency, or user growth flatters | Decks, DRHP |
| **Adjusted EBITDA margin** | adjusted EBITDA / NMV or NTV | % | **Get the adjustment list in full.** ESOP is the usual exclusion and it is a real cost in this sector. State the denominator: Urban Company's 9.9%/7.1% by FY30 are % of NTV, not of revenue | Company disclosure |

## Supporting KPIs
NMV/NTV and the GMV-conversion ratio; orders and order frequency per user; average order value;
transacting sellers/partners and NMV per seller cohort; seller retention and orders per seller
cohort; user retention by cohort and repeat-user share of NMV; new vs repeat mix; category mix and
take rate by category; fulfilment/logistics cost per order; payment-processing cost; customer-support
cost per order; buyer and seller incentives as % of GMV; marketing as % of GMV; CAC and LTV/CAC on
contribution; ESOP cost as % of revenue and as % of NMV; headcount and revenue per employee;
cash burn and months of runway; working capital (float, if payments are involved).
*SaaS/software-product:* ARR and its growth; net revenue retention (NRR) and gross retention;
logo churn; ACV and average deal size; CAC payback in months; Rule of 40 (growth % + FCF margin %);
magic number; gross margin (hosting-adjusted); customer count by revenue band.
*Fintech platforms (Pine Labs, Zaggle type):* TPV, device/merchant count, revenue per merchant,
attach rate of value-added services, and where lending sits — if the platform takes credit risk,
`nbfc_diversified`'s credit-cost discipline applies to that segment and must be run separately.

## Standard exhibit set
**The funnel, as a single waterfall: GMV → NMV/NTV → net revenue → contribution → adjusted EBITDA**,
with the conversion at each step · GMV and NMV as two lines with the gap shown · growth decomposed
into users × frequency × AOV · **cohort curves: NMV retention per user cohort and per seller cohort**
(the sector's highest-value exhibit and the one most often absent) · repeat-user share of NMV ·
take rate by category and blended, over time · contribution-margin bridge with incentives as a
separate line · incentives and marketing as % of GMV · CAC and LTV/CAC on contribution ·
adjusted-EBITDA margin as % of NMV with the adjustment list stated · segment-level path to
profitability with dates · category and geography mix · market share of the addressable pool
(Meesho: 7-8% of Indian e-commerce GMV) · competitive map including quick-commerce and incumbent
cross-subsidy capacity · ESOP cost trajectory · cash burn and runway · EV/Sales and EV/GMV bands
with the transition point to EV/EBITDA marked.
*SaaS:* ARR waterfall (new/expansion/churn), NRR by cohort, Rule of 40 vs peers, CAC payback.

## Valuation convention
**EV/Sales or EV/GMV while the business is pre-profit, transitioning to EV/EBITDA (or DCF) as it
crosses over — and the note must state which regime it is in and why.** The transition is the
judgment call, and `docs/ER_CORPUS_FINDINGS.md` §4's discipline applies: name the metric, name the
year, and justify the multiple against peers.

**Demand a dated path to profitability.** This is the playbook's hard requirement. A platform valued
on EV/Sales is being priced on a promise; the note must say *when* contribution and adjusted EBITDA
turn, *for each segment*, and what has to be true for that to happen. Urban Company's
segment-by-segment disclosure (one profitable at contribution and adjusted-EBITDA level, another not)
is the granularity that makes such a forecast inspectable rather than rhetorical.

**A DCF is more defensible here than a multiple, and should usually be run**, because the whole value
sits beyond the forecast horizon — Meesho's and Urban Company's notes both model to FY30 for exactly
this reason. If a DCF is used, publish the terminal margin and the terminal growth, and cross-check
the implied exit multiple; a DCF whose implied exit EV/EBITDA is 40x has not escaped the multiple
problem, only hidden it.

*Traps:* (i) **treating GMV as revenue** or NMV as GMV — the sector's defining error, worth ~40% on
Meesho's numbers; (ii) quoting a margin without its denominator (% of revenue vs % of NMV/NTV differ
by the take rate); (iii) accepting "adjusted" EBITDA without reading the adjustment list — excluding
ESOP in a business whose main cost is people flatters materially; (iv) valuing user growth bought
with incentives as franchise growth; (v) LTV/CAC computed on revenue rather than contribution, or on
an unstated horizon; (vi) crediting a take-rate increase without asking what the supply side does in
response; (vii) applying a global platform's multiple to an Indian AOV and take rate;
(viii) valuing a fintech platform's lending book at a platform multiple — that segment is a lender.

## Divergence cases

*Same verified fact, two defensible readings, and the evidence that settles them. The rule
and the closed vocabulary of conditioning variables are in `docs/OPINION_VS_ANALYSIS.md`
§7. `prompts/33_thesis_synthesis.md` seeds `state/interpretation_ledger.json` from these;
`prompts/34_thesis_redteam.md` checks 16-18 audit the result. A reading that names no
conditioner is an unearned adjective (§2 F6).*

**1. It trades at 8x EV/Sales and is pre-profit.**
- *Unanchored* (`terminal_value_share`) — a sales multiple on a loss-making business prices
  a promise.
- *The correct regime, for now* (`terminal_value_share`) — EV/Sales or EV/GMV while
  pre-profit, transitioning to EV/EBITDA or DCF at crossover. The transition is the
  judgment call, and the note must state which regime it is in and why.
- *Discriminator* (`forward_observable`) — a **dated** path to profitability, per segment.
  This is the playbook's hard requirement. Urban Company's segment-by-segment disclosure
  (one segment profitable at contribution and adjusted-EBITDA level, another not) is the
  model for what "dated and segmented" looks like.

**2. Adjusted EBITDA has turned positive.**
- *Profitable* (`earnings_base_quality`).
- *Adjusted of what* (`earnings_base_quality`) — ESOP is the usual exclusion and customer
  acquisition is the dangerous one. Contribution margin before the adjustments is the
  honest cut.
- *Discriminator* (`disclosed_mechanism`) — the adjustment list, published.

**3. GMV grew 45%.**
- *Demand* (`growth_durability`).
- *A subsidy* (`growth_durability`) — GMV bought with discounts is spend, not a market.
- *Discriminator* (`disclosed_mechanism`) — take rate and net revenue growth published
  alongside GMV. If take rate fell while GMV rose, the growth was purchased.

## Forensic screens (sector-specific)
- **GMV, NMV and net revenue used interchangeably**, or the GMV definition changed between periods
  (inclusive/exclusive of taxes, shipping, cancellations).
- The GMV-to-NMV conversion deteriorating — rising returns or discounting, masked by GMV growth.
- Take rate rising while seller counts or seller-cohort retention fall: monetisation is being
  extracted from a shrinking supply base.
- **Cohort data absent, or the cohort definition changed, or only the best cohort shown.** Older
  cohorts quietly dropped from the chart is a serious flag.
- User metrics switched between MTU, MAU, ATU and "registered users" across periods, or a
  90-day-active definition introduced in a weak quarter.
- Incentives and discounts moved between "revenue deduction", "marketing" and "other expenses" —
  each presentation gives a different take rate and contribution margin on identical economics.
- Marketing cost capitalised, or CAC computed on blended (including organic) users to look lower.
- ESOP excluded from adjusted EBITDA while ESOP grants accelerate; adjustment list expanding
  year on year.
- Related-party transactions with promoter or group entities appearing in GMV — GMV is the easiest
  metric in this playbook to inflate, because no cash margin need touch the platform.
- Revenue recognised gross (principal) where the platform is an agent, or vice versa — check the
  Ind AS 115 principal-vs-agent judgement and whether it changed.
- Segment reporting that nets a loss-making vertical into a profitable one; "other" growing faster
  than named segments.
- Cash burn funded by float (customer or seller money in transit) presented as operating cash flow.
- For fintech: lending losses sitting in a subsidiary outside the platform's reported segment;
  first-loss-default-guarantee arrangements not disclosed.

## Dependencies to map
Internet and smartphone penetration, and online-adoption rates in lower-tier cities (Meesho's growth
thesis rests on exactly this) · UPI and digital-payment rails, and any change to MDR/interchange
economics · **quick-commerce expansion, which is now the principal competitive threat to horizontal
e-commerce** and is simultaneously a channel for some models · the incumbents' willingness to
cross-subsidise (Amazon, Flipkart, Reliance) · logistics cost and 3PL capacity; own-network vs
outsourced economics · GST on e-commerce, TCS/TDS provisions, and the equalisation levy where
relevant · the DPDP Act and data-localisation rules · **the Digital Competition Bill / ex-ante
competition regulation and CCI actions**, which are live and could constrain self-preferencing,
deep discounting and platform-neutrality economics · ONDC as a structural take-rate threat ·
FDI policy on inventory-led vs marketplace models (the rule that shapes every Indian e-commerce
corporate structure) · RBI regulation where payments or lending are involved (link to
`nbfc_diversified` for the credit leg) · app-store and ad-platform costs (Google/Meta), which are
the real CAC inputs · AI's effect on both content/search discovery and on customer-support cost.

## Common archetypes here
`capex-to-cashflow` in its platform form — burn converting to profit, the dominant archetype and
the one requiring a dated crossover · `margin-expansion` (contribution and operating leverage on a
fixed cost base — legitimate when the cohort curves support it) · `market-share-gainer` (verify
against the addressable pool, not against the company's own past) · `regulatory-tailwind` or its
inverse, which in this sector can be existential rather than marginal · `quality-compounder` for
platforms with genuine network effects — **the claim requires improving older-cohort economics, and
cohort curves are the only acceptable evidence** · and `re-rating`, which carries the highest
skepticism weight here because pre-profit valuation is *already* a multiple argument: when the
metric is EV/Sales, essentially all of the return is the multiple, and `prompts/33`'s 40% rule
should be read as near-automatically triggered.
