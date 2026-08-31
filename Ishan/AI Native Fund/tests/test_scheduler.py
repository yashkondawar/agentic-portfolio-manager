"""Offline tests for afund.orchestrator.scheduler — due-job logic against
config/settings.yaml's real cadences dict."""
from __future__ import annotations

import datetime as dt

from afund.orchestrator import scheduler


def test_daily_jobs_always_due():
    on_date = dt.date(2026, 7, 8)  # a Wednesday
    due = scheduler.due_jobs(on_date)
    assert "daily_news" in due
    assert "daily_prices" in due
    assert "daily_mf_navs" in due
    assert "daily_nav" in due


def test_weekly_idea_cycle_due_on_monday_only():
    monday = dt.date(2026, 7, 6)
    tuesday = dt.date(2026, 7, 7)
    assert "weekly_idea_cycle" in scheduler.due_jobs(monday)
    assert "weekly_idea_cycle" not in scheduler.due_jobs(tuesday)


def test_monthly_newsletters_due_on_configured_day():
    # cadences.monthly_newsletters = "monthly 6"
    due_day = dt.date(2026, 7, 6)
    not_due_day = dt.date(2026, 7, 7)
    assert "monthly_newsletters" in scheduler.due_jobs(due_day)
    assert "monthly_newsletters" not in scheduler.due_jobs(not_due_day)


def test_quarterly_due_within_first_5_days_of_quarter_start_month():
    for d in (dt.date(2026, 7, 1), dt.date(2026, 7, 5), dt.date(2026, 4, 3), dt.date(2026, 1, 5), dt.date(2026, 10, 2)):
        due = scheduler.due_jobs(d)
        assert "quarterly_financials" in due, f"expected due on {d}"
        assert "quarterly_macro" in due, f"expected due on {d}"


def test_quarterly_not_due_outside_window():
    for d in (dt.date(2026, 7, 6), dt.date(2026, 6, 30), dt.date(2026, 5, 1), dt.date(2026, 8, 1)):
        due = scheduler.due_jobs(d)
        assert "quarterly_financials" not in due, f"expected not due on {d}"
        assert "quarterly_macro" not in due, f"expected not due on {d}"


def test_last_run_suppresses_already_run_weekly_job():
    monday = dt.date(2026, 7, 6)
    # Already ran earlier that same Monday.
    last_run = {"weekly_idea_cycle": "2026-07-06"}
    due = scheduler.due_jobs(monday, last_run=last_run)
    assert "weekly_idea_cycle" not in due


def test_last_run_from_prior_week_does_not_suppress():
    monday = dt.date(2026, 7, 6)
    last_run = {"weekly_idea_cycle": "2026-06-29"}  # prior Monday, prior window
    due = scheduler.due_jobs(monday, last_run=last_run)
    assert "weekly_idea_cycle" in due


def test_last_run_does_not_suppress_daily_jobs():
    on_date = dt.date(2026, 7, 8)
    last_run = {"daily_news": on_date.isoformat()}
    due = scheduler.due_jobs(on_date, last_run=last_run)
    assert "daily_news" in due


def test_last_run_suppresses_quarterly_within_same_quarter_window():
    on_date = dt.date(2026, 7, 3)
    last_run = {"quarterly_financials": "2026-07-01"}
    due = scheduler.due_jobs(on_date, last_run=last_run)
    assert "quarterly_financials" not in due


def test_last_run_from_prior_quarter_does_not_suppress():
    on_date = dt.date(2026, 7, 3)
    last_run = {"quarterly_financials": "2026-04-02"}  # prior quarter's window
    due = scheduler.due_jobs(on_date, last_run=last_run)
    assert "quarterly_financials" in due
