"""Pipeline base class: fetch -> parse -> upsert, wrapped with job_runs logging.

Every concrete pipeline (universe, prices_yf, index_valuation, amfi_nav,
news_rss, financials, corp_actions, macro_*, newsletters) subclasses
Pipeline and implements `fetch()`, `parse()`, and `upsert()`. Calling
`run()` executes all three in sequence, logs a row to job_runs with status
('SUCCESS' | 'FAILED' | 'PARTIAL'), rows_written, and timestamps, and never
lets an exception from a single source escape to crash the whole process —
run() catches everything and returns a JobResult.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import traceback
from dataclasses import dataclass, field
from typing import Any

from afund.db.connection import get_conn


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass
class JobResult:
    job_name: str
    status: str  # SUCCESS | FAILED | PARTIAL
    rows_written: int = 0
    started_at: str = ""
    finished_at: str = ""
    error: str | None = None
    sample: Any = None
    extra: dict = field(default_factory=dict)


def log_job_run(
    conn: sqlite3.Connection,
    job_name: str,
    status: str,
    rows_written: int,
    started_at: str,
    finished_at: str,
    error: str | None,
) -> None:
    """Insert one row into job_runs. Always a plain INSERT — job_runs is an
    append-only observability log, not something we upsert against."""
    conn.execute(
        """
        INSERT INTO job_runs (job_name, status, rows_written, started_at, finished_at, error)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (job_name, status, rows_written, started_at, finished_at, error),
    )
    conn.commit()


class Pipeline:
    """Base class for a Phase 1 data pipeline.

    Subclasses set `job_name` and implement `fetch()` / `parse()` / `upsert()`.
    `fetch()` returns raw data (bytes/str/dict/whatever the source gives).
    `parse()` turns that into normalized rows (list[dict] typically).
    `upsert()` writes those rows to SQLite and returns the count written.
    """

    job_name: str = "unnamed_job"

    def __init__(self, conn: sqlite3.Connection | None = None):
        self._owns_conn = conn is None
        self.conn = conn or get_conn()

    def fetch(self) -> Any:
        raise NotImplementedError

    def parse(self, raw: Any) -> Any:
        raise NotImplementedError

    def upsert(self, parsed: Any) -> int:
        raise NotImplementedError

    def run(self) -> JobResult:
        started_at = _now_iso()
        try:
            raw = self.fetch()
            parsed = self.parse(raw)
            rows_written = self.upsert(parsed)
            finished_at = _now_iso()
            result = JobResult(
                job_name=self.job_name,
                status="SUCCESS",
                rows_written=rows_written,
                started_at=started_at,
                finished_at=finished_at,
                error=None,
                sample=parsed,
            )
            log_job_run(
                self.conn, self.job_name, "SUCCESS", rows_written, started_at, finished_at, None
            )
            return result
        except Exception as exc:  # noqa: BLE001 - a broken source must never crash the whole job
            finished_at = _now_iso()
            error_text = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            result = JobResult(
                job_name=self.job_name,
                status="FAILED",
                rows_written=0,
                started_at=started_at,
                finished_at=finished_at,
                error=error_text,
            )
            try:
                log_job_run(
                    self.conn, self.job_name, "FAILED", 0, started_at, finished_at, error_text
                )
            except Exception:  # noqa: BLE001 - even job_runs logging must not crash the caller
                pass
            return result
        finally:
            if self._owns_conn:
                self.conn.close()
