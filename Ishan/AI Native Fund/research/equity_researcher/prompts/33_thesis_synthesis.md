# 33 — Thesis Synthesis (owns `state/thesis.json`, `state/interpretation_ledger.json` and the rating)

*(NEW. Sonnet tier, high thinking. Runs at step 6a, after peer-valuation (23) and
estimates (32), before the red team (34) and the report (40/41). Re-runs when any thesis
pillar's evidence goes stale.)*

## Why this module exists

Until now nothing owned the thesis. `prompts/01` said `state/thesis.json` was written "by the
orchestrator after each wave"; `CLAUDE.md` said modules 23 and 32 produced it; neither
agent definition mentioned writing it; prompt numbering jumped 32 → 40. The rating was
improvised each run from one sentence in `docs/SOP_ORCHESTRATOR_RUNS.md`. There was no
archetype library, no consistency between runs, and no separation between the evidence
and the verdict.

This module closes that. It does **not** generate new facts. It selects, types, tests and
concludes over work already done.

## Inputs
`findings/*.json` (fundamental, forensic, guidance, governance, peer_valuation, estimates)
· `state/business_model.json` (identity, net_position, kpi_tree, swing_drivers)
· `state/red_flags.json` · `state/open_questions.json` · `facts/estimates.json`
· `facts/market_data.json` · `handoff/valuation_handoff.json`
· `prompts/thesis_archetypes/README.md` and the selected archetype file(s)
· `prompts/sector_playbooks/<playbook>.md` §§ "Valuation convention" and "Divergence
  cases" — the convention, its traps, the corpus note anchoring it, and the sub-sector's
  canonical same-fact/different-reading pairs. (`config/sector_registry.yaml` routes only,
  and carries the machine form: `primary_multiple`, `multiple_conditioners`.)
· `docs/OPINION_VS_ANALYSIS.md` §7 — the divergence rule and the closed vocabulary.

## Outputs

1. `state/thesis.json` — must validate against `schema/thesis.schema.json`
2. `state/interpretation_ledger.json` — must validate against `schema/interpretation.schema.json`
   (step 6b). One entry per valuation-relevant fact whose *reading* is load-bearing.

Work through the steps in order. Do not jump to the rating.

---

### Step 1 — The return decomposition (do this FIRST)

Before naming any archetype, split the expected return arithmetically:

```
expected_return  =  (1 + metric_growth)  ×  (1 + multiple_change)  −  1
```

where `metric` is the valuation metric the sector convention uses (EPS, EBITDA, BVPS,
EV/EBITDA base). Publish all four numbers: current multiple, target multiple, current
metric, target-year metric.

Then compute `multiple_share_pct` — the fraction of expected return attributable to the
multiple moving rather than the metric growing.

**This is the most important number in the module.** It determines the archetype, the
skepticism weight, and what the red team will attack. It appears in the final note.

**Also state the valuation base year explicitly**, and if it is rolled forward beyond the
last year in the estimates table (`Sep'27E BVPS`, `H1FY28E EV/EBITDA`), show what the
target would be un-rolled. The corpus shows this is routinely done and never disclosed
(`docs/ER_CORPUS_FINDINGS.md` §4).

### Step 2 — Select the archetype

Read `prompts/thesis_archetypes/README.md`, pick **one primary** archetype and at most one
secondary, and record the evidence for the choice.

**The 40% rule is mechanical and overrides self-description.** If
`multiple_share_pct > config.thesis.rerate_share_threshold_pct` (default 40), the thesis
is *additionally* typed `re-rating` and must clear `re-rating.md`'s five conditions —
whatever else it is called. A turnaround with a large multiple-expansion leg is both.

### Step 3 — Build the pillars

3–4 pillars, each: a claim, ≥2 independent evidence refs (different source documents, per
`config.orchestration.evidence_min_per_thesis_pillar`), and the fact IDs.

A pillar must be **falsifiable** and **decision-relevant**. "The company has a strong
brand" is neither. "Direct distribution reach of X outlets, up Y% over three years, is
what allows the price increase taken in Q2 to hold — and it did, with volume flat" is
both.

Ban the reasoning listed in `docs/OPINION_VS_ANALYSIS.md` §5 at pillar level too.

### Step 4 — Run the archetype's `must_be_true` checklist

For each condition in the selected archetype file, record:

```json
{ "condition": "...", "status": "established | partial | unestablished",
  "evidence": ["fact ids"], "why": "one line" }
```

Be honest about `partial`. The point of the checklist is to find out what we have *not*
established, not to produce a pass.

**If the majority of conditions are `unestablished`, the archetype is rejected.** Do not
downgrade to a weaker version of the same thesis. Say so, fall back to the underlying
earnings case with the multiple held flat, and disclose the gap. A thesis that cannot be
evidenced is not a thesis.

### Step 5 — Falsifiers → monitorables

Convert each archetype falsifier into a monitorable with a **numeric threshold and a
review date**. "Watch margins" is not a monitorable. "Gross margin below 31% for two
consecutive quarters, or a second commissioning slip beyond Q3FY27, downgrades pillar 2"
is.

### Step 6 — The variant view

State where we differ from management guidance (credibility-weighted per `prompts/22`)
and from consensus where `prompts/31` located it. Then the **reverse read**: at CMP and
our forward metric, what growth path does the market's multiple imply, versus ours?

If we differ from neither guidance nor consensus, say so plainly. **No variant view is a
legitimate finding** — it means the analysis supports the current price, and the rating
should reflect that rather than manufacturing a disagreement.

### Step 6b — The interpretation ledger (you own `state/interpretation_ledger.json`)

Steps 1-6 separate what is established from what is not. This step handles the case that
distinction does not cover: **two competent readers agree on a verified fact and disagree
about what it means.** A trailing P/E of 30 is expensive against a ten-year median of 18
and cheap at a PEG of 1.0. Both are arithmetic on the same disclosed numbers. Neither is
wrong. What separates them is a named **conditioning variable** and a named
**discriminator**, and this file is where both are recorded.

The rule, the closed twelve-token vocabulary of conditioning variables, and the four
admissible discriminator types are in `docs/OPINION_VS_ANALYSIS.md` §7. The sub-sector's
canonical divergences — the same fact carrying different default verdicts in different
industries — are in `prompts/sector_playbooks/<playbook>.md` § "Divergence cases". Read
that section before writing entries; it is the sector-conditioned prior, and an entry that
contradicts it must say why.

Write one entry per load-bearing valuation fact. Each entry needs:

- **`fact`** — the verified quantity or disclosed mechanism, stated so nobody disputes it,
  with its `fact_source`. Introduce no new facts here; step 6b is a reading of the
  existing stores, not a new pass over them.
- **`readings`** — **at least two.** Each names one conditioning variable from the closed
  vocabulary and shows the arithmetic or mechanism that gets from the fact to the verdict.
  A reading that names no conditioner is an unearned adjective (§2 F6) and does not count.
  Listing only our own reading fails red-team check 17 — it is F3, "a base case that is
  really the bull case", in a new costume.
- **`discriminator`** — the evidence that settles between them: a historical distribution,
  a peer distribution, a disclosed mechanism, or a dated forward observable. **Tone,
  consensus, "the market is wrong" and analyst conviction are not discriminators.** Where
  none of the four is obtainable, use `none_available`, state what evidence *would* settle
  it, and set `resolved: false`.
- **`our_reading`** and **`materiality`**.

Where a divergence is unresolved and the thesis proceeds anyway, that is legitimate — set
`becomes_load_bearing_assumption: true` and carry it into `rating.capped_by`. Under
`stance: evidence_first` a disclosed unresolved divergence is worth more to a reader than a
verdict with nothing behind it. What is not legitimate is resolving it by assertion.

The ledger feeds step 7 directly: the multiple in the return decomposition is the single
biggest judgment call in any note, and its conditioning variable must appear here.

### Step 7 — Derive the rating, bottom-up

The rating is a **consequence** of steps 1-6b, not an input to them.

1. Start from expected return over the horizon (step 1).
2. Apply the archetype's skepticism weight: at weight 4-5, evidence that is `partial`
   counts as `unestablished` for rating purposes.
3. Haircut for confirmed high-severity red flags and for governance findings.
4. Widen the range for disclosed data gaps and for `sparse` data mode.
5. Map to the scale in `config.rating.scale`.

Then, mandatorily, **argue the other side**: write the strongest case for the adjacent
rating in both directions ("not-BUY-because…", "not-SELL-because…"). If you cannot
construct a credible opposite case, the evidence base is too thin for a confident rating —
say that.

The rating appears **exactly once** in the final note, in the rating box.

### Step 7b — The mandatory post-red-team pass (you own `redteam`)

`prompts/34` runs after you, in a **separate context**, and writes `findings/thesis_redteam.json`.
It is forbidden from editing `state/thesis.json` — a red team that can rewrite the thesis it is
attacking is not a red team. But `schema/thesis.schema.json` carries a `redteam` block, and
**you are its only possible writer, because you own this file.** Before 2026-08-03 that block had
no writer and was an orphan.

So you run a second time, always — `config.thesis.redteam_min_rounds` is 1 and the round trip is
never skipped. On that pass:

1. Read `findings/thesis_redteam.json` in full.
2. **Answer every high-severity challenge**: either revise the thesis (pillar, must-be-true status,
   monitorable, expected return, or rating) or record why the challenge does not land. Dropping one
   silently is not permitted — module 34's verdict names them and the note surfaces the count.
3. If the verdict is `not_established`, the thesis is **not** publishable as-is: revise until it is
   `survives` or `survives_with_qualifications`, or downgrade the rating to what the evidence
   actually supports.
4. Write the `redteam` block back into `state/thesis.json`:
   `verdict`, `material_challenges_count`, `high_severity_challenges`, `disconfirming_exhibit`
   (which exhibit in the note carries it), and `rounds` (≥1).
5. Re-validate against the schema (`python tools/validate_state.py <workspace>`).

The rating you emit after this pass is the one that ships. If it changed, say so in your return
summary — a rating that survives a red team unchanged and one that was revised by it are different
facts about the thesis, and the run log should show which happened.

## Your role under `stance: evidence_first`

`config.report.stance` is `evidence_first`, so be clear about what you are for. **You are quality
control on the evidence, not the author of the report's headline.** The rating you derive is a
bounded by-product that appears once, in a one-page section at the END of the note, and disappears
entirely when `config.rating.emit` is false. That does not reduce your work — it changes which of
your outputs matters most to a reader:

- **Most valuable:** the `must_be_true` checklist with honest `established / partial / unestablished`
  statuses, the return decomposition (which surfaces the multiple — the one real judgment call in any
  note), the monitorables as thresholded falsifiers, and the disconfirming exhibit. All of these are
  *evidence about how good the evidence is*, which is exactly what a reader forming their own opinion
  needs.
- **Least valuable, and treated as such:** the rating letter. `docs/ER_CORPUS_FINDINGS.md` §5 measured
  why — 94% of 165 initiations are positive, so "the rating carries almost no information."

Two consequences for how you work. First, **never soften an `unestablished` status to make the rating
easier to defend** — the status is the deliverable and the rating is the by-product, not the reverse.
Second, if the evidence does not support any confident call, say so in `rating.confidence` and
`rating.capped_by` rather than manufacturing conviction; an honest "medium, capped by X" is more useful
to a reader than a decisive letter.

## Guardrails
- Introduce no new facts. Every number carries a fact ID from an existing store. If you
  need a fact that does not exist, raise an open question and mark the pillar `partial`.
- Do not write the note's prose. Module 41 does that.
- Do not compute a formal target price — that stays with the downstream engine
  (`handoff/valuation_handoff.json`). Fair-value *context* is permitted and must be
  labelled as such.
- **You will be adversarially reviewed by module 34, running in a separate context.**
  Write the checklist honestly; a `partial` you disclose costs far less than one the red
  team finds.
