"""Tests for the Tier-2 conviction layer.

Three defects are covered, all of them found by measuring the LIVE record rather
than by reading the code:

1. Conviction was stretching the holding window past the only value the backtest
   validated (live positions held 110-129 days against a validated 90).
2. The score was anchored: the prompt named its own cut-offs, so the model
   returned values parked just inside the bucket it wanted, and the number
   carried no information beyond the word next to it.
3. Verdicts were not persisted, so the gate could not be evaluated at all.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

import pytest

from backtesting.qtr_results.strategy import BacktestConfig
from qtr_results import conviction as conv
from qtr_results import config, targets, verdict_log


# ── 1. Holding window parity ─────────────────────────────────────────────────


def _analysis():
    from types import SimpleNamespace

    return SimpleNamespace(
        symbol="TEST", company_name="Test Ltd", latest_quarter="Q1FY26",
        current_pe=20.0, ttm_eps=10.0, strength_score=80.0,
        yoy_profit_growth=40.0, qoq_profit_growth=10.0, yoy_sales_growth=20.0,
        yoy_eps_growth=38.0, margin_delta_pp=1.5, debt_to_equity=0.3,
    )


@pytest.mark.parametrize(
    "conviction", [None, 0.0, 0.08, 0.45, 0.58, 0.66, 0.72, 0.82, 1.0]
)
def test_holding_window_never_deviates_from_the_validated_backtest(conviction):
    """The live time stop must equal the backtest's, whatever the score.

    This is the regression that matters: the live book was carrying 110-129 day
    stops because conviction multiplied MAX_HOLDING_DAYS by 0.7 + c*0.9. The
    backtest has no conviction layer, so that stretch was never validated by
    anything.
    """
    plan = targets.build_target_plan(_analysis(), entry_price=100.0,
                                     conviction=conviction, atr=2.0)
    assert plan is not None
    effective_hold = plan.max_holding_days or config.MAX_HOLDING_DAYS
    assert effective_hold == BacktestConfig().max_holding_days


@pytest.mark.parametrize("conviction", [None, 0.1, 0.5, 0.9, 1.0])
def test_target_cap_never_deviates_from_the_validated_backtest(conviction):
    cap, hold = targets._conviction_band(conviction)
    assert cap == config.TARGET_MAX_PCT
    assert hold is None


def test_conviction_shaping_is_off():
    """Guards the flag itself; re-enabling needs a point-in-time backtest."""
    assert config.CONVICTION_SHAPES_EXIT is False


def test_shaping_flag_still_works_if_deliberately_re_enabled(monkeypatch):
    """The mechanism is retained, just disarmed -- keep it honest."""
    monkeypatch.setattr(config, "CONVICTION_SHAPES_EXIT", True)
    _, hold = targets._conviction_band(0.5)
    assert hold is not None


# ── 2. De-anchored scoring ───────────────────────────────────────────────────


def test_prompt_does_not_leak_its_own_cutoffs():
    """The anchoring bug in one assertion.

    The old prompt printed '0.75-1.0', '0.45-0.75' and '< 0.45' and then asked
    for a score; live output clustered at 0.66-0.68 for passes and 0.38-0.43 for
    rejects. If a threshold ever reappears in the prompt, that behaviour returns.
    """
    prompt = conv._build_conviction_prompt(
        {"symbol": "TEST", "company": "Test Ltd"}, _analysis(), date(2026, 8, 12)
    )
    for leaked in ("0.75", "0.45", "0.6 ", "0.0,", "[0,1]"):
        assert leaked not in prompt
    assert "conviction score" not in prompt.lower().replace(
        "do not output any conviction score", ""
    )
    assert "Do NOT output any conviction score" in prompt


def test_prompt_asks_for_disconfirming_evidence_and_allows_unknown():
    prompt = conv._build_conviction_prompt(
        {"symbol": "TEST"}, _analysis(), date(2026, 8, 12)
    )
    assert "DISCONFIRMING" in prompt
    assert '"unknown"' in prompt
    assert "not_applicable" in prompt


def _derive(**kw):
    components = {"beat_quality": "unknown", "order_book": "unknown",
                  "guidance": "unknown", "sector_backdrop": "unknown",
                  "red_flags": []}
    components.update(kw)
    return conv._derive_conviction(components)


def test_no_evidence_yields_a_neutral_verdict_that_passes():
    """Absence of evidence must not be evidence of badness."""
    score, verdict, _ = _derive()
    assert score is None
    assert conv.ConvictionVerdict(conviction=score, verdict=verdict).passes_gate


def test_evidence_moves_the_score_in_the_right_direction():
    clean, _, _ = _derive(beat_quality="operational", order_book="strong",
                          guidance="raised", sector_backdrop="tailwind")
    weak, _, _ = _derive(beat_quality="one_off", order_book="weak",
                         guidance="lowered", sector_backdrop="headwind")
    mixed, _, _ = _derive(beat_quality="mixed")
    assert clean > mixed > weak
    assert 0.0 <= weak <= clean <= 1.0


def test_scoring_is_deterministic():
    a = _derive(beat_quality="operational", order_book="adequate")
    b = _derive(beat_quality="operational", order_book="adequate")
    assert a == b


def test_severe_red_flag_vetoes_however_good_the_quarter_looks():
    score, verdict, reasons = _derive(
        beat_quality="operational", order_book="strong", guidance="raised",
        sector_backdrop="tailwind", red_flags=["auditor_concern"],
    )
    assert verdict == "skip"
    assert score == 0.0
    assert any("auditor_concern" in r for r in reasons)


def test_not_applicable_order_book_is_not_penalised():
    """Banks and FMCG have no order book; scoring that as weakness would
    systematically reject whole sectors for their business model."""
    na, _, _ = _derive(beat_quality="operational", order_book="not_applicable")
    unknown, _, _ = _derive(beat_quality="operational", order_book="unknown")
    weak, _, _ = _derive(beat_quality="operational", order_book="weak")
    assert na == unknown > weak


def test_one_off_driven_beat_is_rejected():
    score, verdict, _ = _derive(beat_quality="one_off", guidance="lowered")
    assert score < config.MIN_CONVICTION
    assert verdict == "skip"


def test_derived_score_spreads_unlike_the_anchored_one():
    """The old score took two values in practice; a derived one must vary."""
    scores = set()
    for beat in conv.BEAT_QUALITY:
        for book in conv.ORDER_BOOK:
            s, _, _ = _derive(beat_quality=beat, order_book=book)
            if s is not None:
                scores.add(s)
    assert len(scores) >= 8


# ── Parsing ──────────────────────────────────────────────────────────────────


def _wrap(payload: dict) -> str:
    return "Summary text\n\n```json\n" + json.dumps(payload) + "\n```"


def test_parse_builds_components_and_derives_the_score():
    v = conv._parse_verdict(_wrap({
        "beat_quality": "operational", "order_book": "strong",
        "guidance": "raised", "sector_backdrop": "tailwind",
        "red_flags": [], "positives": ["a"], "risks": ["b"],
        "sources": ["https://example.com"], "summary": "good",
    }))
    assert v.conviction is not None and v.conviction > config.MIN_CONVICTION
    assert v.verdict == "buy"
    assert v.components["beat_quality"] == "operational"
    assert v.sources == ["https://example.com"]
    assert v.passes_gate


def test_parse_ignores_a_model_supplied_score():
    """Even if the model volunteers a number, it must not be used."""
    v = conv._parse_verdict(_wrap({
        "conviction": 0.99, "verdict": "buy",
        "beat_quality": "one_off", "guidance": "lowered",
    }))
    assert v.verdict == "skip"
    assert v.conviction < config.MIN_CONVICTION


def test_parse_drops_out_of_vocabulary_values():
    v = conv._parse_verdict(_wrap({
        "beat_quality": "spectacular", "order_book": "Strong",
        "red_flags": ["vibes_are_off", "margin-pressure"],
    }))
    assert v.components["beat_quality"] == "unknown"
    assert v.components["order_book"] == "strong"
    assert v.components["red_flags"] == ["margin_pressure"]


def test_unparseable_output_degrades_to_a_passing_neutral_verdict():
    v = conv._parse_verdict("no json here at all")
    assert v.conviction is None
    assert v.passes_gate


def test_llm_failure_degrades_to_a_passing_neutral_verdict():
    def boom(_prompt):
        raise RuntimeError("network down")

    v = conv.evaluate_conviction(
        {"symbol": "TEST"}, _analysis(), as_of=date(2026, 8, 12),
        verdict_fn=boom, journal=False,
    )
    assert v.conviction is None
    assert v.passes_gate
    assert "network down" in (v.error or "")


# ── 3. Durable verdict journal ───────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path):
    conn = sqlite3.connect(tmp_path / "verdicts.db")
    conn.row_factory = sqlite3.Row
    conn.executescript(verdict_log._SCHEMA)
    yield conn
    conn.close()


def test_verdict_round_trips_with_its_evidence(store):
    v = conv._parse_verdict(_wrap({
        "beat_quality": "one_off", "order_book": "weak", "guidance": "lowered",
        "sector_backdrop": "headwind", "red_flags": ["margin_pressure"],
        "sources": ["https://nse.example/filing.pdf"], "summary": "flattered",
    }))
    assert verdict_log.record_verdict(
        v, symbol="TEST", decision_date=date(2026, 8, 12),
        prompt_version=conv.PROMPT_VERSION, company="Test Ltd",
        quarter="Q1FY26", connection=store,
    )
    rows = verdict_log.load_verdicts(connection=store)
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "TEST"
    assert row["passed_gate"] == 0
    assert row["beat_quality"] == "one_off"
    assert row["sector_backdrop"] == "headwind"
    # Components are stored so the weights can be re-fitted later WITHOUT
    # re-running any LLM calls -- the whole point of journalling evidence.
    assert json.loads(row["components_json"])["red_flags"] == ["margin_pressure"]
    assert row["prompt_version"] == conv.PROMPT_VERSION


def test_failed_verdicts_are_journalled_too(store):
    v = conv.ConvictionVerdict(error="network down")
    verdict_log.record_verdict(v, symbol="TEST", decision_date=date(2026, 8, 12),
                               prompt_version=conv.PROMPT_VERSION, connection=store)
    row = verdict_log.load_verdicts(connection=store)[0]
    assert row["error"] == "network down"
    assert row["conviction"] is None


def test_rerunning_a_day_does_not_duplicate_rows(store):
    v = conv.ConvictionVerdict(conviction=0.7, verdict="buy")
    for _ in range(3):
        verdict_log.record_verdict(v, symbol="TEST", decision_date=date(2026, 8, 12),
                                   prompt_version=conv.PROMPT_VERSION,
                                   connection=store)
    assert len(verdict_log.load_verdicts(connection=store)) == 1


def test_load_filters_by_date_and_prompt_version(store):
    v = conv.ConvictionVerdict(conviction=0.7, verdict="buy")
    verdict_log.record_verdict(v, symbol="A", decision_date=date(2026, 8, 1),
                               prompt_version="old", connection=store)
    verdict_log.record_verdict(v, symbol="B", decision_date=date(2026, 9, 1),
                               prompt_version=conv.PROMPT_VERSION, connection=store)
    assert len(verdict_log.load_verdicts(since=date(2026, 8, 15),
                                         connection=store)) == 1
    assert len(verdict_log.load_verdicts(prompt_version="old",
                                         connection=store)) == 1


def test_journal_failure_never_breaks_a_run(store):
    store.close()  # simulate a broken store
    assert verdict_log.record_verdict(
        conv.ConvictionVerdict(), symbol="TEST", decision_date=date(2026, 8, 12),
        prompt_version=conv.PROMPT_VERSION, connection=store,
    ) is False


def test_evaluate_conviction_journals_the_evaluation(tmp_path, monkeypatch):
    db = tmp_path / "verdicts.db"

    def _open(*_a, **_k):
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        conn.executescript(verdict_log._SCHEMA)
        return conn

    monkeypatch.setattr(verdict_log, "open_store", _open)
    conv.evaluate_conviction(
        {"symbol": "TEST", "company": "Test Ltd"}, _analysis(),
        as_of=date(2026, 8, 12),
        verdict_fn=lambda _p: _wrap({"beat_quality": "operational",
                                     "order_book": "strong"}),
    )
    rows = verdict_log.load_verdicts()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "TEST"
    assert rows[0]["passed_gate"] == 1
