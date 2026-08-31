# Narrative Intensity Scoring

Source: `cycle_positioning_framework.md` sections 2.5-2.6 (verbatim
source: `docs/source-material/cycle-positioning-framework.txt`, sections
2.5-2.6).

## Why this exists

Numbers alone can't tell you whether a historical range is still valid.
Two assets can have an identical valuation percentile and mean opposite
things — one because nobody has noticed yet, one because everybody has
already sold and it's a trap. This is where an AI system's
language-reasoning capability is a genuine structural advantage over a
traditional quant model: it can read news flow, earnings-call
transcripts, analyst notes, fund-flow commentary, and retail sentiment,
and score them systematically, at a scale and consistency a human analyst
cannot sustain.

## Scale

Narrative Intensity Score: **-100 to +100**, on the same phase scale as
the quantitative cycle-position read (Phase 1 Euphoria at the positive
extreme, Phase 5 Deep Value/Capitulation at the negative extreme).

## Markers to detect, by cycle position

**Top-of-cycle psychology (Phases 1-2, score toward +100):**
- Narratives of structural permanence ("new paradigm," "structural
  re-rating").
- Dismissal of valuation concerns as failure to understand a new reality.
- Surging retail participation and leverage.
- Proliferation of new products/instruments around the theme.

**Bottom-of-cycle psychology (Phase 5, score toward -100):**
- Narratives of permanent impairment ("this is structurally broken,"
  "nobody wants this").
- Forced or redemption-driven selling.
- Capitulatory analyst downgrades even as operating metrics stabilize.
- An absence of new capital/product formation in the space.

**Transition markers (Phases 3, 6, score near the midpoint but watch the
gap):**
- A persistent gap between price action and narrative — price stops
  falling despite continued bad headlines, or stops rising despite
  continued good ones.
- Early, quiet positioning shifts ahead of broad recognition.

## Reconciling quantitative and qualitative reads

| Quantitative phase vs. Qualitative phase | Interpretation | Action |
|---|---|---|
| Aligned | High-confidence classification | Proceed at full conviction sizing |
| Quant reads cheap, narrative still dismissive/pessimistic | The classic contrarian sweet spot — the crowd hasn't repriced yet | Highest-conviction opportunity, but mandatory Pre-Mortem first, to rule out a genuine value trap |
| Quant reads expensive, narrative still euphoric | Late-cycle, textbook top-forming pattern | Reduce; do not wait for narrative confirmation, which arrives after price does |
| Ambiguous / conflicting in an unclear way | Genuine uncertainty | Lower confidence, smaller size, flag for human/deeper research review |

## Where this plugs in

- Feeds the `narrative_intensity_score` field of the `CycleAssessment`
  output schema (`cycle_positioning_framework.md` section 6.5).
- The `research_head` / `synthesis` agents are the natural producers of
  this score today (text-reasoning over news/newsletter digests already
  flowing through `news_items` and the `knowledge_base` table); the
  `macro_digest` agent's MACRO-tagged notes are a direct qualitative-marker
  source for the macro cycles specifically.
- Divergence between quantitative phase and narrative score is a
  **mandatory Pre-Mortem trigger**, not just a confidence adjustment — see
  `buyside_depth.md` and `cycle_positioning_framework.md` section 6.2.
