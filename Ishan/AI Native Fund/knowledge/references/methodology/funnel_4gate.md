# The Four-Gate Security Selection Funnel

Source: `cycle_positioning_framework.md` section 5.4 (verbatim source:
`docs/source-material/cycle-positioning-framework.txt`, section 5.4).

Scope note: no company names, sector names, or live screens are embedded
here — this is the scoring logic the AI system runs against its own live
fundamental-data feed. Consumed by the (future) Idea Generation and
Critique agents when screening or challenging a candidate.

## The four gates, in order

### Gate 1 — Cycle-Favorability Gate (top-down)

Only surface new candidates from sectors/themes whose Sector-Specific
Cycle phase (see `knowledge/references/methodology/cycle_positioning_framework.md`
section 2.4, the eight-phase wheel, applied at sector scope per section
2.7's fractal application) is **Phase 4-7 (Value through Momentum)**.

Existing holdings in Phase 1-2 sectors move to the trim/hedge workflow
instead of the buy funnel — a Phase-1/2 sector is never a source of new
candidates regardless of how compelling an individual name inside it
looks.

### Gate 2 — Quality Screen

- ROE/ROCE **stable** (not merely high) over a 5-8yr trailing window —
  stability signals durability over a cyclically-flattered single year.
- Cash + Short-Term-Investments / Total-Assets above the peer
  distribution's median.
- FCF Yield positive and ideally rising.
- Debt/EBITDA within a peer-appropriate bound.

### Gate 3 — Idiosyncratic Value Screen

Re-run the identical Section 2 cycle-position engine at the
single-security level: percentile-rank the stock's own P/E / P/B /
EV-EBITDA against its own 5-10yr history — not just against the sector.

This deliberately catches two distinct opportunities:

- a name in its own Phase 4-6 within an already-attractive sector (best
  case); and
- it deliberately **excludes** a name that has run into its own Phase 1-2
  even inside an otherwise merely Momentum-phase sector (avoiding "the
  most extended name in a reasonable sector").

### Gate 4 — Neglect / Contrarian Confirmation Screen

- Declining or below-average institutional-ownership trend.
- A negative-but-inflecting analyst-revision trend (turning, not just
  low).
- Absence of a name-specific euphoric retail narrative.

## Sizing

Rank the shortlist by combined Quality + Idiosyncratic-Value + Neglect
confidence; size positions proportional to that combined confidence,
capped by standing single-name and sector concentration limits (see
`registry/rules/risk_limits.yaml`); log the rationale per the governance
section's explainability requirement (`cycle_positioning_framework.md`
section 6.4).

## Where this plugs in

- **Idea Generation** runs Gate 1 as a pre-filter before generating
  candidates (top-down path) — see the `idea_gen` agent.
- **Equity Research / Sectoral Analyst** agents supply the Gate 2/3 raw
  fundamentals (registry `quantitative_kpis` per sector).
- **Critique** is the natural place to re-run Gate 3/4 adversarially on a
  candidate that already passed Synthesis, before Risk Management sees it.
- This funnel does not replace the KPI-level qualitative checks already
  in `registry/kpis/<sector>.yaml` (`qualitative_checks`,
  `cycle_overlap_checks`, `niche_pointers`) — it is a sequencing/ordering
  layer on top of them.
