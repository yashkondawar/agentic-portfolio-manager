# Buy-Side Depth Methodology

Author: this document is authored for the fund (not sourced from the
cycle-positioning strategy document or any external file) — it captures
the analytical depth a buy-side fundamental analyst is expected to reach
before a name is allowed past the Idea Generation stage, distinct from
(and complementary to) the cycle-positioning engine's top-down/relative-
value read.

## Why this exists

The cycle-positioning framework (`cycle_positioning_framework.md`) and the
4-gate funnel (`funnel_4gate.md`) tell you *when* a sector/security is
statistically and behaviorally attractive. They do not, by themselves,
verify that a specific company's numbers actually hang together — that a
reported quarter is real, sustainable, and consistent with what
management said would happen. That verification is buy-side depth: the
discipline of tracing a business's physical/operational reality through
to its reported financials, and catching the gap between what management
promises and what management delivers before the market does.

An idea that passes the cycle engine's Quality Screen (Gate 2) on
trailing ratios alone, but that has never been checked against this
methodology, has not actually been researched at buy-side depth — it has
only been screened.

## The four required bridges

### 1. Cost bridge

Walk the cost structure from its physical/operational drivers to the P&L
line, not the other way around. For a manufacturer: raw-material tonnage
x realized input price + conversion cost per unit + fixed overhead
absorption at the reported utilization rate should reconcile to the
reported cost of goods sold within a small, explainable residual. For a
services business: billed headcount x realized rate - subcontracting cost
- delivery overhead should reconcile to reported cost of revenue. A
residual that can't be explained by a disclosed one-off (forex, a
provision, a write-back) is a flag, not a footnote to skip past.

### 2. Revenue-driver bridge (capacity -> revenue -> EBITDA -> margins -> EPS)

The full chain, each link independently checkable against disclosure:

1. **Capacity** (installed capacity, headcount, store count, order book,
   as appropriate to the sector — see `registry/kpis/<sector>.yaml`'s
   `quantitative_kpis` for the sector-specific capacity proxy).
2. **-> Revenue**: capacity x utilization/same-store-growth/billing rate
   should reconcile to reported revenue. A revenue beat with no
   corresponding capacity or utilization change is either a pricing/mix
   story (verify it's disclosed as such) or unexplained (flag).
3. **-> EBITDA**: revenue growth flowing through at a materially different
   incremental margin than the business's own operating-leverage history
   needs a specific, disclosed cause (cost deflation, one-off, mix
   shift) — "margins just expanded" is not an answer, it's the question.
4. **-> Margins**: is the margin move structural (a genuine step-change in
   the cost curve, pricing power, or mix) or cyclical (input-cost
   tailwind, one-off absorption benefit that reverses)? This
   classification is exactly the value-type vs. cyclical judgment the
   cycle engine needs as an input, not a substitute for it.
5. **-> EPS**: reconcile reported EPS growth to (a) the EBITDA/margin
   chain above, (b) share count changes (buybacks, dilution, ESOPs), and
   (c) below-the-line items (tax rate changes, exceptional items,
   associate/JV income). An EPS beat driven mostly by (b) or (c) rather
   than (a) is lower-quality and should be flagged as such in the
   research packet, not presented at face value.

### 3. Transcript-to-numbers bridge

Every specific, checkable claim made in an earnings call or investor
presentation should be tied to a number in this quarter's or a future
quarter's disclosure:

- A claimed capacity addition should show up in capex and, on the
  promised timeline, in reported capacity/utilization.
- A claimed new-client win or order-book addition should show up in the
  order book / revenue in the disclosed timeframe.
- A claimed cost-reduction program should show up in the cost bridge
  above within the guided timeframe.

Claims with no attached number or no attached timeline are noted as
**unverifiable-as-stated** rather than silently dropped or silently
accepted — this is itself a data point (vague guidance is a qualitative
marker worth carrying into the narrative-intensity read, see
`narrative_intensity_scoring.md`).

### 4. Management tone + delivery-vs-promise bridge

Track, across consecutive quarters, per management team:

- **Delivery-vs-promise ratio**: of the specific, numbered claims made
  last quarter (per bridge 3 above), how many were delivered on the
  guided timeline, delivered late, delivered short, or dropped without
  explanation? This is trackable longitudinally per company and is a
  genuine, computable measure of management credibility — not a
  qualitative impression.
- **Tone drift**: is the specificity and confidence of guidance language
  increasing or decreasing quarter over quarter, independent of whether
  results are good or bad? A management team that shifts from specific
  numbered guidance to vaguer language while results are still reported
  as good is an early flag worth carrying into the Gate 4 (Neglect /
  Contrarian Confirmation) screen.
- **Consistency under stress**: does the explanation for a miss change
  between the quarter it happens and the following quarter's retelling of
  it? A moving explanation for the same miss is a stronger flag than the
  miss itself.

## Where this plugs in

- This is fundamentally an **Equity Research** function (see
  `equity_research_placeholder` — the dedicated agent for this is not yet
  built; until it is, `research_head` and the sector-specific `registry/
  kpis/<sector>.yaml` qualitative_checks carry a lighter-weight version of
  this work).
- The delivery-vs-promise ratio and tone-drift tracking are natural
  `knowledge_base` (DB table) entries — timestamped, per-instrument,
  `SITUATION`-tagged notes accumulated one earnings call at a time, not a
  one-shot calculation.
- A name that has NOT been walked through these four bridges should not
  be presented to Critique or Risk Management as passing Gate 2 (Quality
  Screen) on ratios alone — ratios are the output of a bridge that must
  have been checked, not a substitute for checking it.
- This methodology is deliberately sector-agnostic in its structure (cost
  bridge, revenue-driver bridge, transcript bridge, tone bridge) — the
  *inputs* to each bridge are sector-specific and come from
  `registry/kpis/<sector>.yaml` and `knowledge/references/sectors/<sector>.md`.
