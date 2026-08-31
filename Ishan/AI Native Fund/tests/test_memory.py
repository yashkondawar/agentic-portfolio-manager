"""Offline tests for afund.memory.stores + afund.memory.retrieval.

All synthetic data seeded into a temp SQLite DB built from schema.sql. No
network, no LLM calls.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from afund.memory import retrieval, stores

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "afund_test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()
    yield connection
    connection.close()


def _seed_instrument(conn, id_, symbol, sector):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector, active) VALUES (?, ?, 'STOCK', ?, 1)",
        (id_, symbol, sector),
    )
    conn.commit()


# --- decision_log ------------------------------------------------------------


def test_record_recommendation_and_get_precedents(conn):
    _seed_instrument(conn, 1, "INFY", "Information Technology")
    decision_id = stores.record_recommendation(
        conn,
        instrument_id=1,
        sector="Information Technology",
        action="NEW",
        strategy_tag="cycle_contrarian",
        invalidation_condition="if 1y return >= 100%",
        fund_manager_rec_json={"conviction": 0.7},
        registry_version="abc123",
    )
    assert isinstance(decision_id, int)

    row = conn.execute("SELECT * FROM decision_log WHERE id = ?", (decision_id,)).fetchone()
    assert row["human_decision"] == "PENDING"
    assert row["action"] == "NEW"

    precedents = stores.get_precedents(conn, instrument_id=1)
    assert len(precedents) == 1
    assert precedents[0]["id"] == decision_id


def test_get_precedents_no_filters_returns_empty(conn):
    assert stores.get_precedents(conn) == []


def test_get_precedents_most_recent_first(conn):
    _seed_instrument(conn, 1, "INFY", "Information Technology")
    id1 = stores.record_recommendation(
        conn, instrument_id=1, sector="Information Technology", action="NEW",
        strategy_tag="t1", invalidation_condition="c1", fund_manager_rec_json=None,
        registry_version="v1",
    )
    id2 = stores.record_recommendation(
        conn, instrument_id=1, sector="Information Technology", action="ADD",
        strategy_tag="t1", invalidation_condition="c1", fund_manager_rec_json=None,
        registry_version="v1",
    )
    precedents = stores.get_precedents(conn, instrument_id=1, limit=5)
    assert [p["id"] for p in precedents] == [id2, id1]


def test_record_human_decision(conn):
    _seed_instrument(conn, 1, "INFY", "Information Technology")
    decision_id = stores.record_recommendation(
        conn, instrument_id=1, sector="Information Technology", action="NEW",
        strategy_tag="t1", invalidation_condition="c1", fund_manager_rec_json=None,
        registry_version="v1",
    )
    stores.record_human_decision(conn, decision_id, "APPROVE", notes="looks good")
    row = conn.execute("SELECT * FROM decision_log WHERE id = ?", (decision_id,)).fetchone()
    assert row["human_decision"] == "APPROVE"
    assert row["human_notes"] == "looks good"


def test_record_human_decision_rejects_bad_value(conn):
    _seed_instrument(conn, 1, "INFY", "Information Technology")
    decision_id = stores.record_recommendation(
        conn, instrument_id=1, sector="IT", action="NEW", strategy_tag="t1",
        invalidation_condition="c1", fund_manager_rec_json=None, registry_version="v1",
    )
    with pytest.raises(ValueError):
        stores.record_human_decision(conn, decision_id, "MAYBE")


# --- thesis_tracker -----------------------------------------------------------


def test_open_thesis_and_active_theses(conn):
    _seed_instrument(conn, 1, "INFY", "Information Technology")
    decision_id = stores.record_recommendation(
        conn, instrument_id=1, sector="IT", action="NEW", strategy_tag="t1",
        invalidation_condition="c1", fund_manager_rec_json=None, registry_version="v1",
    )
    thesis_id = stores.open_thesis(
        conn, instrument_id=1, decision_id=decision_id,
        thesis_text="Margin expansion thesis", invalidation_condition="Op margin < 20%",
    )
    theses = stores.active_theses(conn)
    assert len(theses) == 1
    assert theses[0]["id"] == thesis_id
    assert theses[0]["status"] == "ACTIVE"


def test_set_status_excludes_from_active_theses(conn):
    _seed_instrument(conn, 1, "INFY", "IT")
    decision_id = stores.record_recommendation(
        conn, instrument_id=1, sector="IT", action="NEW", strategy_tag="t1",
        invalidation_condition="c1", fund_manager_rec_json=None, registry_version="v1",
    )
    thesis_id = stores.open_thesis(
        conn, instrument_id=1, decision_id=decision_id, thesis_text="t", invalidation_condition="c",
    )
    stores.set_status(conn, thesis_id, "CLOSED")
    assert stores.active_theses(conn) == []

    stores.set_status(conn, thesis_id, "WATCH")
    theses = stores.active_theses(conn)
    assert len(theses) == 1
    assert theses[0]["status"] == "WATCH"


def test_set_status_rejects_bad_value(conn):
    _seed_instrument(conn, 1, "INFY", "IT")
    decision_id = stores.record_recommendation(
        conn, instrument_id=1, sector="IT", action="NEW", strategy_tag="t1",
        invalidation_condition="c1", fund_manager_rec_json=None, registry_version="v1",
    )
    thesis_id = stores.open_thesis(
        conn, instrument_id=1, decision_id=decision_id, thesis_text="t", invalidation_condition="c",
    )
    with pytest.raises(ValueError):
        stores.set_status(conn, thesis_id, "UNKNOWN")


# --- knowledge_base -------------------------------------------------------------


def test_add_note_and_get_notes_roundtrip(conn):
    note_id = stores.add_note(
        conn, tag_type="INSTRUMENT", tag_value="INFY", content="Q1 beat estimates", source_ref="news:123"
    )
    notes = stores.get_notes(conn, "INSTRUMENT", "INFY")
    assert len(notes) == 1
    assert notes[0]["id"] == note_id
    assert notes[0]["content"] == "Q1 beat estimates"


def test_supersede_excludes_note(conn):
    note_id = stores.add_note(conn, tag_type="SECTOR", tag_value="IT", content="old note", source_ref=None)
    stores.supersede(conn, note_id)
    assert stores.get_notes(conn, "SECTOR", "IT") == []


def test_add_note_rejects_bad_tag_type(conn):
    with pytest.raises(ValueError):
        stores.add_note(conn, tag_type="BAD", tag_value="x", content="c", source_ref=None)


def test_get_notes_most_recent_first(conn):
    id1 = stores.add_note(conn, tag_type="INSTRUMENT", tag_value="INFY", content="first", source_ref=None)
    id2 = stores.add_note(conn, tag_type="INSTRUMENT", tag_value="INFY", content="second", source_ref=None)
    notes = stores.get_notes(conn, "INSTRUMENT", "INFY")
    assert [n["id"] for n in notes] == [id2, id1]


# --- lessons ----------------------------------------------------------------


def test_propose_and_approve_lesson(conn):
    lesson_id = stores.propose_lesson(
        conn, heuristic="Avoid euphoria-tagged entries", context_tag="cycle_contrarian",
        evidence_json={"n": 3}, confidence=0.6,
    )
    # not approved yet -> not returned by approved_only=True
    assert stores.lessons_for(conn, "cycle_contrarian", approved_only=True) == []
    all_lessons = stores.lessons_for(conn, "cycle_contrarian", approved_only=False)
    assert len(all_lessons) == 1
    assert all_lessons[0]["approved_by_human"] == 0

    stores.approve_lesson(conn, lesson_id)
    approved = stores.lessons_for(conn, "cycle_contrarian", approved_only=True)
    assert len(approved) == 1
    assert approved[0]["id"] == lesson_id


# --- calibration --------------------------------------------------------------


def test_record_prediction_and_outcome(conn):
    _seed_instrument(conn, 1, "INFY", "IT")
    decision_id = stores.record_recommendation(
        conn, instrument_id=1, sector="IT", action="NEW", strategy_tag="t1",
        invalidation_condition="c1", fund_manager_rec_json=None, registry_version="v1",
    )
    cal_id = stores.record_prediction(
        conn, decision_id=decision_id, predicted_outcome="up_10pct_90d", predicted_prob=0.7
    )
    stores.record_outcome(conn, cal_id, "up_10pct_90d", realized_at="2026-10-01")
    row = conn.execute("SELECT * FROM calibration WHERE id = ?", (cal_id,)).fetchone()
    assert row["realized_outcome"] == "up_10pct_90d"
    assert row["realized_at"] == "2026-10-01"


def test_brier_score_perfect_and_worst(conn):
    _seed_instrument(conn, 1, "INFY", "IT")
    decision_id = stores.record_recommendation(
        conn, instrument_id=1, sector="IT", action="NEW", strategy_tag="t1",
        invalidation_condition="c1", fund_manager_rec_json=None, registry_version="v1",
    )
    # Perfect prediction: predicted_prob=1.0, outcome matches -> squared error 0
    cal_id1 = stores.record_prediction(conn, decision_id=decision_id, predicted_outcome="up", predicted_prob=1.0)
    stores.record_outcome(conn, cal_id1, "up", realized_at="2026-08-01")

    score = stores.brier_score(conn, "2026-01-01", "2026-12-31")
    assert score == pytest.approx(0.0)

    # Worst prediction: predicted_prob=1.0 but outcome doesn't match -> squared error 1
    cal_id2 = stores.record_prediction(conn, decision_id=decision_id, predicted_outcome="up", predicted_prob=1.0)
    stores.record_outcome(conn, cal_id2, "down", realized_at="2026-08-02")

    score2 = stores.brier_score(conn, "2026-01-01", "2026-12-31")
    assert score2 == pytest.approx(0.5)  # avg of 0.0 and 1.0


def test_brier_score_none_when_no_rows(conn):
    assert stores.brier_score(conn, "2026-01-01", "2026-12-31") is None


def test_brier_score_ignores_rows_outside_window(conn):
    _seed_instrument(conn, 1, "INFY", "IT")
    decision_id = stores.record_recommendation(
        conn, instrument_id=1, sector="IT", action="NEW", strategy_tag="t1",
        invalidation_condition="c1", fund_manager_rec_json=None, registry_version="v1",
    )
    cal_id = stores.record_prediction(conn, decision_id=decision_id, predicted_outcome="up", predicted_prob=1.0)
    stores.record_outcome(conn, cal_id, "down", realized_at="2025-01-01")  # outside window
    assert stores.brier_score(conn, "2026-01-01", "2026-12-31") is None


# --- retrieval: scoping ---------------------------------------------------------


def test_retrieval_scoping_infy_excludes_tcs(conn):
    _seed_instrument(conn, 1, "INFY", "Information Technology")
    _seed_instrument(conn, 2, "TCS", "Information Technology")

    stores.add_note(conn, tag_type="INSTRUMENT", tag_value="INFY", content="INFY-only note about margins", source_ref=None)
    stores.add_note(conn, tag_type="INSTRUMENT", tag_value="TCS", content="TCS-only note about attrition", source_ref=None)

    slices = retrieval.get_slices(conn, instrument_id=1, symbol="INFY", budget_chars=8000)
    contents = " ".join(n["content"] for n in slices["knowledge_notes"])
    assert "INFY-only" in contents
    assert "TCS-only" not in contents
    assert "TCS" not in contents


def test_retrieval_no_tags_returns_empty(conn):
    stores.add_note(conn, tag_type="SECTOR", tag_value="IT", content="some content", source_ref=None)
    slices = retrieval.get_slices(conn)
    assert slices["knowledge_notes"] == []
    assert slices["lessons"] == []
    assert slices["precedents"] == []
    assert slices["active_theses"] == []
    assert slices["approx_tokens"] == 0


def test_retrieval_sector_scoping(conn):
    _seed_instrument(conn, 1, "INFY", "Information Technology")
    stores.add_note(conn, tag_type="SECTOR", tag_value="Information Technology", content="Sector-wide IT commentary", source_ref=None)
    stores.add_note(conn, tag_type="SECTOR", tag_value="Healthcare", content="Pharma-only commentary", source_ref=None)

    slices = retrieval.get_slices(conn, sector="Information Technology", budget_chars=8000)
    contents = " ".join(n["content"] for n in slices["knowledge_notes"])
    assert "Sector-wide IT" in contents
    assert "Pharma-only" not in contents


def test_retrieval_budget_enforcement_truncates(conn):
    _seed_instrument(conn, 1, "INFY", "Information Technology")
    for i in range(20):
        stores.add_note(
            conn, tag_type="INSTRUMENT", tag_value="INFY",
            content="X" * 500, source_ref=None,
        )
    tiny_budget = 600
    slices = retrieval.get_slices(conn, instrument_id=1, symbol="INFY", budget_chars=tiny_budget)
    assert len(slices["knowledge_notes"]) < 20
    assert slices["approx_tokens"] <= tiny_budget // 4


def test_retrieval_precedents_and_theses_included(conn):
    _seed_instrument(conn, 1, "INFY", "Information Technology")
    decision_id = stores.record_recommendation(
        conn, instrument_id=1, sector="Information Technology", action="NEW",
        strategy_tag="t1", invalidation_condition="c1", fund_manager_rec_json=None,
        registry_version="v1",
    )
    stores.open_thesis(conn, instrument_id=1, decision_id=decision_id, thesis_text="t", invalidation_condition="c")

    slices = retrieval.get_slices(conn, instrument_id=1, symbol="INFY", budget_chars=8000)
    assert len(slices["precedents"]) == 1
    assert len(slices["active_theses"]) == 1
