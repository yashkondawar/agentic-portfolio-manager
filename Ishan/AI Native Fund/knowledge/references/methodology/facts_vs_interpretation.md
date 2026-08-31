# Facts vs interpretation: the divergence rule and the discriminator types

Author: authored for the fund. The evidence base behind it — 165 broker notes
read against this taxonomy — lives in the ER subsystem at
`research/equity_researcher/docs/OPINION_VS_ANALYSIS.md` (§1 taxonomy, §2 ten
failure modes, §5 banned reasoning, §7 same fact, divergent readings). This
doc is the fund-side canonical statement and is kept deliberately thin:
packets carry a pointer to it, never its text.

## Why this exists

The fund already separates *fact* from *opinion* in one place — the
`research_head` agent's `"is_opinion": false` flag on each research finding.
That flag answers "did someone measure this, or choose it?" It does not answer
the question that actually decides most positions:

> Two analysts agree on every published number and reach opposite conclusions.
> Which one is right, and what evidence would settle it?

A P/E of 30 is **expensive** against the company's own 10-year median of 18.
The same P/E of 30 is **cheap** at a PEG of 1.0. Both are arithmetic on
identical disclosed numbers. Neither analyst has made an error. Calling one of
them wrong without naming what separates them is the failure this doc exists
to prevent — and it is the most common failure in sell-side and buy-side work
alike, because it feels like judgement rather than a gap.

## The three-part rule

**A fact** is a published quantity or a disclosed mechanism. It is checkable,
and it is the same for everyone. "Trailing P/E is 30.2 on FY25 consolidated
EPS" is a fact. "The multiple is rich" is not.

**A reading** is:

```
fact + conditioning variable + sector convention -> verdict
```

Two readings of one fact are **both legitimate** when each names its
conditioning variable. A verdict that names none is an unearned adjective, and
under the ER audit it is a §2 failure-mode hit, not analysis.

**A discriminator** is the evidence that settles between readings. Exactly
four types count:

| Type | What it is | Example against the P/E 30 case |
|---|---|---|
| `historical_distribution` | A published base rate over time | How often has an Indian IT company sustained 20% cc growth for the 5 years a PEG of 1.0 implicitly assumes? |
| `peer_distribution` | A cross-sectional distribution across a **named** peer set at a stated date | Where does 30x sit in the distribution of the 8 comparables, on the same base year? |
| `disclosed_mechanism` | Something the company or regulator actually disclosed | A signed 5-year contract, a tariff order, a covenant, an accounting-policy change |
| `forward_observable` | A falsifiable future observation **with a date** | "Q3FY27 order inflow below ₹X kills the durability reading" |

Nothing else counts. Consensus, tone, conviction, and "the market is wrong"
are absent from that list on purpose — they are the things that feel like
evidence and are not.

The worked case, all the way through:

- **Fact.** Trailing P/E = 30.2 (FY25 consolidated EPS, annual report p. 84).
- **Reading A.** Expensive. Conditioner: `own_history_anchor` — the stock's own
  10-year median is 18x.
- **Reading B.** Cheap. Conditioner: `growth_rate` — PEG is 1.0 on 30% forward
  EPS growth.
- **What actually separates them.** Neither the median nor the PEG. It is
  `growth_durability`: how many years the 30% holds. Reading A silently assumes
  the business today is comparable to the business that earned the 18x median;
  Reading B silently assumes the growth persists roughly as long as the
  multiple implies.
- **Discriminator.** `historical_distribution` — the published base rate for
  sustaining that growth over that many years, for this sector. Cite it, or
  concede the reading is opinion.

## Unresolved is an answer

Where no discriminator of an allowed type exists, the divergence is recorded
`resolved: false` and becomes a **disclosed load-bearing assumption**. It is
not deleted, and one reading is not quietly adopted as though it were the
fact. A named assumption a reader can attack is worth more than a verdict with
nothing behind it — and it is the only honest output when the evidence is not
there, which the fund's no-fabrication rule (CLAUDE.md) requires anyway.

## Sector convention is part of the reading

The same multiple carries different meaning by sector, and that is convention,
not preference. A P/E is defensible for a metals recycler whose spread is
contractual and indefensible for a primary smelter whose earnings are an LME
derivative; both are "metals". A bank is read on P/B conditioned by
`sustainable_roe`; an infra developer on SoTP conditioned by
`balance_sheet_risk` and `terminal_value_share`, because an equity multiple on
a leveraged asset owner answers the wrong question.

Which multiple, and which conditioners, are **governed data, not prose**:

- `registry/rules/interpretation_frames.yaml` — the fund's 12-token closed
  vocabulary, the 5 discriminator types, and default frames for the 8 sector
  slugs. All `status: DRAFT` until back-tested.
- `research/equity_researcher/config/sector_registry.yaml` — the same 8
  families plus 32 tier-2 playbooks (upstream-owned).
- `src/afund/research/interpretation.py::resolve_frame()` — layers them,
  family first and playbook on top, and is what puts `interpretation_frame`
  into the buy-side and sector packets.
- `scripts/check_interpretation_frames.py --check` — one-way check that the
  upstream tokens stay inside the fund vocabulary.

## Where this is enforced

| Layer | Mechanism |
|---|---|
| Contracts | `FactClaim`, `Reading`, `DivergenceCase` in `src/afund/agents/contracts.py`. `DivergenceCase` raises if `resolved: true` names no discriminator. |
| Buy-side | `BuySideRecommendation.multiple_conditioner` — the recommendation must say which variable makes its chosen P/E defensible. |
| Sector | `SectorResearchNote.facts` / `.interpretations` / `.divergence_cases`. |
| Critique | The 18-check audit; `opinion_audit`, `banned_reasoning_hits`, `unresolved_divergences`. |
| ER run | `state/interpretation_ledger.json` (written by `prompts/33` step 6b, schema `schema/interpretation.schema.json`), audited by `prompts/34` checks 16–18, carried into the fund on `valuation_handoff.interpretation_ledger`. |

## What this does not do

It does not decide which reading is right. It forces the disagreement to be
stated in terms that can be resolved by evidence rather than by whoever writes
the note last.
