# EPS-Bridge Doctrine

GENERALIZED logic. This document encodes the user's buy-side EPS-bridge
reasoning verbatim-faithfully, structured for reuse by the fund's `buy_side`
agent and the deterministic checker (`research/equity_researcher/tools/
eps_bridge_check.py`). It is sector-agnostic by design — a sector may
override or add checks via `knowledge/references/sectors/<sector>.md`
("special cases"); this file states the general rule, the sector file states
the deviation. All numeric thresholds referenced here live in
`registry/rules/eps_bridge.yaml` and are DRAFT until the user back-tests them
(per repo `CLAUDE.md` hard rule — never treat a DRAFT threshold as approved).

Companion methodology: `buyside_depth.md` (the four required bridges — cost,
revenue-driver, transcript-to-numbers, management tone). This document is the
EPS-specific decomposition that sits inside that same discipline: buyside_depth
tells you *how* to verify a bridge holds together; eps_bridge tells you *which*
EPS-specific ladder rungs a rerating thesis must clear.

## i. Price = EPS x PE frame

`Price = EPS x PE`. A stock re-rates (PE expands) when EPS growth is
**consistent** and **>20%** while the starting PE is **low** relative to that
growth (i.e. the market has not yet priced the growth in). This is the
rerating condition: consistent >20% EPS growth + low starting PE -> PE
rerating is the expected outcome, not a hoped-for one. The corollary: EPS
growth that is not consistent (lumpy, one-off-driven, or decelerating) does
not earn a rerating even if any single year clears 20% — consistency is the
gate, not a single strong print.

Qualitative co-requirement: good-quality management. A numerically clean EPS
bridge from a management team that does not clear the management gate (section
v below) is not sufficient on its own — both must hold.

## ii. EPS decomposition ladder

The ladder walks from revenue visibility down to EPS, each rung independently
checkable against disclosure (this mirrors buyside_depth's revenue-driver
bridge, EPS-specific):

### Revenue: needs increment WITH visibility

Revenue growth alone is not the check — revenue growth **with a disclosed,
forward-looking reason to believe it continues** is. Visibility sources
(any one or more, disclosed and checkable):

- higher demand (order book, footfall, same-store growth, industry demand
  data)
- new capacity coming live (capex-to-commissioning timeline disclosed and
  on-track)
- price increases (disclosed, realized — not merely announced)
- new contracts / order-book additions (traceable to backlog disclosure)
- steady growth track record (multi-year consistency, not a single beat)
- geographic expansion (new markets entered, disclosed ramp)
- product expansion (new SKUs/lines, disclosed contribution)

A revenue number with no attached visibility source is lower-quality growth
even if the absolute number is strong — flag it as such, don't take it at
face value.

### Costs: need reduction, or growth slower than revenue's

Cost discipline shows up as one or more of:

- raw-material cost reduction (input price deflation, sourcing efficiency)
- economies of scale (fixed-cost absorption improving with volume)
- higher utilization (capacity running hotter, unit cost falling)
- automation (labor/conversion cost per unit falling structurally)

The test is **relative to revenue growth**: costs growing slower than revenue
is sufficient even without an absolute reduction — margin expansion is a
revenue-cost relationship, not a cost-level in isolation.

### Gross margin: rising via combination or mix shift

Gross margin rises through the revenue+cost combination above, OR through a
shift in product mix toward higher-margin products or new (typically
higher-margin) products entering the mix. Both routes are legitimate;
distinguish which one is driving the number (mix-shift margin gains are more
durable if the new/higher-margin products have their own demand visibility
per the revenue rung above; pure cost-driven margin gains are more exposed to
input-cost reversal — this classification is the same
structural-vs-cyclical judgment buyside_depth's bridge #2 requires).

### Indirect / marginal costs: reduced marginal burden

Below gross margin, indirect costs should show **reduced marginal costs** as
revenue scales — less marginal labor added per unit of incremental revenue,
scale benefits flowing through SG&A/overhead as a declining percentage of
revenue. This is the operating-leverage check: EBITDA should grow faster than
revenue when this rung holds.

### D&A: non-cash — adjust EPS-impacting changes explicitly

Depreciation & amortization is non-cash. A change in D&A (new capacity
depreciating, an intangible amortization schedule, an accelerated write-off)
mechanically moves EPS without moving cash economics. Any EPS growth (or
EPS-growth shortfall) driven by a D&A change must be called out and
adjusted for explicitly — do not let a D&A swing pass silently as if it were
an operating-performance signal.

## iii. Funding rules — interest and dilution discipline

Growth funded by new capital (debt or equity) must clear a **net-positive**
test on EPS — the funding cost must be smaller than the growth it buys.

### Debt-funded expansion

If revenue/capacity growth is funded via new debt:

- the **interest-coverage impact** of the new debt must be smaller than the
  growth it funds — i.e., post-debt interest coverage must not deteriorate
  by more than the growth justifies. Concretely: the incremental interest
  cost from the new debt, combined with the tax shield it generates, must
  have a **net positive impact on EPS** — the coverage-impact percentage
  must be **less than** the revenue-growth percentage the debt is funding.
- in absolute terms: **absolute interest cost increase < absolute EBIT
  growth increment**. If the new debt's interest bill grows faster in
  absolute rupees than EBIT grows in absolute rupees, the debt is destroying
  EPS quality even if revenue is growing.

### Equity-funded expansion

If growth is funded via new equity (QIP, preferential allotment, warrants,
ESOP-driven dilution at scale):

- **EPS dilution must be smaller than the EBIT growth it funds** — net
  positive impact on EPS, same principle as the debt case.
- **dilution once or twice is acceptable**; dilution in **consecutive**
  years/rounds is a flag — repeated, back-to-back dilution is a funding-
  discipline failure, not a one-off capital-raise for a specific project.
  The consecutive-ness is what converts an acceptable event into a red flag,
  not the act of diluting itself.

## iv. Working-capital rules

### Receivables as % of revenue — trend, checked per year

Track trade receivables as a percentage of revenue **year by year**, not just
start-to-end. A rising trend (receivables growing faster than revenue,
i.e. DSO expanding) is a working-capital-quality flag regardless of whether
the absolute revenue/EPS numbers look good — rising receivables intensity
can mask a revenue-recognition or channel-stuffing problem, or simply
deteriorating collection discipline.

### Short-term-loan-funded working capital

If the working capital of expanded capacity (higher receivables/inventory
that comes with higher revenue) is funded via short-term loans, the
**revenue growth must exceed the short-term interest expense** it triggers —
same net-positive-impact principle as the long-term debt rule above, applied
to the working-capital layer.

### Operating cash flow must stay positive through expansion

CFO must remain positive through an expansion phase. Debt draws, equity
dilution, and short-term-loan interest are **special/financing items**, not
substitutes for operating cash generation — they fund the expansion, they do
not replace the requirement that the underlying business still throws off
positive operating cash while it expands. A negative-CFO expansion phase,
even if fully explained by capex timing, is a materially different risk
profile from a positive-CFO one and must be flagged as such.

### Asset-heavy industries: refinancing check

For asset-heavy businesses (manufacturing, infrastructure, capital-intensive
sectors), separately check whether the company is refinancing existing debt
to reduce interest cost — refinancing into lower-cost/longer-tenor debt is a
positive EPS-bridge input in its own right (interest-cost step-down is not
noise, it is an intentional funding-quality lever) and should be attributed
if it is happening.

## v. Qualitative gate — management intent + delivery

Numbers alone are not sufficient. Corroborate the EPS bridge against what
management is actually saying and actually delivering:

- **Management must be actively discussing these exact strategies** — market
  positioning, beating competition, share capture, portfolio expansion — in
  earnings calls and MD&A, not just reporting the numbers after the fact. A
  bridge that holds numerically but has no corroborating management
  narrative is a weaker, more coincidental-looking bridge.
- **Delivery-vs-promise track record**: does the same management team have a
  history of doing what it said it would do, on the timeline it said (see
  buyside_depth's management tone + delivery-vs-promise bridge for the
  longitudinal tracking mechanism — this gate consumes that same
  measurement, applied specifically to the EPS-bridge claims).

## vi. Funding-quality hierarchy

In order of preference, from best to acceptable:

1. **Internally funded (operating cashflows)** — expansion funded from the
   business's own cash generation. This is the marker of good management:
   growth that does not need external capital to happen.
2. **Sensible debt + internal cashflows combined** — still good, provided
   the debt clears the interest-vs-EBIT-growth test in section iii and the
   business is not relying on debt alone.

Funding that fails both — undisciplined debt (interest growth outpacing EBIT
growth) or repeated/consecutive dilution — is a funding-quality flag
regardless of how good the top-line growth story looks.

## Sector overrides

This methodology is deliberately GENERALIZED / sector-agnostic in its
structure (the six-rung ladder, the funding rules, the working-capital
rules, the management gate). The specific inputs and any sector-specific
special cases (e.g. BFSI's NII/advances structure has no "gross margin" line
in the conventional sense; capital-intensive sectors weight the refinancing
check more heavily; asset-light services businesses may never trip the
debt-funding rules at all) are documented per sector in
`knowledge/references/sectors/<sector>.md` and, where they change a
threshold rather than just add narrative, in `registry/rules/eps_bridge.yaml`'s
`sector_overrides:` block. Absent an explicit sector override, the general
rule in this document applies.
