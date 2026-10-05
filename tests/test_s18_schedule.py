import pytest

from core import schedules, storage
from backtesting.s18 import schedule


def test_prepared_schedule_is_disabled_idempotent_and_keeps_other_jobs(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "scheduler.sqlite3"))
    monkeypatch.setattr(schedule, "get_dataset", lambda: object())
    existing = schedules.create_schedule(strategy_id="gfs_live", run_at="17:30")
    first = schedule.prepare_schedule(capital=500000)
    repeated = schedule.prepare_schedule(capital=500000)
    assert first.id == repeated.id
    assert not repeated.enabled
    assert repeated.run_at == "19:00"
    assert repeated.days_of_week == schedules.ALL_DAYS
    assert repeated.timezone == "Asia/Kolkata"
    assert repeated.params["capital"] == 500000
    assert not {"kit_path", "forward_path", "data_source"} & repeated.params.keys()
    assert "as_of" not in repeated.params
    assert schedules.get_schedule(existing.id).enabled
    assert (
        storage.get_document("strategy_defaults", "s18_daily")["book_id"]
        == "s18-p15-forward"
    )
    schedules.set_enabled(repeated.id, True)
    with pytest.raises(ValueError, match="active"):
        schedule.prepare_schedule(capital=500000)
