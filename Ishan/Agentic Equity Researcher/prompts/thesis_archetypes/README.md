# Thesis archetypes — the index

*Selected by `prompts/33_thesis_synthesis.md` the way triage selects a sector pack.
Derived from the 165-note corpus; see `docs/ER_CORPUS_FINDINGS.md` §6.*

An equity thesis is not a list of good things about a company. It is a **claim about why
the current price is wrong, and what has to happen for that to be resolved.** Different
claims have different shapes, need different evidence, and fail in different ways. This
library names the shapes.

## How module 33 uses this

1. Compute the **return decomposition** first — split expected return into EPS/BVPS
   growth versus change in the multiple. The split largely determines the archetype and
   must be published either way.
2. Select **one primary archetype** (and at most one secondary). Record the evidence for
   the choice.
3. Run that archetype's **`must_be_true` checklist** against the evidence base. Every
   condition gets `established` / `partial` / `unestablished` with fact references.
4. Record its **falsifiers** as monitorables with thresholds.
5. Apply its **skepticism weight** when converting the checklist into a rating.
6. `prompts/34_thesis_redteam.md` then attacks the result, in a separate context, using
   that archetype's `standard_failure_mode`.

A thesis whose `must_be_true` conditions are mostly `unestablished` does not become a
weaker BUY. It becomes **no thesis** — and the honest output is a rating driven by
valuation alone, with the gap disclosed.

## The archetypes

| Archetype | Return comes from | Skepticism weight | File |
|---|---|---|---|
| GARP | Earnings growth, multiple broadly held | Low (1) | [garp.md](garp.md) |
| Quality compounder | Sustained high ROCE reinvested | Low-medium (2) | [quality-compounder.md](quality-compounder.md) |
| Margin expansion | Operating leverage or mix | Medium (3) | [margin-expansion.md](margin-expansion.md) |
| Market-share gainer | Volume outgrowing the market | Medium (3) | [market-share-gainer.md](market-share-gainer.md) |
| Capex-to-cashflow | FCF inflection as capex rolls off | Medium (3) | [capex-to-cashflow.md](capex-to-cashflow.md) |
| Balance-sheet repair | Deleveraging shifting value to equity | Medium (3) | [balance-sheet-repair.md](balance-sheet-repair.md) |
| Cyclical recovery | Cycle turning off a trough | Medium-high (4) | [cyclical-recovery.md](cyclical-recovery.md) |
| Regulatory tailwind / PLI | Policy-created economics | Medium-high (4) | [regulatory-tailwind.md](regulatory-tailwind.md) |
| Turnaround | Fixing a broken business | High (4) | [turnaround.md](turnaround.md) |
| Special situation | Demerger, holdco, asset monetisation | High (4) | [special-situation.md](special-situation.md) |
| Deep value / SOTP | Price below parts or replacement cost | High (4) | [deep-value-sotp.md](deep-value-sotp.md) |
| **Re-rating** | **The multiple itself** | **Highest (5)** | [re-rating.md](re-rating.md) |
| Cyclical peak (bear) | Cycle rolling over | Medium-high (4) | [cyclical-peak.md](cyclical-peak.md) |
| De-rating (bear) | Multiple compressing | High (4) | [de-rating.md](de-rating.md) |

## The skepticism scale

Weight is **how much a passing checklist is worth**, not how likely the thesis is to be
right. It reflects how easily each archetype's argument can be constructed from
ambiguous evidence.

| Weight | Meaning | Effect on rating |
|---|---|---|
| 1 | Claim is mostly arithmetic on established trends | Checklist taken at face value |
| 2 | Claim rests on durability of a demonstrated record | Require the record to span a full cycle |
| 3 | Claim rests on a change that has started but not completed | Require in-period evidence, not just a plan |
| 4 | Claim rests on a change that has *not* started, or on external conditions | Require a dated catalyst and a named falsifier; cap conviction |
| 5 | Claim rests on other investors changing their minds | Require a mechanism, a catalyst, a falsifier, AND an explanation of what the market currently believes and why it is wrong. Absent any of these, the archetype is rejected and the thesis reverts to its underlying earnings case. |

**Why re-rating alone sits at 5.** Every other archetype makes a claim about the
*business*, which the filings can eventually adjudicate. Re-rating makes a claim about
*the market's opinion of the business*. It is the only archetype where being right
requires other people to agree with you, and the only one with no internal evidence that
can ever confirm it. And in the corpus it is never a passing remark: roughly one note in
five reaches for re-rating language, and those that do use it repeatedly (median 3
mentions) — it appears as load-bearing argument, not as an aside. See `docs/OPINION_VS_ANALYSIS.md` §2 F1 for the two worked corpus examples.

## The 40% rule

If more than **40%** of expected return comes from a change in the multiple rather than
growth in the underlying metric, the thesis is typed `re-rating` **regardless of what
else it is called**, and must clear that file's bar. This is checked arithmetically, not
by reading the note's self-description — SAMHI Hotels calls itself a turnaround, and it
is one, but a large share of its upside is the multiple moving from ~11x to 15x, so it
must clear the re-rating bar too.

Threshold configured at `config/agent_config.yaml → thesis.rerate_share_threshold_pct`.

## File format

Each archetype file carries, in this order: `definition` · `return_source` ·
`must_be_true` (3–6 numbered conditions, each with the evidence that would establish it) ·
`standard_evidence_pattern` · `standard_failure_mode` · `falsifiers` ·
`skepticism_weight` · `sectors_where_it_recurs` · `corpus_examples`.
