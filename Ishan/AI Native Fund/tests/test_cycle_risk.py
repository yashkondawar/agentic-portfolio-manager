"""Offline tests for Phase 10 cycle-aware risk:
  - afund.portfolio.risk.cycle_adjusted_limit
  - afund.orchestrator.escalation.mechanical_checklist
  - afund.orchestrator.escalation.requires_human's new `checklist` parameter

All synthetic data seeded into a temp SQLite DB built from schema.sql. No
network, no LLM calls. cycle_adjusted_limit reads the REAL registry (registry/
rules/risk_limits.yaml via Registry.load()) rather than a monkeypatched one,
per the repo's "Registry is the governed source of truth" rule -- so these
goldens use the actual committed max_single_position_pct (10.0) and
phase_multipliers values, and would need updating if those change.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from afund.orchestrator import escalation
from afund.portfolio import risk

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


def _insert_instrument(conn, instrument_id, symbol, sector=None):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, sector, active) VALUES (?, ?, 'STOCK', ?, 1)",
        (instrument_id, symbol, sector),
    )


def _insert_cycle_assessment(conn, *, scope, as_of_date, phase_id, directional_lean,
                              percentile=None, data_pending=0):
    conn.execute(
        """
        INSERT INTO cycle_assessments
            (cycle_id, scope, as_of_date, framework_version, phase_id, directional_lean,
             percentile, data_pending, created_at)
        VALUES ('valuation_cycle', ?, ?, 'test-fw-v1', ?, ?, ?, ?, ?)
        """,
        (scope, as_of_date, phase_id, directional_lean, percentile, data_pending,
         dt.datetime.now().isoformat()),
    )


def _insert_decision_log(conn, instrument_id, action="NEW"):
    conn.execute(
        """
        INSERT INTO decision_log (decision_date, instrument_id, action, human_decision, created_at)
        VALUES ('2026-01-01', ?, ?, 'APPROVE', '2026-01-01T00:00:00')
        """,
        (instrument_id, action),
    )


# ---------------------------------------------------------------------------
# cycle_adjusted_limit
# ---------------------------------------------------------------------------

def test_cycle_adjusted_limit_deep_value_multiplier(conn):
    _insert_instrument(conn, 1, "TESTCO", sector="Information Technology")
    _insert_cycle_assessment(conn, scope="it_technology", as_of_date="2026-07-01",
                              phase_id="deep_value", directional_lean=1)
    conn.commit()

    result = risk.cycle_adjusted_limit(conn, instrument_id=1)
    assert result["unknown_phase"] is False
    assert result["phase_id"] == "deep_value"
    assert result["multiplier"] == pytest.approx(1.2)
    assert result["base_limit_pct"] == pytest.approx(10.0)
    assert result["adjusted_limit_pct"] == pytest.approx(12.0)


def test_cycle_adjusted_limit_euphoria_multiplier_tightens(conn):
    _insert_instrument(conn, 1, "TESTCO", sector="Financial Services")
    _insert_cycle_assessment(conn, scope="bfsi", as_of_date="2026-07-01",
                              phase_id="euphoria", directional_lean=-1)
    conn.commit()

    result = risk.cycle_adjusted_limit(conn, instrument_id=1)
    assert result["multiplier"] == pytest.approx(0.5)
    assert result["adjusted_limit_pct"] == pytest.approx(5.0)


def test_cycle_adjusted_limit_unknown_phase_defaults_to_1x(conn):
    # No cycle_assessments rows at all -> unknown_phase, multiplier 1.0.
    _insert_instrument(conn, 1, "TESTCO", sector="Information Technology")
    conn.commit()

    result = risk.cycle_adjusted_limit(conn, instrument_id=1)
    assert result["unknown_phase"] is True
    assert result["multiplier"] == pytest.approx(1.0)
    assert result["adjusted_limit_pct"] == result["base_limit_pct"]


def test_cycle_adjusted_limit_falls_back_to_nifty_500(conn):
    _insert_instrument(conn, 1, "TESTCO", sector="Healthcare")  # -> pharma_chemicals, no data
    _insert_cycle_assessment(conn, scope="NIFTY 500", as_of_date="2026-07-01",
                              phase_id="momentum", directional_lean=1)
    conn.commit()

    result = risk.cycle_adjusted_limit(conn, instrument_id=1)
    assert result["scope_used"] == "NIFTY 500"
    assert result["multiplier"] == pytest.approx(1.0)  # momentum -> 1.0


def test_cycle_adjusted_limit_custom_base_limit(conn):
    _insert_instrument(conn, 1, "TESTCO", sector="Information Technology")
    _insert_cycle_assessment(conn, scope="it_technology", as_of_date="2026-07-01",
                              phase_id="deep_value", directional_lean=1)
    conn.commit()

    result = risk.cycle_adjusted_limit(conn, instrument_id=1, base_limit_pct=20.0)
    assert result["base_limit_pct"] == pytest.approx(20.0)
    assert result["adjusted_limit_pct"] == pytest.approx(24.0)  # 20 * 1.2


def test_cycle_adjusted_limit_explicit_sector_string_overrides_instrument(conn):
    _insert_instrument(conn, 1, "TESTCO", sector="Information Technology")
    _insert_cycle_assessment(conn, scope="bfsi", as_of_date="2026-07-01",
                              phase_id="euphoria", directional_lean=-1)
    conn.commit()

    # sector= explicitly passed should win over instrument_id's own sector.
    result = risk.cycle_adjusted_limit(conn, instrument_id=1, sector="Financial Services")
    assert result["scope_used"] == "bfsi"
    assert result["multiplier"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# mechanical_checklist
# ---------------------------------------------------------------------------

def test_checklist_size_vs_limit_pass_and_fail(conn):
    _insert_instrument(conn, 1, "TESTCO", sector="Information Technology")
    _insert_cycle_assessment(conn, scope="it_technology", as_of_date="2026-07-01",
                              phase_id="deep_value", directional_lean=1)
    conn.commit()
    # adjusted_limit_pct = 10.0 * 1.2 = 12.0

    passing = escalation.mechanical_checklist(conn, {"instrument_id": 1, "size_or_weight_pct": 8.0})
    assert passing["size_vs_cycle_adjusted_limit"] == "PASS"

    failing = escalation.mechanical_checklist(conn, {"instrument_id": 1, "size_or_weight_pct": 15.0})
    assert failing["size_vs_cycle_adjusted_limit"] == "FAIL"


def test_checklist_size_na_when_no_size_given(conn):
    _insert_instrument(conn, 1, "TESTCO", sector="Information Technology")
    conn.commit()
    result = escalation.mechanical_checklist(conn, {"instrument_id": 1})
    assert result["size_vs_cycle_adjusted_limit"] == "NA"


def test_checklist_cash_floor_and_sector_cap_na_without_inputs(conn):
    result = escalation.mechanical_checklist(conn, {"instrument_id": None})
    assert result["cash_floor"] == "NA"
    assert result["sector_cap"] == "NA"


def test_checklist_cash_floor_pass_and_fail(conn):
    passing = escalation.mechanical_checklist(conn, {"resulting_cash_pct": 10.0})
    assert passing["cash_floor"] == "PASS"  # >= default floor 5%
    failing = escalation.mechanical_checklist(conn, {"resulting_cash_pct": 2.0})
    assert failing["cash_floor"] == "FAIL"


def test_checklist_sector_cap_pass_and_fail(conn):
    passing = escalation.mechanical_checklist(conn, {"sector_weight_pct_after": 20.0})
    assert passing["sector_cap"] == "PASS"  # <= default 25%
    failing = escalation.mechanical_checklist(conn, {"sector_weight_pct_after": 30.0})
    assert failing["sector_cap"] == "FAIL"


def test_checklist_alignment_vs_size_fails_only_when_both_low_and_large(conn):
    _insert_instrument(conn, 1, "TESTCO", sector="Information Technology")
    _insert_cycle_assessment(conn, scope="it_technology", as_of_date="2026-07-01",
                              phase_id="deep_value", directional_lean=1)
    conn.commit()
    # adjusted limit = 12.0, half_limit = 6.0

    # Low alignment (<40) + large size (>= 6.0) -> FAIL
    result = escalation.mechanical_checklist(
        conn, {"instrument_id": 1, "alignment_score": 20, "size_or_weight_pct": 8.0}
    )
    assert result["alignment_vs_size"] == "FAIL"

    # Low alignment but small size -> PASS
    result = escalation.mechanical_checklist(
        conn, {"instrument_id": 1, "alignment_score": 20, "size_or_weight_pct": 2.0}
    )
    assert result["alignment_vs_size"] == "PASS"

    # High alignment + large size -> PASS
    result = escalation.mechanical_checklist(
        conn, {"instrument_id": 1, "alignment_score": 80, "size_or_weight_pct": 8.0}
    )
    assert result["alignment_vs_size"] == "PASS"


def test_checklist_alignment_vs_size_na_without_inputs(conn):
    result = escalation.mechanical_checklist(conn, {"instrument_id": None})
    assert result["alignment_vs_size"] == "NA"


def test_checklist_first_time_exposure_fails_for_new_instrument_on_capital_action(conn):
    _insert_instrument(conn, 1, "TESTCO")
    conn.commit()
    result = escalation.mechanical_checklist(conn, {"instrument_id": 1, "action": "NEW"})
    assert result["first_time_exposure"] == "FAIL"


def test_checklist_first_time_exposure_passes_when_prior_decision_exists(conn):
    _insert_instrument(conn, 1, "TESTCO")
    _insert_decision_log(conn, 1, action="ADD")
    conn.commit()
    result = escalation.mechanical_checklist(conn, {"instrument_id": 1, "action": "ADD"})
    assert result["first_time_exposure"] == "PASS"


def test_checklist_first_time_exposure_na_for_hold_action(conn):
    # HOLD/MONITOR_ONLY don't initiate exposure -- NA regardless of history.
    _insert_instrument(conn, 1, "TESTCO")
    conn.commit()
    result = escalation.mechanical_checklist(conn, {"instrument_id": 1, "action": "HOLD"})
    assert result["first_time_exposure"] == "NA"


def test_checklist_first_time_exposure_na_when_no_action_given(conn):
    # risk_mgmt-stage packets don't know the action yet -- NA, not FAIL.
    _insert_instrument(conn, 1, "TESTCO")
    conn.commit()
    result = escalation.mechanical_checklist(conn, {"instrument_id": 1})
    assert result["first_time_exposure"] == "NA"


def test_checklist_anchor_extreme_fails_beyond_tail_percentile(conn):
    _insert_instrument(conn, 1, "TESTCO", sector="Information Technology")
    _insert_cycle_assessment(conn, scope="it_technology", as_of_date="2026-07-01",
                              phase_id="euphoria", directional_lean=-1, percentile=99.9)
    conn.commit()
    result = escalation.mechanical_checklist(conn, {"instrument_id": 1})
    assert result["anchor_extreme"] == "FAIL"


def test_checklist_anchor_extreme_passes_within_normal_range(conn):
    _insert_instrument(conn, 1, "TESTCO", sector="Information Technology")
    _insert_cycle_assessment(conn, scope="it_technology", as_of_date="2026-07-01",
                              phase_id="deep_value", directional_lean=1, percentile=15.0)
    conn.commit()
    result = escalation.mechanical_checklist(conn, {"instrument_id": 1})
    assert result["anchor_extreme"] == "PASS"


def test_checklist_anchor_extreme_na_when_no_assessment(conn):
    result = escalation.mechanical_checklist(conn, {"instrument_id": None})
    assert result["anchor_extreme"] == "NA"


def test_checklist_every_item_always_present(conn):
    # Empty event -> every item still PASS/FAIL/NA, never omitted.
    result = escalation.mechanical_checklist(conn, {})
    expected_keys = {
        "size_vs_cycle_adjusted_limit", "cash_floor", "sector_cap",
        "alignment_vs_size", "first_time_exposure", "anchor_extreme",
    }
    assert set(result) == expected_keys
    assert all(v in ("PASS", "FAIL", "NA") for v in result.values())


# ---------------------------------------------------------------------------
# requires_human's checklist parameter (rule 5)
# ---------------------------------------------------------------------------

def test_requires_human_true_on_checklist_fail_even_for_light_review_action():
    event = {"action": "HOLD"}  # HOLD alone would NOT escalate
    checklist = {"anchor_extreme": "FAIL", "cash_floor": "PASS"}
    assert escalation.requires_human(event, checklist=checklist) is True


def test_requires_human_false_when_checklist_all_pass_or_na():
    event = {"action": "HOLD"}
    checklist = {"anchor_extreme": "PASS", "cash_floor": "NA"}
    assert escalation.requires_human(event, checklist=checklist) is False


def test_requires_human_backward_compatible_with_no_checklist_arg():
    # Every pre-Phase-10 caller omits `checklist` entirely -- must behave
    # exactly as before (pure event-dict rules only).
    assert escalation.requires_human({"action": "HOLD"}) is False
    assert escalation.requires_human({"action": "NEW"}) is True


def test_requires_human_true_for_new_action_regardless_of_checklist():
    # Rule 1 (hard-escalate action) already fires; checklist=None must not
    # matter here.
    assert escalation.requires_human({"action": "NEW"}, checklist=None) is True
