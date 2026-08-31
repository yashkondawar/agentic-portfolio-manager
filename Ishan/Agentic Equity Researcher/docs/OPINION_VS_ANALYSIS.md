# Opinion vs analysis — how to read a broker note, and how to audit our own

*Derived from the 165-note corpus (`docs/ER_CORPUS_FINDINGS.md`). This document is the
checklist `prompts/34_thesis_redteam.md` runs against our own draft, and the lens
`prompts/31` applies when it consumes competitor research.*

---

## 0. Why the split matters

The corpus settles this empirically. Across 152 rated initiations: **85% BUY, 6% ADD, 3%
ACCUMULATE, 3% REDUCE, 2% SELL, 1% HOLD** — 94% positive. The BUY share measured 82% at
n=34, 82% at n=109, 84% at n=132 and 85% at n=152: about as stable as a corpus statistic
gets, and it drifted *up* as the sample grew.

A signal that is 94% positive has very little variance and therefore very little
information. The *analysis* underneath the same notes varies enormously — in depth,
granularity, honesty and method — and most of it is checkable against filings and
external data.

So:

> **Mine broker notes for their analysis. Ignore their verdicts. Never calibrate our
> rating distribution against theirs.**

The same discipline applies inward. Our own note has exactly one place where judgment
legitimately enters — the choice of multiple and the resulting rating. Everywhere else,
opinion leaking into what looks like analysis is a defect.

---

## 1. The taxonomy

### ANALYSIS — verifiable, reproducible, falsifiable

| Layer | What it contains | How to check it |
|---|---|---|
| **Structural facts** | Capacity, plants, keys/beds/branches/stores, segments, geography, product list, customer concentration, promoter holding | Against the filing. Binary. |
| **Historical numbers** | Revenue, margins, cash flow, per-unit economics, KPI time series | Re-derive from statements. Binary. |
| **Industry data** | Market size, supply-demand balance, capacity pipeline, market share, cycle position, regulatory regime | Against a *named external source*. If unsourced, it is opinion wearing analysis's clothes. |
| **Relationships** | "1% LME → 3.3% EBITDA"; "credit cost 2.5%→2.2% adds 300bps to RoE" | Recompute from the cost/revenue structure. Elasticities are arithmetic. |
| **Peer comparison** | Multiples, margins, returns, leverage, growth — *on a comparable basis* | Reproducible, but see the comparability traps in §3. |
| **Decomposition** | Volume vs price; organic vs acquired; segment mix shift | Arithmetic on disclosed data. |

### OPINION — chosen, not derived

| Layer | What it contains | Why it is opinion |
|---|---|---|
| **The rating** | BUY/ADD/REDUCE/SELL | A mapping from expected return to a label, with a threshold nobody derives. |
| **The target multiple** | "38x FY27E", "3x Sep'27E BVPS", "15x Jun'27 EV/EBITDA" | **The single biggest judgment call in the entire note.** Everything downstream of it is arithmetic. |
| **The valuation base year** | `Sep'27E`, `H1FY28E`, `Jun'27` | Rolling forward adds a year of growth to the target without touching the multiple. |
| **The peer set** | Which comparables are "the peers" | Choosing the peer set chooses the answer. |
| **Forecast drivers** | Growth rates, margin path, terminal assumptions | Anchored to guidance or history, but the anchoring choice is judgment. |
| **Risk weighting** | Which risks make the list, and in what order | Selection is editorial. |
| **Tone** | "formidable moat", "blue-chip heritage", "proxy to India's growth story" | Adjectives are not evidence. |

### The boundary case: probability and durability claims

"Credit cost normalises to ~2.2%" or "the moat is durable" sit between the two. Treat
them as **opinion with an analytical spine**: the *level* is a judgment, but the *base
rate* is checkable. HDB Financial's note does this well — it justifies a 2.2% forward
credit cost by publishing the decade average (~2%) beside it. The claim becomes
"reversion to a demonstrated base rate" rather than a hope.

Rule: a forward assumption is analysis-backed if a historical distribution, a peer
distribution, or a disclosed mechanism is published next to it. Otherwise it is opinion.

---

## 2. Failure modes — opinion masquerading as analysis

Each is stated as a **detector**, so `prompts/34` can test for it mechanically.

### F1. Circular re-rating
> "It trades at a discount to peers, so we assign a higher multiple."

The discount is the observation; assuming it closes is the conclusion; and the assumed
closure *is* the target. No mechanism, no falsifier.

*Corpus instances:* Varun Beverages (Nuvama, Sep-21) sets its target multiple *to* the
assumed narrowing of an observed FMCG discount, and SAMHI Hotels (Yes, Sep-25) makes the
peer discount its fifth pillar while attributing that discount only to unnamed factors.
Both are quoted in full in `docs/ER_CORPUS_FINDINGS.md` §6.

**Detector:** the multiple-justification sentence contains a comparative ("discount to",
"below peers", "cheap versus") and does *not* contain a named, dated mechanism.

**Important caveat, and it cuts both ways.** VBL went on to perform very well. A
re-rating call can be right while its printed reasoning is unsound. Do not treat
"the stock went up" as validation of the argument, and do not treat "the argument is
circular" as a prediction that the stock falls. Judge the reasoning, not the outcome.

### F2. Peak extrapolation
Forecasting from a cyclical high as if it were the run-rate — most dangerous in metals,
cement, chemicals, shipping, sugar and any commodity spread business.

**Detector:** the base year's margin sits in the top quartile of its own 7–10 year range
and the forecast holds or expands it, without a named structural change (commissioned
integration, permanent mix shift, closed capacity).

### F3. The base case that is really the bull case
Every driver set at the optimistic end, then labelled "base".

**Detector:** the base case sits closer to the bull than the bear on a majority of
drivers; or the bear case is not modelled, only described.

### F4. Boilerplate risk sections
"Slowdown in the economy, adverse regulatory changes, raw-material inflation, execution
risk." Generic risks that would appear in any note about any company.

**Detector:** no risk in the list is quantified, and no risk is specific enough that it
could not be pasted into a note on a different company in a different sector.

### F5. Silent basis switching
Standalone in one exhibit, consolidated in the next; pre-Ind-AS 116 here,
post there; attributable EBITDA in the peer table, headline EBITDA in the target.

**Detector:** the same metric for the same period differs across exhibits, or the basis
is unlabelled.

### F6. The unearned adjective
"Formidable moat", "blue-chip heritage", "proven execution", "best-in-class" — with no
quantification attached.

**Detector:** a moat/quality adjective within two sentences of no number.
(`config/agent_config.yaml` already bans a superlative list for our own prose; this
detector is the generalised form.)

### F7. Rolled-forward base, undisclosed
Target struck on a base year further out than the estimate horizon the rest of the note
discusses, without stating what that contributes.

**Detector:** valuation base year > the latest year in the estimates table, and no
un-rolled comparison is given.

### F8. Peer-set gerrymandering
Comparables chosen to make the target look conservative.

**Detector:** the peer set used for the target multiple differs from the peer set in the
operating-comparison table, without a stated reason.

### F9. Conflict-adjacent initiation
Initiating shortly after an IPO/QIP the house may have banked; heavy reliance on the
RHP/DRHP as a data source.

*Corpus signal:* HDB Financial (ICICI Securities, Mar-26) cites "Company RHP" and
"Company DRHP" repeatedly for a recently listed name. This is not evidence of
wrongdoing — it is the normal consequence of a recent listing being the only source of
some data — but it is a flag that belongs in the reader's field of view.

**Detector:** listing date within ~18 months of the note, or RHP/DRHP among the top
sources, or the broker named in the issue's syndicate.

### F10. Unsourced industry numbers
A market size, CAGR or share figure with no attribution.

**Detector:** an industry quantity in prose with no `Source:` line and no citation.

---

## 3. Comparability traps in the peer table

The peer table is where analysis most often silently degrades into opinion.

1. **Minority and JV structures.** SAMHI's note compares *attributable* EV/EBITDA, net of
   GIC's share. Comparing headline EV/EBITDA across peers with different ownership
   structures is arithmetically wrong.
2. **Different fiscal bases.** FY vs CY; H1FY28E vs FY27E.
3. **Adjusted vs reported.** One peer ex-ESOP, another not. Max Healthcare's note
   explicitly normalises for moderating ESOP expense.
4. **Different business mixes under one label.** A CDMO and a commodity generic are both
   "pharma"; a regulated transco and a merchant genco are both "power".
5. **Leverage.** P/E across differently-levered peers compares nothing; EV/EBITDA or
   ROCE is the honest cut.

---

## 4. The audit, as run against our own note

`prompts/34_thesis_redteam.md` executes this. Each row is pass/fail with evidence.
Checks 1–15 test whether opinion is masquerading as analysis; checks 16–18 test whether
legitimate divergence has been flattened into a single reading (§7).

| # | Check | Fails if |
|---|---|---|
| 1 | Rating appears exactly once | It appears in the summary or conclusion too |
| 2 | Return decomposed into EPS growth vs multiple change | The split is not stated numerically |
| 3 | If >40% of expected return is multiple expansion, the re-rating bar is met | No named, dated, falsifiable mechanism |
| 4 | Target multiple justified against ≥2 of: peers, own history, growth, DCF | Only one anchor, or none |
| 5 | Valuation base year stated, and the un-rolled target shown | Base rolled forward silently |
| 6 | Peer set identical for operating and valuation comparison, or difference explained | Gerrymandered |
| 7 | Peer multiples adjusted for minority/JV/leverage comparability | Headline multiples compared naively |
| 8 | Base case is between bull and bear on a majority of drivers | Base ≈ bull |
| 9 | Every risk quantified or given a threshold | Boilerplate |
| 10 | At least one **disconfirming** exhibit included | The note contains no evidence against itself |
| 11 | Every forward assumption has a published historical or peer base rate beside it | Bare assertion |
| 12 | No banned reasoning (§5) | Any hit |
| 13 | Basis consistent across exhibits, and labelled | Silent switch |
| 14 | Every industry quantity has a named source | Unsourced |
| 15 | Conflict signals disclosed (recent listing, RHP reliance) | Undisclosed |
| 16 | Every load-bearing fact has an interpretation-ledger entry (§7) | A fact the thesis rests on has only one reading on record |
| 17 | Every ledger entry states ≥1 credible opposing reading | Our reading is the only reading listed — F3 in a new costume |
| 18 | Every `resolved: true` entry cites a discriminator of an allowed type (§7.2) | Resolved by assertion; downgrade to `unresolved` and promote to a load-bearing assumption |

Check 10 deserves emphasis. ICICI's HDB Financial note publishes an exhibit showing the
company grew *slower* than peers over three years, inside a BUY recommendation
(`docs/ER_CORPUS_FINDINGS.md` §7.3). A note that contains nothing against itself has not
been tested.

---

## 5. Banned reasoning

Enforced by `prompts/34`. Each is unfalsifiable, circular, or both.

- "Deserves a higher multiple because peers trade higher." *(circular — F1)*
- "Re-rating on improving sentiment / improving visibility." *(no mechanism)*
- "The discount is unjustified." *(assertion; name what created it and what closes it)*
- "Multiple expansion as the sector re-rates." *(no company-specific mechanism)*
- "Best-in-class execution" as a reason for a premium, without the metric that shows it.
- "Structural story" / "secular growth" without a quantified end-market and a share path.
- "Attractive risk-reward" without the downside actually computed.
- "Management is confident" as evidence. *(That is guidance, and it goes through
  `prompts/22`'s credibility ledger.)*
- "Historically it traded at Xx" without asking whether the earnings base then and now
  are comparable. *(A cyclical's peak-cycle multiple on trough earnings is not a floor.)*

---

## 6. Applying this to competitor research

When `prompts/31` ingests a broker note as an external source:

- **Take:** structural facts, KPI definitions, industry data with sources, historical
  series, elasticities, cost stacks, capacity pipelines, exhibit ideas.
- **Take with attribution and a credibility tag:** forecasts, market-size projections.
- **Discard:** the rating, the target price, the tone.
- **Record separately:** where the note's own analysis contradicts its conclusion. That
  divergence is a high-value signal — it is usually the analyst being honest under
  commercial pressure, and it points at the real bear case.

Broker-specific adjustments — including Kotak, whose numbers work is strong while its
conclusions run structurally conservative — are in `docs/BROKER_CALIBRATION.md`.

---

## 7. Same fact, divergent readings

Sections 1–6 tell you *whether* a statement is analysis or opinion. They do not tell you
what to do when two competent analysts read the **same verified fact** and reach opposite
conclusions — which is the normal case, not the pathological one.

### 7.1 The rule

A **fact** is a published quantity or a disclosed mechanism. A **reading** is:

```
fact  +  conditioning variable  +  sector convention  ->  verdict
```

Two readings of one fact are both legitimate when each names its conditioning variable.
A reading that names none is an unearned adjective (§2 F6) wearing a number.

The canonical case:

> **Fact:** the company trades at a trailing P/E of 30. Verified against price and
> reported EPS. Nobody disputes it.
>
> **Reading A — expensive.** Conditioning variable: `own_history_anchor`. The company's
> own 10-year median P/E is 18. At 30 the market is paying a 67% premium to how it has
> historically been priced, and the note must say what changed.
>
> **Reading B — cheap.** Conditioning variable: `growth_rate`. Earnings are compounding
> at 30%, so PEG is 1.0. On a growth-adjusted basis the stock is at parity, and Reading A
> is comparing a high-growth present against a low-growth past.
>
> **Neither is wrong.** Both are arithmetic on the same disclosed numbers.

### 7.2 The discriminator

What separates the two readings is not rhetoric — it is a specific, nameable piece of
evidence. Here it is **the durability of the 30% growth rate**, because PEG 1.0 silently
assumes the growth persists long enough to earn back the multiple. So the question
becomes falsifiable: *how often has a company in this sub-sector sustained 30% earnings
growth for the number of years this PEG implies?* Publish that base rate, or concede the
reading is opinion.

Only four things may serve as a discriminator:

| Type | What it is | Example |
|---|---|---|
| `historical_distribution` | The company's or sector's own realised record | "3 of 41 Indian IT names held 20%+ EPS growth for 5 consecutive years" |
| `peer_distribution` | The cross-sectional spread today, on a comparable basis | "peer PEGs range 0.7–1.4; this is at 1.0" |
| `disclosed_mechanism` | A named, dated structural cause published by the company | "the commissioned Line 3 adds 40% capacity from Q2FY27" |
| `forward_observable` | A falsifiable future observation with a date attached | "if Q3FY27 order inflow is below ₹X, Reading B is dead" |

Tone, consensus, "the market is wrong", and analyst conviction are **not** discriminators.

### 7.3 Sector conditions the reading

The same fact carries a different default reading in different sub-sectors, and that
default is not a preference — it is what the economics of the business dictate. This is
already encoded: each `prompts/sector_playbooks/<slug>.md` carries a
`## Valuation convention` section and a `## Divergence cases` section, and
`config/sector_registry.yaml` carries the machine form of the same thing per playbook
(`primary_multiple`, `secondary_multiples`, `multiple_conditioners`).

Two illustrations already in the playbooks:

- **P/E 25 on a metals company.** In `ferrous_non_ferrous_metals` the convention is
  EV/EBITDA on *mid-cycle* EBITDA, because a primary smelter's P/E is contaminated by
  plant vintage, leverage and where the cycle sits. But the playbook also records that
  *"for a recycler, a P/E is more defensible"* — Gravita at 25x FY28E P/E is arguable;
  the identical multiple on a primary smelter is not. Same multiple, same family,
  opposite verdicts, and the discriminator is `capital_intensity` plus `cycle_position`.
- **Two tier-2 IT companies deserving the same multiple.** `it_services` records that
  15% cc growth with a flat EBIT margin and 12% growth with 200bps of margin expansion
  can support the same P/E — *"the note must say which combination it is paying for."*
  The discriminator is `growth_durability` versus `incremental_roce`.

### 7.4 The closed vocabulary of conditioning variables

A reading must name its conditioner from this list. The list is closed so that readings
are comparable across notes and machine-checkable; it lives in machine form under
`interpretation_vocabulary` in `config/sector_registry.yaml`, and E13 in
`tools/validate_sector_registry.py` rejects anything outside it.

| Token | The question it answers |
|---|---|
| `growth_rate` | Is the multiple justified by the *level* of growth (PEG)? |
| `growth_durability` | For how many years must that growth hold, and has it ever? |
| `incremental_roce` | What return does the *marginal* rupee of capital earn? |
| `sustainable_roe` | What through-cycle return level does a P/B or P/ABV capitalise? |
| `cycle_position` | Is the earnings base at trough, mid-cycle or peak? |
| `earnings_base_quality` | Adjusted vs reported, attributable vs headline, one-offs, core |
| `capital_intensity` | Asset-heavy or asset-light; what does replacement cost say? |
| `terminal_value_share` | How much of the value sits beyond the forecast horizon? |
| `balance_sheet_risk` | Does leverage, funding cost or covenant change the verdict? |
| `accounting_basis` | Ind-AS 116, standalone vs consolidated, fiscal-base mismatch |
| `own_history_anchor` | How is this priced against its own multiple band? |
| `peer_set_choice` | Which comparables define "the peers", and who chose them? |

### 7.5 The escalation — unresolved is a legitimate outcome

Where the available evidence cannot discriminate between two readings, **do not resolve
it by assertion.** Record the entry as `resolved: false` and promote it to a
**load-bearing assumption** of the thesis. A disclosed unresolved divergence is worth
more to a reader than a confident verdict with no discriminator behind it, and it is
exactly what `config.report.stance: evidence_first` is for.

This is the honest form of the §0 finding. A 94%-positive rating distribution is what
happens when an industry resolves every divergence in the same direction by default.

### 7.6 Where this is recorded

`prompts/33_thesis_synthesis.md` writes `state/interpretation_ledger.json` (schema:
`schema/interpretation.schema.json`) alongside `state/thesis.json`. Every
valuation-relevant fact whose reading is load-bearing gets one entry: the fact, its
source, the competing readings with their conditioners, the discriminator, our reading,
and the sector convention applied.

`prompts/34_thesis_redteam.md` audits it — checks 16–18 of the audit in §4. The failure
mode it is hunting is a ledger in which our reading is the only reading listed, which is
§2 F3 (the base case that is really the bull case) in a new costume.
