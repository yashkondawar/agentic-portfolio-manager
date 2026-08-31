"""Offline tests for afund.orchestrator.escalation — pure rules, no I/O beyond
the one-time risk_limits.yaml read."""
from __future__ import annotations

from afund.orchestrator.escalation import requires_human


def test_exit_requires_human():
    assert requires_human({"type": "recommendation", "action": "EXIT"}) is True


def test_new_add_reduce_require_human():
    for action in ("NEW", "ADD", "REDUCE"):
        assert requires_human({"type": "recommendation", "action": action}) is True


def test_hold_and_monitor_only_do_not_require_human_by_default():
    assert requires_human({"type": "recommendation", "action": "HOLD"}) is False
    assert requires_human({"type": "recommendation", "action": "MONITOR_ONLY"}) is False


def test_thesis_invalidated_requires_human():
    assert requires_human({"type": "thesis_status", "thesis_status": "INVALIDATED"}) is True


def test_thesis_watch_breach_requires_human():
    assert requires_human({"type": "thesis_status", "thesis_status": "WATCH"}) is True


def test_thesis_active_does_not_require_human():
    assert requires_human({"type": "thesis_status", "thesis_status": "ACTIVE"}) is False


def test_risk_violation_requires_human():
    assert requires_human({"type": "risk_violation", "risk_violation": True}) is True


def test_risk_violation_false_does_not_require_human():
    assert requires_human({"type": "risk_violation", "risk_violation": False}) is False


def test_empty_event_does_not_require_human():
    assert requires_human({}) is False


def test_unrecognized_action_does_not_require_human():
    assert requires_human({"action": "SOME_UNKNOWN_ACTION"}) is False
