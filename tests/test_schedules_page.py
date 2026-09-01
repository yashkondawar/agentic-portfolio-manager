"""The schedules page renders and round-trips a new schedule.

These go through Streamlit's own test runner because the failures worth
catching here are Streamlit API misuses (nested expanders, duplicate widget
keys, forms without submit buttons) that a plain import can never surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import schedules

APP = Path(__file__).parent / "apps" / "schedules_app.py"

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "portfolio.sqlite3"))
    return AppTest.from_file(str(APP), default_timeout=120).run()


def test_page_renders_the_seeded_schedules(app):
    assert not app.exception
    headings = [item.value for item in app.subheader]
    assert "Configured schedules" in headings
    assert "Add or edit a schedule" in headings
    # One card per seeded default, each with its own run button and toggle.
    assert len([b for b in app.button if b.label == "Run now"]) == len(
        schedules.DEFAULT_SCHEDULES
    )
    assert [m.label for m in app.metric][0] == "Background scheduler"


def test_a_new_schedule_can_be_created_from_the_form(app):
    before = {item.id for item in schedules.list_schedules()}

    app.selectbox(key="sched_strategy_new").set_value("qtr_results").run()
    app.text_input(key="sched_form_new_qtr_results_name").set_value("Probe job").run()
    next(b for b in app.button if b.label == "Save schedule").click().run()

    assert not app.exception
    created = [
        item for item in schedules.list_schedules() if item.id not in before
    ]
    assert len(created) == 1
    assert created[0].name == "Probe job"
    assert created[0].strategy_id == "qtr_results"
    # Strategy defaults are baked in, so the daemon runs it the same way the UI would.
    assert created[0].params
