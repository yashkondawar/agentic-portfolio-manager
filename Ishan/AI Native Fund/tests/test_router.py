"""Offline tests for afund.orchestrator.router — trigger -> pipeline map shape."""
from __future__ import annotations

import pytest

from afund.orchestrator.router import TRIGGERS, show_pipeline


def test_all_expected_triggers_present():
    expected = {
        "daily_data",
        "daily_news_process",
        "weekly_idea_cycle",
        "position_monitoring",
        "monthly_newsletter_digest",
        "meta_research_cycle",
    }
    assert expected.issubset(set(TRIGGERS.keys()))


def test_weekly_idea_cycle_ends_with_human():
    steps = show_pipeline("weekly_idea_cycle")
    assert steps[-1] == "HUMAN"


def test_weekly_idea_cycle_critique_precedes_risk_precedes_allocator():
    steps = show_pipeline("weekly_idea_cycle")
    critique_idx = steps.index("agent:critique")
    risk_idx = steps.index("agent:risk_mgmt")
    allocator_idx = steps.index("agent:allocator")
    assert critique_idx < risk_idx < allocator_idx


def test_weekly_idea_cycle_idea_gen_before_synthesis_before_critique():
    steps = show_pipeline("weekly_idea_cycle")
    assert steps.index("agent:idea_gen") < steps.index("agent:synthesis") < steps.index("agent:critique")


def test_weekly_idea_cycle_fund_manager_before_human():
    steps = show_pipeline("weekly_idea_cycle")
    assert steps.index("agent:fund_manager") < steps.index("HUMAN")


def test_position_monitoring_ends_with_human():
    steps = show_pipeline("position_monitoring")
    assert steps[-1] == "HUMAN"


def test_meta_research_cycle_ends_with_human():
    steps = show_pipeline("meta_research_cycle")
    assert steps[-1] == "HUMAN"


def test_daily_data_has_only_py_steps():
    steps = show_pipeline("daily_data")
    assert all(step.startswith("py:") for step in steps)


def test_show_pipeline_unknown_trigger_raises():
    with pytest.raises(KeyError):
        show_pipeline("not_a_real_trigger")


def test_monthly_newsletter_digest_fetch_before_macro_digest():
    steps = show_pipeline("monthly_newsletter_digest")
    assert steps[0].startswith("py:")
    assert steps[-1] == "agent:macro_digest"
