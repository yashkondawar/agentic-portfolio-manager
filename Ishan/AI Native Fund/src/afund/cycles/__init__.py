"""Phase 7 cycle engine.

Encodes the Universal Cycle-Positioning Framework
(docs/source-material/cycle-positioning-framework.txt) as constitution-as-
config (registry/strategies/cycle_framework.yaml, loaded by framework.py)
plus pure-Python computation modules:

    framework.py   pydantic loader for cycle_framework.yaml
    anchors.py     per-cycle anchor-metric series (live day-1 cycles only;
                   everything else honestly reports data_pending)
    transforms.py  orientation transforms (value/fear/goldilocks)
    classify.py    percentile, direction, momentum-of-momentum, 8-phase
                   classification (pure, golden-testable)
    parabolic.py   Parabolic Return Compression Rule check
    composite.py   EVI, functional-group rollup, regime cluster, composite
                   score, alignment score, reconciliation quadrant
    narrative.py   narrative_intensity agent packet builder (no LLM here)
    assess.py      orchestration: run live cycles, write cycle_assessments +
                   composite_decisions rows, CLI entry point

All strategy thresholds are DRAFT until back-tested (see CLAUDE.md). Never
fabricate a reading for a KPI/cycle whose data is not genuinely available —
report data_pending explicitly instead.
"""
