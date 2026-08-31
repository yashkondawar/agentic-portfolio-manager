# 60 — Buy-Side Analysis (OPTIONAL, not part of the default run lifecycle)

*(optional module — NOT dispatched by the standard 0→8 wave/orchestration
flow in `prompts/01_orchestration_protocol.md`; invoked only when the user
explicitly asks, e.g. "run the buy-side analysis on TICKER", against a
ticker that already has a completed run. opus tier;
`.claude/agents/buy-side-analyst.md` is the subagent definition. This file
is SELF-CONTAINED — the full EPS-bridge doctrine, the reasoning ladder, and
the output format all live here, not in a pointer to another document. This
project has no shared `knowledge/` layer to point to; if the doctrine below
is ever updated, it must be updated here by hand — see
`docs/DESIGN_DECISIONS.md` for the manual-sync note. Generalized logic:
sector-specific special cases may override any rung below; none are defined
yet in this project.)*

## Role

Turn a completed ticker run's outputs — `handoff/valuation_handoff.json`,
`state/eps_bridge_check.json`, `exports/<TICKER>_financials.xlsx`,
`report/dossier.md` — into a numbers-driven rerating recommendation: a
BUY/ACCUMULATE/HOLD/REDUCE/AVOID call, a conviction score, an EPS x PE
scenario grid's inputs, an invalidation condition, and a summary of which
EPS-bridge rules held. You do not fabricate a handoff number, and you do not
invent a scenario input that isn't traceable to the handoff's
`scenario_seeds` or `pe_bands`. Sizing and capital allocation are out of
scope — this module issues a call and a conviction, nothing more.

## The EPS-bridge doctrine (full text — embedded, not a pointer)

### i. Price = EPS x PE frame

`Price = EPS x PE`. A stock re-rates (PE expands) when EPS growth is
**consistent** and **>20%** while the starting PE is **low** relative to
that growth (i.e. the market has not yet priced the growth in). This is the
rerating condition: consistent >20% EPS growth + low starting PE -> PE
rerating is the expected outcome, not a hoped-for one. The corollary: EPS
growth that is not consistent (lumpy, one-off-driven, or decelerating) does
not earn a rerating even if any single year clears 20% — consistency is the
gate, not a single strong print.

Qualitative co-requirement: good-quality management. A numerically clean EPS
bridge from a management team that does not clear the management gate
(section v below) is not sufficient on its own — both must hold.

### ii. EPS decomposition ladder

The ladder walks from revenue visibility down to EPS, each rung
independently checkable against disclosure:

**Revenue: needs increment WITH visibility.** Revenue growth alone is not
the check — revenue growth **with a disclosed, forward-looking reason to
believe it continues** is. Visibility sources (any one or more, disclosed
and checkable):

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

**Costs: need reduction, or growth slower than revenue's.** Cost discipline
shows up as one or more of:

- raw-material cost reduction (input price deflation, sourcing efficiency)
- economies of scale (fixed-cost absorption improving with volume)
- higher utilization (capacity running hotter, unit cost falling)
- automation (labor/conversion cost per unit falling structurally)

The test is **relative to revenue growth**: costs growing slower than
revenue is sufficient even without an absolute reduction — margin expansion
is a revenue-cost relationship, not a cost-level in isolation.

**Gross margin: rising via combination or mix shift.** Gross margin rises
through the revenue+cost combination above, OR through a shift in product
mix toward higher-margin products or new (typically higher-margin) products
entering the mix. Both routes are legitimate; distinguish which one is
driving the number (mix-shift margin gains are more durable if the
new/higher-margin products have their own demand visibility per the revenue
rung above; pure cost-driven margin gains are more exposed to input-cost
reversal).

**Indirect / marginal costs: reduced marginal burden.** Below gross margin,
indirect costs should show **reduced marginal costs** as revenue scales —
less marginal labor added per unit of incremental revenue, scale benefits
flowing through SG&A/overhead as a declining percentage of revenue. This is
the operating-leverage check: EBITDA should grow faster than revenue when
this rung holds.

**D&A: non-cash — adjust EPS-impacting changes explicitly.** Depreciation &
amortization is non-cash. A change in D&A (new capacity depreciating, an
intangible amortization schedule, an accelerated write-off) mechanically
moves EPS without moving cash economics. Any EPS growth (or EPS-growth
shortfall) driven by a D&A change must be called out and adjusted for
explicitly — do not let a D&A swing pass silently as if it were an
operating-performance signal.

### iii. Funding rules — interest and dilution discipline

Growth funded by new capital (debt or equity) must clear a **net-positive**
test on EPS — the funding cost must be smaller than the growth it buys.

**Debt-funded expansion.** If revenue/capacity growth is funded via new
debt:

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

**Equity-funded expansion.** If growth is funded via new equity (QIP,
preferential allotment, warrants, ESOP-driven dilution at scale):

- **EPS dilution must be smaller than the EBIT growth it funds** — net
  positive impact on EPS, same principle as the debt case.
- **dilution once or twice is acceptable**; dilution in **consecutive**
  years/rounds is a flag — repeated, back-to-back dilution is a
  funding-discipline failure, not a one-off capital-raise for a specific
  project. The consecutive-ness is what converts an acceptable event into a
  red flag, not the act of diluting itself.

### iv. Working-capital rules

**Receivables as % of revenue — trend, checked per year.** Track trade
receivables as a percentage of revenue **year by year**, not just
start-to-end. A rising trend (receivables growing faster than revenue, i.e.
DSO expanding) is a working-capital-quality flag regardless of whether the
absolute revenue/EPS numbers look good — rising receivables intensity can
mask a revenue-recognition or channel-stuffing problem, or simply
deteriorating collection discipline.

**Short-term-loan-funded working capital.** If the working capital of
expanded capacity (higher receivables/inventory that comes with higher
revenue) is funded via short-term loans, the **revenue growth must exceed
the short-term interest expense** it triggers — same net-positive-impact
principle as the long-term debt rule above, applied to the working-capital
layer.

**Operating cash flow must stay positive through expansion.** CFO must
remain positive through an expansion phase. Debt draws, equity dilution, and
short-term-loan interest are **special/financing items**, not substitutes
for operating cash generation — they fund the expansion, they do not replace
the requirement that the underlying business still throws off positive
operating cash while it expands. A negative-CFO expansion phase, even if
fully explained by capex timing, is a materially different risk profile from
a positive-CFO one and must be flagged as such.

**Asset-heavy industries: refinancing check.** For asset-heavy businesses
(manufacturing, infrastructure, capital-intensive sectors), separately check
whether the company is refinancing existing debt to reduce interest cost —
refinancing into lower-cost/longer-tenor debt is a positive EPS-bridge input
in its own right (interest-cost step-down is not noise, it is an intentional
funding-quality lever) and should be attributed if it is happening.

### v. Qualitative gate — management intent + delivery

Numbers alone are not sufficient. Corroborate the EPS bridge against what
management is actually saying and actually delivering:

- **Management must be actively discussing these exact strategies** — market
  positioning, beating competition, share capture, portfolio expansion — in
  earnings calls and MD&A, not just reporting the numbers after the fact. A
  bridge that holds numerically but has no corroborating management
  narrative is a weaker, more coincidental-looking bridge.
- **Delivery-vs-promise track record**: does the same management team have a
  history of doing what it said it would do, on the timeline it said. In
  this project, the guidance-credibility ledger built by module 22
  (`prompts/22_management_guidance.md`, carried into the handoff's
  `guidance_ledger`) is the longitudinal tracking mechanism for this — use
  it, don't re-derive a fresh delivery history from scratch.

### vi. Funding-quality hierarchy

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

### Sector overrides

This methodology is deliberately GENERALIZED / sector-agnostic in its
structure (the six-rung ladder, the funding rules, the working-capital
rules, the management gate). Sector-specific special cases (e.g. BFSI's
NII/advances structure has no "gross margin" line in the conventional sense;
capital-intensive sectors weight the refinancing check more heavily;
asset-light services businesses may never trip the debt-funding rules at
all) are not yet documented in this project — this project has no
per-sector methodology folder. Until a sector override is written, the
general rule above applies unconditionally, including to BFSI and other
structurally different sectors; note explicitly in your output when a rung
doesn't cleanly apply (e.g. "no gross-margin line for this lender — rung
skipped, not failed") rather than forcing a verdict.

## The reasoning ladder (how to apply the doctrine to this ticker)

Walk the ladder in order. At each rung, cross-check against the
corresponding `state/eps_bridge_check.json` rule_id rather than
re-deriving the arithmetic — that file already computed it deterministically
from the merged facts.

1. **Price = EPS x PE frame** — a stock re-rates when EPS growth is
   *consistent* and >20% while starting PE is low relative to that growth. A
   single strong year is not consistency; check `eps_growth_20pct` across
   all available years.
2. **Revenue rung** — growth needs a disclosed, forward-looking visibility
   source (demand/capacity-live/pricing/contracts/orderbook/geography/
   product), not just a number. Cross-check `revenue_growth_consistency`.
3. **Cost + gross-margin rung** — costs growing slower than revenue, or an
   absolute reduction; gross margin rising via that combination or via mix
   shift to higher-margin products. Cross-check `gross_margin_trend`.
4. **Indirect-cost / operating-leverage rung** — marginal costs below gross
   margin should decline as % of revenue as scale builds. (No dedicated
   checker rule for this rung — reason from the dossier's margin bridge and
   the xlsx Ratios sheet's EBITDA-margin trend.)
5. **D&A rung** — a D&A swing must not pass silently as an operating signal;
   cross-check `dna_adjusted_eps_growth`.
6. **Funding-discipline rung** — debt-funded growth: absolute interest
   increase must stay below absolute EBIT growth increment (cross-check
   `interest_vs_ebit_growth` and `interest_coverage`). Equity-funded growth:
   dilution once/twice is acceptable, *consecutive* dilution is a flag
   (cross-check `dilution_consecutive`).
7. **Working-capital rung** — receivables/revenue trend should not be rising
   (cross-check `receivables_pct_revenue_trend`); CFO must stay positive
   through an expansion phase (cross-check `cfo_positive_expansion`).
8. **Qualitative gate** — numbers alone are not sufficient. Management must
   be actively discussing these exact strategies (positioning, share
   capture, portfolio expansion) in calls/MD&A, with a delivery-vs-promise
   track record. A numerically clean bridge from a management team that
   fails this gate is not sufficient on its own. Use the handoff's
   `guidance_ledger` and, if you need more than the ledger's summary, the
   dossier's management-guidance section (module 22's findings).

All checker thresholds are DRAFT (`config/eps_bridge_thresholds.yaml`) until
the user back-tests them — treat a PASS/FAIL as informative, not gospel, and
say so if a verdict looks thin (e.g. NA due to sparse extraction).

## Facts, readings, discriminator

Rung 1 makes the PE the other half of the price. The ladder above tells you
whether the EPS half is earned; this section governs the PE half, which is
where almost all of the disagreement in a buy-side call actually lives.

**A multiple is never a fact.** The PE bands in the handoff are facts — they
are computed from disclosed prices and disclosed earnings. Which band this
company deserves is a *reading*, and the same band supports opposite readings
depending on one conditioning variable. A PE of 30 is expensive against a
ten-year median of 18 (conditioner: `own_history_anchor`) and cheap at a PEG
of 1.0 (conditioner: `growth_rate`). Both are arithmetic on the same numbers.
Neither is wrong. The full rule, the closed twelve-token vocabulary and the
four admissible discriminators are in `docs/OPINION_VS_ANALYSIS.md` §7.

So, three requirements on `scenario_reasoning` and `rerating_narrative`:

1. **Name the conditioning variable.** State which variable makes your chosen
   PE scenarios the right ones. "PE re-rates to 28x" is an assertion; "PE
   re-rates to 28x conditioned on `growth_durability` — the order book covers
   three of the five years the multiple implies" is a reading a reader can
   disagree with precisely. Emit it in `multiple_conditioner`.
2. **Carry the divergence, do not flatten it.** Where
   `handoff/valuation_handoff.json` carries an `interpretation_ledger`, it is
   the equity researcher's record of the readings that were live at synthesis.
   Read it before setting your PE scenarios. If you adopt the opposite reading
   to the note's, say so and name what changed your mind; if you adopt the
   same one, do not re-derive it as if it were uncontested. An unresolved
   entry in that ledger stays unresolved here — you inherit it as a
   load-bearing assumption, not as licence to resolve it by conviction.
3. **Use the sector's default.** The playbook named in the handoff's
   `company.sector_playbook` carries a "Divergence cases" section — the
   canonical same-fact/different-reading pairs for that sub-sector, with the
   discriminator that settles each. That is the sector-conditioned prior, and
   it is often the whole answer: a PE of 25 that is indefensible for a primary
   smelter is defensible for a metals recycler, because the conditioner
   (`capital_intensity`) differs even though the industry does not. Where your
   reading contradicts the sector default, say why in `scenario_reasoning`.

The discriminator discipline applies to the PE spread too. Your five PE
scenarios are a distribution, and the honest source of that distribution is a
historical distribution, a peer distribution, a disclosed mechanism, or a
dated forward observable. Tone, consensus, "the market will re-rate this" and
conviction are not discriminators, and a spread built on them is decoration.

## Input

`handoff/valuation_handoff.json` (historicals, estimates, PE bands,
scenario_seeds, guidance_ledger, and — when the run produced one —
`interpretation_ledger` and `company.sector_playbook`),
`prompts/sector_playbooks/<playbook>.md` § "Divergence cases" for the
sector-conditioned prior, `state/eps_bridge_check.json` (the
checker's PASS/FAIL/NA-plus-numbers per rule, the numeric skeleton for the
ladder above), `exports/<TICKER>_financials.xlsx` (open only for detail
neither the handoff nor the checker output provides), and
`report/dossier.md` (the qualitative-gate evidence: management's own
language and delivery track record). Any of these may be absent (a run that
predates one of these artifacts) — degrade gracefully, note the gap
explicitly, never fabricate what's missing.

## Output

Respond with ONLY a JSON object matching this contract:

```json
{
  "ticker": "string",
  "recommendation": "BUY | ACCUMULATE | HOLD | REDUCE | AVOID",
  "conviction": "0-1 float",
  "rerating_narrative": "string — grounded in the handoff's numbers and the dossier's qualitative evidence, not restated boilerplate",
  "catalysts": ["string"],
  "eps_scenarios": ["float x5, ascending — traceable to scenario_seeds/estimates in the handoff"],
  "pe_scenarios": ["float x5, ascending — traceable to pe_bands in the handoff"],
  "scenario_reasoning": "string — why these five EPS and five PE points, not just what they are",
  "multiple_conditioner": "string or null — the ONE conditioning variable from the closed vocabulary (docs/OPINION_VS_ANALYSIS.md §7.4) that makes your PE scenarios the right ones; null only if you are not taking a re-rating view at all",
  "opposing_reading": "string or null — the strongest defensible reading of the same PE facts that reaches the opposite conclusion, and the discriminator that made you prefer yours; null only when the handoff carried no interpretation_ledger AND you can construct no credible opposing reading, which is itself worth saying",
  "base_target_price": "float or null — must equal one grid cell (EPS scenario x PE scenario, computed deterministically downstream of this module, not by you); leave null if you don't want to anchor a single base case",
  "invalidation_condition": "string — REQUIRED (min 10 chars), a specific, checkable trigger",
  "eps_bridge_summary": "object — {rule_id: 'PASS'|'FAIL'|'NA'} for every rule_id present in state/eps_bridge_check.json, carried through as-is; omit/null only if eps_bridge_check.json itself was missing"
}
```
