"""Offline tests for shared plumbing: RateLimiter (http.py) and the Pipeline
base class's job_runs logging / graceful-failure contract (base.py). No network."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from afund.data.base import JobResult, Pipeline, log_job_run
from afund.data.http import RateLimiter

REPO_ROOT = Path(__file__).resolve().parents[2]
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


# --- RateLimiter -------------------------------------------------------------

def test_rate_limiter_enforces_minimum_interval():
    limiter = RateLimiter()
    limiter.wait("test-host", min_interval=0.2)
    start = time.monotonic()
    limiter.wait("test-host", min_interval=0.2)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.18  # small tolerance for scheduler jitter


def test_rate_limiter_zero_interval_does_not_block():
    limiter = RateLimiter()
    start = time.monotonic()
    limiter.wait("test-host", min_interval=0.0)
    limiter.wait("test-host", min_interval=0.0)
    assert time.monotonic() - start < 0.1


def test_rate_limiter_different_hosts_independent():
    limiter = RateLimiter()
    limiter.wait("host-a", min_interval=0.3)
    start = time.monotonic()
    limiter.wait("host-b", min_interval=0.3)  # different host, should not wait
    assert time.monotonic() - start < 0.1


# --- Pipeline base class ------------------------------------------------------

class _SucceedingPipeline(Pipeline):
    job_name = "test_succeed"

    def fetch(self):
        return {"a": 1}

    def parse(self, raw):
        return [raw]

    def upsert(self, parsed):
        return len(parsed)


class _FailingPipeline(Pipeline):
    job_name = "test_fail"

    def fetch(self):
        raise RuntimeError("simulated source failure")

    def parse(self, raw):
        return raw

    def upsert(self, parsed):
        return 0


def test_pipeline_success_logs_job_run(conn):
    result = _SucceedingPipeline(conn=conn).run()
    assert result.status == "SUCCESS"
    assert result.rows_written == 1

    row = conn.execute("SELECT * FROM job_runs WHERE job_name = 'test_succeed'").fetchone()
    assert row is not None
    assert row["status"] == "SUCCESS"
    assert row["rows_written"] == 1


def test_pipeline_failure_does_not_raise_and_logs_error(conn):
    result = _FailingPipeline(conn=conn).run()
    assert result.status == "FAILED"
    assert result.rows_written == 0
    assert "simulated source failure" in result.error

    row = conn.execute("SELECT * FROM job_runs WHERE job_name = 'test_fail'").fetchone()
    assert row is not None
    assert row["status"] == "FAILED"
    assert "simulated source failure" in row["error"]


def test_log_job_run_writes_expected_columns(conn):
    log_job_run(conn, "manual_job", "PARTIAL", 5, "2026-01-01T00:00:00", "2026-01-01T00:01:00", "some warning")
    row = conn.execute("SELECT * FROM job_runs WHERE job_name = 'manual_job'").fetchone()
    assert row["status"] == "PARTIAL"
    assert row["rows_written"] == 5
    assert row["error"] == "some warning"


def test_job_result_dataclass_defaults():
    result = JobResult(job_name="x", status="SUCCESS")
    assert result.rows_written == 0
    assert result.error is None
    assert result.extra == {}
