"""Offline tests for dashboard/_shared.py — the Phase 11 multipage app's
shared helpers. Only the pure/DB-query pieces are unit-tested here (per the
plan: "app pages aren't unit-tested; _shared.py helpers ARE"):
  - staleness_check() goldens (green/amber/red/unknown thresholds)
  - job_runs_rolling() / agent_runs_rolling() rolling-5-day window queries
  - build_run_job_args() argv construction

No Streamlit runtime is exercised (st.cache_resource etc. are decorators
only touched when a page actually runs under `streamlit run`), no network,
no subprocess execution.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "src" / "afund" / "db" / "schema.sql"
DASHBOARD_ROOT = REPO_ROOT / "dashboard"
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402


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


TODAY = dt.date(2026, 7, 6)


# ---------------------------------------------------------------------------
# staleness_check
# ---------------------------------------------------------------------------

def test_staleness_check_empty_db_is_unknown(conn):
    chips = shared.staleness_check(conn, as_of=TODAY)
    by_name = {c["name"]: c for c in chips}
    assert set(by_name) == {"daily_prices", "index_data", "news_items", "macro_series"}
    for chip in chips:
        assert chip["level"] == "unknown"
        assert chip["latest_date"] is None
        assert chip["age_days"] is None


def test_staleness_check_green_within_threshold(conn):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (1, 'TCS', 'STOCK', 1)"
    )
    conn.execute(
        "INSERT INTO daily_prices (instrument_id, date, close) VALUES (1, ?, 100)",
        ((TODAY - dt.timedelta(days=1)).isoformat(),),
    )
    conn.commit()
    chips = shared.staleness_check(conn, as_of=TODAY)
    chip = next(c for c in chips if c["name"] == "daily_prices")
    assert chip["level"] == "green"
    assert chip["age_days"] == 1


def test_staleness_check_amber_and_red_bounds(conn):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (1, 'TCS', 'STOCK', 1)"
    )
    # daily_prices thresholds: green<=2, amber<=5, else red.
    conn.execute(
        "INSERT INTO daily_prices (instrument_id, date, close) VALUES (1, ?, 100)",
        ((TODAY - dt.timedelta(days=4)).isoformat(),),
    )
    conn.commit()
    chips = shared.staleness_check(conn, as_of=TODAY)
    chip = next(c for c in chips if c["name"] == "daily_prices")
    assert chip["level"] == "amber"
    assert chip["age_days"] == 4

    conn.execute(
        "UPDATE daily_prices SET date = ?", ((TODAY - dt.timedelta(days=10)).isoformat(),)
    )
    conn.commit()
    chips = shared.staleness_check(conn, as_of=TODAY)
    chip = next(c for c in chips if c["name"] == "daily_prices")
    assert chip["level"] == "red"
    assert chip["age_days"] == 10


def test_staleness_check_macro_series_wider_cadence(conn):
    # macro_series thresholds are wider (monthly cadence): green<=35, amber<=70.
    conn.execute(
        "INSERT INTO macro_series (series_code, date, value) VALUES ('GSEC_10Y', ?, 7.1)",
        ((TODAY - dt.timedelta(days=30)).isoformat(),),
    )
    conn.commit()
    chips = shared.staleness_check(conn, as_of=TODAY)
    chip = next(c for c in chips if c["name"] == "macro_series")
    assert chip["level"] == "green"


# ---------------------------------------------------------------------------
# job_runs_rolling / agent_runs_rolling
# ---------------------------------------------------------------------------

def test_job_runs_rolling_window(conn):
    recent_ts = (TODAY - dt.timedelta(days=1)).isoformat() + "T10:00:00"
    older_ts = (TODAY - dt.timedelta(days=10)).isoformat() + "T10:00:00"
    conn.execute(
        "INSERT INTO job_runs (job_name, status, rows_written, started_at, finished_at) "
        "VALUES ('daily_data', 'SUCCESS', 10, ?, ?)",
        (recent_ts, recent_ts),
    )
    conn.execute(
        "INSERT INTO job_runs (job_name, status, rows_written, started_at, finished_at) "
        "VALUES ('daily_data', 'SUCCESS', 5, ?, ?)",
        (older_ts, older_ts),
    )
    conn.commit()

    result = shared.job_runs_rolling(conn, as_of=TODAY)
    assert result["older_count"] == 1
    assert len(result["recent"]) == 1
    assert result["recent"][0]["job_name"] == "daily_data"
    assert result["recent"][0]["started_at"] == recent_ts


def test_job_runs_rolling_keeps_latest_per_job(conn):
    ts1 = (TODAY - dt.timedelta(days=3)).isoformat() + "T09:00:00"
    ts2 = (TODAY - dt.timedelta(days=1)).isoformat() + "T09:00:00"
    conn.execute(
        "INSERT INTO job_runs (job_name, status, started_at, finished_at) VALUES ('daily_data', 'SUCCESS', ?, ?)",
        (ts1, ts1),
    )
    conn.execute(
        "INSERT INTO job_runs (job_name, status, started_at, finished_at) VALUES ('daily_data', 'FAILED', ?, ?)",
        (ts2, ts2),
    )
    conn.commit()

    result = shared.job_runs_rolling(conn, as_of=TODAY)
    assert len(result["recent"]) == 1
    assert result["recent"][0]["started_at"] == ts2
    assert result["recent"][0]["status"] == "FAILED"


def test_agent_runs_rolling_window(conn):
    recent_ts = (TODAY - dt.timedelta(days=2)).isoformat() + "T12:00:00"
    older_ts = (TODAY - dt.timedelta(days=20)).isoformat() + "T12:00:00"
    conn.execute(
        "INSERT INTO agent_runs (role, model, backend, status, started_at, finished_at) "
        "VALUES ('idea_gen', 'sonnet', 'claude_code', 'COMPLETED', ?, ?)",
        (recent_ts, recent_ts),
    )
    conn.execute(
        "INSERT INTO agent_runs (role, model, backend, status, started_at, finished_at) "
        "VALUES ('idea_gen', 'sonnet', 'claude_code', 'COMPLETED', ?, ?)",
        (older_ts, older_ts),
    )
    conn.commit()

    result = shared.agent_runs_rolling(conn, as_of=TODAY)
    assert result["older_count"] == 1
    assert len(result["recent"]) == 1
    assert result["recent"][0]["role"] == "idea_gen"


def test_rolling_windows_empty_db(conn):
    jobs = shared.job_runs_rolling(conn, as_of=TODAY)
    agents = shared.agent_runs_rolling(conn, as_of=TODAY)
    assert jobs == {"recent": [], "older_count": 0}
    assert agents == {"recent": [], "older_count": 0}


# ---------------------------------------------------------------------------
# build_run_job_args
# ---------------------------------------------------------------------------

def test_build_run_job_args_basic():
    args = shared.build_run_job_args("daily_data")
    assert args[0] == str(shared.PYTHON_EXE)
    assert args[1:] == ["-m", "afund.orchestrator.run", "--job", "daily_data"]


def test_build_run_job_args_with_symbol():
    args = shared.build_run_job_args("weekly_idea_cycle", {"symbol": "TCS"})
    assert args[-2:] == ["--symbol", "TCS"]


def test_build_run_job_args_skips_none_and_false():
    args = shared.build_run_job_args("daily_data", {"symbol": None, "scope": False})
    assert "--symbol" not in args
    assert "--scope" not in args


def test_build_run_job_args_bool_true_is_bare_flag():
    args = shared.build_run_job_args("daily_data", {"all": True})
    assert args[-1] == "--all"


# ---------------------------------------------------------------------------
# instrument_exists / list_active_symbols
# ---------------------------------------------------------------------------

def test_instrument_exists_true_for_active_symbol(conn):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (1, 'TCS', 'STOCK', 1)"
    )
    conn.commit()
    assert shared.instrument_exists(conn, "TCS") is True
    assert shared.instrument_exists(conn, "tcs") is True  # case-insensitive via .upper()


def test_instrument_exists_false_for_unknown_symbol(conn):
    assert shared.instrument_exists(conn, "NOTREAL") is False


def test_instrument_exists_false_for_inactive_symbol(conn):
    conn.execute(
        "INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (1, 'DELISTED', 'STOCK', 0)"
    )
    conn.commit()
    assert shared.instrument_exists(conn, "DELISTED") is False


def test_instrument_exists_false_for_empty_string(conn):
    assert shared.instrument_exists(conn, "") is False


def test_list_active_symbols_excludes_inactive(conn):
    conn.execute("INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (1, 'TCS', 'STOCK', 1)")
    conn.execute("INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (2, 'INFY', 'STOCK', 1)")
    conn.execute("INSERT INTO instruments (id, symbol, instrument_type, active) VALUES (3, 'OLD', 'STOCK', 0)")
    conn.commit()
    assert shared.list_active_symbols(conn) == ["INFY", "TCS"]


def test_list_active_symbols_empty_db(conn):
    assert shared.list_active_symbols(conn) == []


# ---------------------------------------------------------------------------
# latest_agent_output / latest_batch_id_for_trigger
# ---------------------------------------------------------------------------

def test_latest_agent_output_none_when_no_agent_runs(conn):
    assert shared.latest_agent_output(conn, "idea_gen") is None


def test_latest_agent_output_none_when_output_file_missing(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(shared, "REPO_ROOT", tmp_path)
    conn.execute(
        "INSERT INTO agent_runs (role, model, backend, status, run_batch_id, started_at, finished_at) "
        "VALUES ('idea_gen', 'sonnet', 'claude_code', 'COMPLETED', 'batch1', '2026-07-01T00:00:00', '2026-07-01T00:00:01')"
    )
    conn.commit()
    assert shared.latest_agent_output(conn, "idea_gen") is None


def test_latest_agent_output_reads_json_for_completed_row(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(shared, "REPO_ROOT", tmp_path)
    cur = conn.execute(
        "INSERT INTO agent_runs (role, model, backend, status, run_batch_id, started_at, finished_at) "
        "VALUES ('idea_gen', 'sonnet', 'claude_code', 'COMPLETED', 'batch1', '2026-07-01T00:00:00', '2026-07-01T00:00:01')"
    )
    conn.commit()
    run_id = cur.lastrowid

    out_dir = tmp_path / "data" / "packets" / "batch1" / "outputs"
    out_dir.mkdir(parents=True)
    (out_dir / f"{run_id}_idea_gen_output.json").write_text('{"ideas": []}', encoding="utf-8")

    result = shared.latest_agent_output(conn, "idea_gen")
    assert result == {"ideas": []}


def test_latest_agent_output_ignores_non_completed_status(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(shared, "REPO_ROOT", tmp_path)
    conn.execute(
        "INSERT INTO agent_runs (role, model, backend, status, run_batch_id, started_at, finished_at) "
        "VALUES ('idea_gen', 'sonnet', 'claude_code', 'PREPARED', 'batch1', '2026-07-01T00:00:00', NULL)"
    )
    conn.commit()
    assert shared.latest_agent_output(conn, "idea_gen") is None


def test_latest_agent_output_scoped_to_batch_id(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(shared, "REPO_ROOT", tmp_path)
    conn.execute(
        "INSERT INTO agent_runs (role, model, backend, status, run_batch_id, started_at, finished_at) "
        "VALUES ('idea_gen', 'sonnet', 'claude_code', 'COMPLETED', 'batch_old', '2026-06-01T00:00:00', '2026-06-01T00:00:01')"
    )
    cur = conn.execute(
        "INSERT INTO agent_runs (role, model, backend, status, run_batch_id, started_at, finished_at) "
        "VALUES ('idea_gen', 'sonnet', 'claude_code', 'COMPLETED', 'batch_new', '2026-07-01T00:00:00', '2026-07-01T00:00:01')"
    )
    conn.commit()
    new_id = cur.lastrowid

    old_dir = tmp_path / "data" / "packets" / "batch_old" / "outputs"
    old_dir.mkdir(parents=True)
    (old_dir / "1_idea_gen_output.json").write_text('{"ideas": ["old"]}', encoding="utf-8")

    new_dir = tmp_path / "data" / "packets" / "batch_new" / "outputs"
    new_dir.mkdir(parents=True)
    (new_dir / f"{new_id}_idea_gen_output.json").write_text('{"ideas": ["new"]}', encoding="utf-8")

    assert shared.latest_agent_output(conn, "idea_gen", batch_id="batch_old") == {"ideas": ["old"]}
    assert shared.latest_agent_output(conn, "idea_gen", batch_id="batch_new") == {"ideas": ["new"]}


def test_latest_batch_id_for_trigger_returns_most_recent(conn):
    conn.execute(
        "INSERT INTO agent_runs (role, model, backend, status, run_batch_id, started_at, finished_at) "
        "VALUES ('idea_gen', 'sonnet', 'claude_code', 'COMPLETED', 'batch_old', '2026-06-01T00:00:00', '2026-06-01T00:00:01')"
    )
    conn.execute(
        "INSERT INTO agent_runs (role, model, backend, status, run_batch_id, started_at, finished_at) "
        "VALUES ('idea_gen', 'sonnet', 'claude_code', 'PREPARED', 'batch_new', '2026-07-01T00:00:00', NULL)"
    )
    conn.commit()
    assert shared.latest_batch_id_for_trigger(conn, role="idea_gen") == "batch_new"


def test_latest_batch_id_for_trigger_none_when_empty(conn):
    assert shared.latest_batch_id_for_trigger(conn, role="idea_gen") is None
