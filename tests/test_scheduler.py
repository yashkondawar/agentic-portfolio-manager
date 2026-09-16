"""Schedule arithmetic, claim semantics and daemon firing."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from core import scheduler, schedules
from core.run_history import list_runs
from core.strategy import StrategyResult

IST = schedules._zone(schedules.DEFAULT_TIMEZONE)

# 2026-08-26 is a Wednesday; 2026-08-30 is a Sunday.
WEDNESDAY = datetime(2026, 8, 26, tzinfo=IST)
SUNDAY = datetime(2026, 8, 30, tzinfo=IST)


def _at(day: datetime, hour: int, minute: int = 0) -> datetime:
    return day.replace(hour=hour, minute=minute)


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "portfolio.sqlite3"


def _weekday_schedule(db, **overrides):
    options = {
        "strategy_id": "gfs_live",
        "run_at": "17:30",
        "name": "GFS",
        "days_of_week": schedules.WEEKDAYS,
        "db_path": db,
    }
    options.update(overrides)
    return schedules.create_schedule(**options)


def test_schedule_is_due_only_after_its_time(db):
    schedule = _weekday_schedule(db)
    assert schedule.is_due(_at(WEDNESDAY, 17, 0)) is False
    assert schedule.is_due(_at(WEDNESDAY, 17, 30)) is True
    assert schedule.is_due(_at(WEDNESDAY, 23, 0)) is True


def test_missed_occurrence_fires_inside_the_catch_up_window(db):
    schedule = _weekday_schedule(db, catch_up_minutes=720)
    # Machine was asleep; booted the next morning, still inside 12 hours.
    assert schedule.is_due(_at(WEDNESDAY + timedelta(days=1), 5, 0)) is True


def test_missed_occurrence_is_abandoned_outside_the_catch_up_window(db):
    schedule = _weekday_schedule(db, catch_up_minutes=60)
    assert schedule.is_due(_at(WEDNESDAY + timedelta(days=1), 5, 0)) is False


def test_weekday_schedule_does_not_fire_on_the_weekend(db):
    schedule = _weekday_schedule(db)
    assert schedule.is_due(_at(SUNDAY, 18, 0)) is False
    following = schedule.next_occurrence(_at(SUNDAY, 18, 0))
    assert following.weekday() == 0  # Monday


def test_disabled_schedules_never_come_due(db):
    schedule = _weekday_schedule(db, enabled=False)
    assert schedule.is_due(_at(WEDNESDAY, 18, 0)) is False


def test_claiming_an_occurrence_is_single_shot(db):
    schedule = _weekday_schedule(db)
    key = schedules.occurrence_key(schedule.due_occurrence(_at(WEDNESDAY, 18, 0)))
    assert schedules.claim_occurrence(schedule.id, key, db_path=db) is True
    assert schedules.claim_occurrence(schedule.id, key, db_path=db) is False
    reloaded = schedules.get_schedule(schedule.id, db_path=db)
    assert reloaded.is_due(_at(WEDNESDAY, 18, 0)) is False
    # The next day is a separate occurrence and must still fire.
    assert reloaded.is_due(_at(WEDNESDAY + timedelta(days=1), 18, 0)) is True


def test_time_and_day_inputs_are_validated(db):
    with pytest.raises(schedules.ScheduleError):
        schedules.create_schedule(strategy_id="gfs_live", run_at="25:00", db_path=db)
    with pytest.raises(schedules.ScheduleError):
        schedules.create_schedule(
            strategy_id="gfs_live", run_at="17:30", days_of_week=[], db_path=db
        )
    compact = schedules.create_schedule(
        strategy_id="gfs_live", run_at="0815", db_path=db
    )
    assert compact.run_at == "08:15"


def test_defaults_are_seeded_once(db):
    first = schedules.ensure_defaults(db_path=db)
    assert {item.strategy_id for item in first} == {
        "gfs_live",
        "qtr_results",
        "breakout_ath_daily",
    }
    schedules.delete_schedule(first[0].id, db_path=db)
    second = schedules.ensure_defaults(db_path=db)
    assert len(second) == len(first) - 1  # never re-seeds over a user's edits


def test_fire_due_runs_persists_and_does_not_repeat(db, monkeypatch):
    calls: list[dict] = []

    def fake_run(strategy_id, params=None):
        calls.append({"strategy_id": strategy_id, "params": params})
        return StrategyResult(
            strategy_id=strategy_id,
            status="completed",
            report="done",
            data={"orders": []},
        )

    monkeypatch.setattr(scheduler.registry, "run_strategy", fake_run)
    schedule = _weekday_schedule(db, params={"universe_index": "nifty200"})
    now = _at(WEDNESDAY, 18, 0)

    fired = scheduler.fire_due(now, db_path=db)
    assert [item[0].id for item in fired] == [schedule.id]
    assert calls == [
        {"strategy_id": "gfs_live", "params": {"universe_index": "nifty200"}}
    ]

    # The report is in the database, which is what the UI reads at market open.
    rows = list_runs(strategy_id="gfs_live", db_path=db)
    assert len(rows) == 1 and rows[0]["status"] == "completed"

    stored = schedules.get_schedule(schedule.id, db_path=db)
    assert stored.last_status == "completed"
    assert stored.last_run_id == rows[0]["id"]

    # A second poll in the same window must not run it again.
    assert scheduler.fire_due(now + timedelta(minutes=1), db_path=db) == []
    assert len(calls) == 1


def test_failed_runs_are_recorded_rather_than_raised(db, monkeypatch):
    monkeypatch.setattr(
        scheduler.registry,
        "run_strategy",
        lambda strategy_id, params=None: StrategyResult(
            strategy_id=strategy_id,
            status="failed",
            report="boom",
            error="network down",
        ),
    )
    schedule = _weekday_schedule(db)
    scheduler.fire_due(_at(WEDNESDAY, 18, 0), db_path=db)

    stored = schedules.get_schedule(schedule.id, db_path=db)
    assert stored.last_status == "failed"
    assert stored.last_error == "network down"


def test_heartbeat_reports_a_recent_age(db):
    scheduler.write_heartbeat(db_path=db, poll_seconds=30)
    age = scheduler.heartbeat_age_seconds(db_path=db)
    assert age is not None and age < 60


def test_serve_polls_a_bounded_number_of_times(db, monkeypatch):
    monkeypatch.setattr(
        scheduler.registry,
        "run_strategy",
        lambda strategy_id, params=None: StrategyResult(
            strategy_id=strategy_id, status="completed", report=""
        ),
    )
    monkeypatch.setattr(scheduler.time, "sleep", lambda _seconds: None)
    assert scheduler.serve(poll_seconds=1, max_cycles=2, db_path=db) == 0
    assert scheduler.heartbeat_age_seconds(db_path=db) is not None


def test_default_schedules_land_after_the_nse_close():
    """The defaults exist to be read before the *next* open, never during."""
    by_strategy = {spec["strategy_id"]: spec for spec in schedules.DEFAULT_SCHEDULES}
    gfs_hour = int(by_strategy["gfs_live"]["run_at"].split(":")[0])
    assert gfs_hour >= 16  # NSE closes 15:30 IST; bars publish around 16:00
    assert all(spec["why"] for spec in schedules.DEFAULT_SCHEDULES)


def test_the_ath_sleeve_runs_once_a_day_after_the_close():
    """Close-based rules have one decision point, so one weekday run.

    Firing it intraday would test a closing breakout and a closing stop
    against a price that is not the close yet, which is a different strategy
    from the one that was backtested.
    """
    ath = [
        spec
        for spec in schedules.DEFAULT_SCHEDULES
        if spec["strategy_id"] == "breakout_ath_daily"
    ]
    assert len(ath) == 1
    spec = ath[0]
    hour, minute = (int(part) for part in spec["run_at"].split(":"))
    assert (hour, minute) > (15, 30)  # never during the session
    assert hour >= 16  # and after the exchange candle has published
    assert tuple(spec["days_of_week"]) == schedules.WEEKDAYS


def test_timezone_resolution_survives_a_missing_tz_database(monkeypatch):
    def explode(_name):
        raise KeyError("no tzdata")

    monkeypatch.setattr(schedules, "ZoneInfo", explode)
    zone = schedules._zone(schedules.DEFAULT_TIMEZONE)
    assert datetime(2026, 8, 26, tzinfo=zone).utcoffset() == timedelta(
        hours=5, minutes=30
    )
    assert schedules._zone("Nowhere/Nothing") is timezone.utc


def test_ui_falls_back_to_the_last_saved_run(tmp_path, monkeypatch):
    """A scheduled run happens with no browser open, so session state is empty."""
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "ui.sqlite3"))
    from core.run_history import save_run
    from ui import components

    assert components.latest_result("gfs_live") is None

    save_run(
        StrategyResult(
            strategy_id="gfs_live",
            status="completed",
            report="overnight report",
            data={"orders": [{"symbol": "TCS"}]},
        ),
        {"universe_index": "nifty200"},
        duration_ms=10,
    )

    recovered = components.latest_result("gfs_live")
    assert recovered is not None
    assert recovered.report == "overnight report"
    assert recovered.data["orders"][0]["symbol"] == "TCS"
    assert components.latest_result("gfs_live", from_history=False) is None


def test_bootstrap_script_survives_a_console_less_interpreter(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "runtime_dir", lambda: tmp_path)
    script = scheduler.write_bootstrap("scheduler_probe.py", ["once"])
    body = script.read_text(encoding="utf-8")

    # pythonw.exe leaves sys.stdout/sys.stderr as None, so the generated script
    # has to redirect them before anything imports logging_config.
    assert "sys.stdout = _stream" in body
    assert "sys.stderr = _stream" in body
    assert str(scheduler.REPO_ROOT) in body
    assert "main(['once'])" in body


def test_supervisor_restarts_the_daemon_until_it_gives_up(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduler, "runtime_dir", lambda: tmp_path)
    calls = []

    class _Exited:
        returncode = 3

    def fake_run(command, **kwargs):
        calls.append(command)
        return _Exited()

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: None)

    code = scheduler.supervise(poll_seconds=7, backoff_seconds=0, max_restarts=3)

    assert code == 3
    assert len(calls) == 3
    assert calls[0][1:] == ["-m", "core.scheduler", "serve", "--poll", "7"]


def test_install_falls_back_to_a_startup_entry_when_tasks_are_denied(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(scheduler.os, "name", "nt")
    monkeypatch.setattr(scheduler, "runtime_dir", lambda: tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(scheduler, "_create_task", lambda *a, **k: 1)

    assert scheduler.install_task() == 0

    entry = scheduler.startup_entry_path()
    assert entry.exists()
    assert "scheduler_supervise.py" in entry.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Source-change detection
#
# A long-lived daemon imports strategies once. Without these, adding a strategy
# leaves every running daemon failing "Unknown strategy" until a human restarts
# it by hand -- which is exactly the bug this guards against.
# ---------------------------------------------------------------------------
def _tree(root, package="strategies"):
    directory = root / package
    directory.mkdir(parents=True, exist_ok=True)
    module = directory / "alpha.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    return module


def test_fingerprint_changes_when_a_strategy_is_edited(tmp_path):
    module = _tree(tmp_path)
    before = scheduler.code_fingerprint(tmp_path)
    import os

    stamp = module.stat().st_mtime + 10
    module.write_text("VALUE = 2\n", encoding="utf-8")
    os.utime(module, (stamp, stamp))
    assert scheduler.code_fingerprint(tmp_path) != before


def test_fingerprint_changes_when_a_strategy_is_added(tmp_path):
    _tree(tmp_path)
    before = scheduler.code_fingerprint(tmp_path)
    (tmp_path / "strategies" / "beta.py").write_text("VALUE = 3\n", encoding="utf-8")
    assert scheduler.code_fingerprint(tmp_path) != before


def test_fingerprint_changes_when_a_strategy_is_deleted(tmp_path):
    module = _tree(tmp_path)
    (tmp_path / "strategies" / "beta.py").write_text("VALUE = 3\n", encoding="utf-8")
    before = scheduler.code_fingerprint(tmp_path)
    module.unlink()
    assert scheduler.code_fingerprint(tmp_path) != before


def test_fingerprint_ignores_bytecode_caches(tmp_path):
    """Otherwise every run would rewrite .pyc files and trigger a restart loop."""
    _tree(tmp_path)
    before = scheduler.code_fingerprint(tmp_path)
    cache = tmp_path / "strategies" / "__pycache__"
    cache.mkdir()
    (cache / "alpha.cpython-312.py").write_text("x\n", encoding="utf-8")
    assert scheduler.code_fingerprint(tmp_path) == before


def test_fingerprint_ignores_unwatched_directories(tmp_path):
    """Editing the UI cannot change a scheduled outcome, so it must not restart."""
    _tree(tmp_path)
    before = scheduler.code_fingerprint(tmp_path)
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "pages.py").write_text("x\n", encoding="utf-8")
    assert scheduler.code_fingerprint(tmp_path) == before


def test_serve_exits_with_reload_code_when_source_changes(db, monkeypatch):
    monkeypatch.setattr(scheduler, "fire_due", lambda **kwargs: [])
    monkeypatch.setattr(scheduler, "write_heartbeat", lambda **kwargs: None)
    seen = iter(["1:100", "2:200"])
    monkeypatch.setattr(scheduler, "code_fingerprint", lambda *a: next(seen))
    assert scheduler.serve(max_cycles=5, db_path=db) == scheduler.RELOAD_EXIT_CODE


def test_serve_stays_put_when_source_is_unchanged(db, monkeypatch):
    monkeypatch.setattr(scheduler, "fire_due", lambda **kwargs: [])
    monkeypatch.setattr(scheduler, "write_heartbeat", lambda **kwargs: None)
    monkeypatch.setattr(scheduler, "code_fingerprint", lambda *a: "1:100")
    assert scheduler.serve(max_cycles=2, db_path=db) == 0


def test_serve_honours_the_no_auto_reload_escape_hatch(db, monkeypatch):
    monkeypatch.setattr(scheduler, "fire_due", lambda **kwargs: [])
    monkeypatch.setattr(scheduler, "write_heartbeat", lambda **kwargs: None)
    calls = []

    def _fingerprint(*args):
        calls.append(args)
        return f"{len(calls)}:0"

    monkeypatch.setattr(scheduler, "code_fingerprint", _fingerprint)
    assert scheduler.serve(max_cycles=2, db_path=db, auto_reload=False) == 0
    assert calls == []


def _supervise_once(monkeypatch, tmp_path, returncode):
    import subprocess as _subprocess

    slept = []
    monkeypatch.setattr(scheduler, "log_path", lambda: tmp_path / "scheduler.log")
    monkeypatch.setattr(scheduler, "_interpreter", lambda: "python")
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(
        scheduler.subprocess,
        "run",
        lambda *a, **k: _subprocess.CompletedProcess(a[0], returncode),
    )
    code = scheduler.supervise(max_restarts=2)
    return code, slept


def test_supervise_restarts_immediately_after_a_reload(monkeypatch, tmp_path):
    code, slept = _supervise_once(monkeypatch, tmp_path, scheduler.RELOAD_EXIT_CODE)
    assert code == scheduler.RELOAD_EXIT_CODE
    assert slept == []


def test_supervise_still_backs_off_after_a_crash(monkeypatch, tmp_path):
    code, slept = _supervise_once(monkeypatch, tmp_path, 1)
    assert code == 1
    assert slept == [15]


def test_supervise_backs_off_when_reloads_will_not_settle(monkeypatch, tmp_path):
    """A checkout that rewrites files for a while must not cause a spin."""
    import subprocess as _subprocess

    slept = []
    monkeypatch.setattr(scheduler, "log_path", lambda: tmp_path / "scheduler.log")
    monkeypatch.setattr(scheduler, "_interpreter", lambda: "python")
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(
        scheduler.subprocess,
        "run",
        lambda *a, **k: _subprocess.CompletedProcess(a[0], scheduler.RELOAD_EXIT_CODE),
    )
    scheduler.supervise(max_restarts=scheduler.MAX_RELOADS_PER_WINDOW + 2)
    assert slept == [15]


def test_a_schedule_pinned_to_a_stale_run_date_is_refreshed():
    """A frozen "run through" date silently recomputes the same day forever.

    The ATH schedule was created with the date form pre-filled to that day, so
    every later scheduled run recomputed 2026-09-04 and still reported success.
    A stale run is indistinguishable from a fresh one, which is why it drifted
    unnoticed.
    """
    import strategies  # noqa: F401  (populate the registry)

    stale = {"as_of": "2026-09-04", "capital": 100_000.0}
    out = scheduler.resolve_run_params(
        "breakout_ath_daily", stale, today=date(2026, 9, 8)
    )
    assert out["as_of"] == "2026-09-08"
    assert out["capital"] == 100_000.0
    # The stored schedule must not be mutated as a side effect.
    assert stale["as_of"] == "2026-09-04"


def test_a_blank_run_date_is_left_alone():
    """Blank already means today to the strategy; filling it in changes meaning."""
    import strategies  # noqa: F401

    out = scheduler.resolve_run_params(
        "breakout_ath_daily", {"capital": 100_000.0}, today=date(2026, 9, 8)
    )
    assert "as_of" not in out


def test_parameters_that_do_not_track_today_are_never_rewritten():
    import strategies  # noqa: F401

    params = {"as_of": "2026-09-04", "start": "2020-01-01", "end": "2024-01-01"}
    out = scheduler.resolve_run_params(
        "swing_backtest", params, today=date(2026, 9, 8)
    )
    assert out == params


def test_an_unknown_strategy_does_not_stop_the_run():
    params = {"as_of": "2026-09-04"}
    assert scheduler.resolve_run_params("no_such_strategy", params) == params
