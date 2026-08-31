"""Shared helpers for the multipage Streamlit dashboard.

Every page imports from here rather than duplicating connection/formatting/
subprocess plumbing. Nothing in this module writes to the database — the
dashboard stays read-only + CLI-surfacing per CLAUDE.md's hard rules;
`run_job()` shells out to the same `afund.orchestrator.run` CLI a human
would type, it never calls pipeline code directly.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterator

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from afund.config import load_settings, get_db_path  # noqa: E402

PYTHON_EXE = REPO_ROOT / ".venv" / "Scripts" / "python"

# Rolling window for the Home/Ops status boards (Phase 11 spec: "rolling
# 5-day window only — older activity collapses to one count line").
ROLLING_WINDOW_DAYS = 5

# Expected cadence (in days) per staleness chip, used by staleness_check()
# to color a chip green/amber/red. DRAFT judgment calls (no back-tested
# cadence yet) — thresholds live here, not scattered across pages.
STALENESS_THRESHOLDS_DAYS = {
    "daily_prices": {"green": 2, "amber": 5},
    "index_data": {"green": 2, "amber": 5},
    "news_items": {"green": 2, "amber": 5},
    "macro_series": {"green": 35, "amber": 70},
}


@st.cache_resource
def get_conn() -> sqlite3.Connection:
    """Cached read-only-by-convention SQLite connection (the app never
    writes; decisions/approvals happen via the CLI per CLAUDE.md)."""
    conn = sqlite3.connect(str(get_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def df_from_query(conn: sqlite3.Connection, query: str, params: tuple = ()) -> pd.DataFrame:
    rows = conn.execute(query, params).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


def fmt_money(value, currency: str = "INR") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    return f"{currency} {value:,.2f}"


def fmt_pct(value, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    return f"{value * 100:.{decimals}f}%" if abs(value) < 5 else f"{value:.{decimals}f}%"


def fmt_num(value, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    return f"{value:,.{decimals}f}"


def get_settings() -> dict:
    return load_settings()


# ---------------------------------------------------------------------------
# Rolling-window status board queries
# ---------------------------------------------------------------------------

def _cutoff_date(as_of: dt.date | None = None, window_days: int = ROLLING_WINDOW_DAYS) -> str:
    as_of = as_of or dt.date.today()
    return (as_of - dt.timedelta(days=window_days)).isoformat()


def job_runs_rolling(conn: sqlite3.Connection, *, window_days: int = ROLLING_WINDOW_DAYS,
                      as_of: dt.date | None = None) -> dict:
    """Last-run timestamp per job_name within the rolling window, plus a
    single collapsed count of older runs. Returns
    {"recent": [{"job_name", "status", "started_at", "finished_at"}...],
     "older_count": int}."""
    cutoff = _cutoff_date(as_of, window_days)
    recent_rows = conn.execute(
        """
        SELECT job_name, status, started_at, finished_at, MAX(started_at) OVER (PARTITION BY job_name) AS last_started
          FROM job_runs
         WHERE started_at >= ?
         ORDER BY started_at DESC
        """,
        (cutoff,),
    ).fetchall()

    # Keep only the latest row per job_name (SQL window function gave us the
    # max started_at per group; filter down to those exact rows).
    seen = set()
    recent = []
    for row in recent_rows:
        if row["job_name"] in seen:
            continue
        seen.add(row["job_name"])
        recent.append({
            "job_name": row["job_name"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        })

    older_count_row = conn.execute(
        "SELECT COUNT(*) AS n FROM job_runs WHERE started_at < ?", (cutoff,)
    ).fetchone()
    older_count = older_count_row["n"] if older_count_row else 0

    recent.sort(key=lambda r: r["started_at"] or "", reverse=True)
    return {"recent": recent, "older_count": older_count}


def agent_runs_rolling(conn: sqlite3.Connection, *, window_days: int = ROLLING_WINDOW_DAYS,
                        as_of: dt.date | None = None) -> dict:
    """Last-run timestamp per agent role within the rolling window, plus a
    collapsed older count. Same shape as job_runs_rolling but keyed by role."""
    cutoff = _cutoff_date(as_of, window_days)
    recent_rows = conn.execute(
        """
        SELECT role, status, started_at, finished_at, MAX(started_at) OVER (PARTITION BY role) AS last_started
          FROM agent_runs
         WHERE started_at >= ?
         ORDER BY started_at DESC
        """,
        (cutoff,),
    ).fetchall()

    seen = set()
    recent = []
    for row in recent_rows:
        if row["role"] in seen:
            continue
        seen.add(row["role"])
        recent.append({
            "role": row["role"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        })

    older_count_row = conn.execute(
        "SELECT COUNT(*) AS n FROM agent_runs WHERE started_at < ?", (cutoff,)
    ).fetchone()
    older_count = older_count_row["n"] if older_count_row else 0

    recent.sort(key=lambda r: r["started_at"] or "", reverse=True)
    return {"recent": recent, "older_count": older_count}


# ---------------------------------------------------------------------------
# Staleness chips
# ---------------------------------------------------------------------------

def _chip_level(latest_date: str | None, thresholds: dict, *, as_of: dt.date | None = None) -> str:
    """green/amber/red/unknown from a latest ISO date string vs thresholds
    {"green": days, "amber": days}. 'unknown' when there's no data at all."""
    if not latest_date:
        return "unknown"
    as_of = as_of or dt.date.today()
    try:
        latest = dt.date.fromisoformat(latest_date[:10])
    except ValueError:
        return "unknown"
    age_days = (as_of - latest).days
    if age_days <= thresholds["green"]:
        return "green"
    if age_days <= thresholds["amber"]:
        return "amber"
    return "red"


def staleness_check(conn: sqlite3.Connection, *, as_of: dt.date | None = None) -> list[dict]:
    """One chip per tracked data source: {"name", "label", "latest_date",
    "age_days", "level"}. Never raises on an empty table — degrades to
    latest_date=None / level='unknown', matching the rest of the dashboard's
    graceful-empty-state convention."""
    as_of = as_of or dt.date.today()
    chips = []

    def _add(name: str, label: str, query: str, params: tuple = ()):
        row = conn.execute(query, params).fetchone()
        latest = row[0] if row else None
        thresholds = STALENESS_THRESHOLDS_DAYS[name]
        level = _chip_level(latest, thresholds, as_of=as_of)
        age_days = None
        if latest:
            try:
                age_days = (as_of - dt.date.fromisoformat(latest[:10])).days
            except ValueError:
                age_days = None
        chips.append({
            "name": name, "label": label, "latest_date": latest,
            "age_days": age_days, "level": level,
        })

    _add("daily_prices", "Daily prices", "SELECT MAX(date) FROM daily_prices")
    _add("index_data", "Index P/E (index_data)", "SELECT MAX(date) FROM index_data WHERE pe IS NOT NULL")
    _add("news_items", "News fetch", "SELECT MAX(fetched_at) FROM news_items")
    _add("macro_series", "Macro series", "SELECT MAX(date) FROM macro_series")

    return chips


# ---------------------------------------------------------------------------
# run_job(): subprocess wrapper around the orchestrator CLI
# ---------------------------------------------------------------------------

def build_run_job_args(job: str, extra_args: dict | None = None) -> list[str]:
    """Pure argv builder (unit-tested separately from the actual subprocess
    call) — [python_exe, -m, afund.orchestrator.run, --job, JOB, ...extra].
    extra_args keys map to CLI flags, e.g. {"symbol": "TCS"} ->
    ["--symbol", "TCS"]; boolean True values become bare flags."""
    args = [str(PYTHON_EXE), "-m", "afund.orchestrator.run", "--job", job]
    for key, value in (extra_args or {}).items():
        flag = f"--{key}"
        if value is True:
            args.append(flag)
        elif value is None or value is False:
            continue
        else:
            args.extend([flag, str(value)])
    return args


def run_job(job: str, extra_args: dict | None = None, *, cwd: Path | None = None) -> Iterator[str]:
    """Run `afund.orchestrator.run --job <job> [extra_args]` as a subprocess,
    yielding stdout lines as they arrive (for st.status live-log rendering).
    Combines stderr into stdout so failures are visible in the same stream.
    Raises nothing itself — a non-zero exit shows up as the final yielded
    line via the sentinel this function appends."""
    args = build_run_job_args(job, extra_args)
    process = subprocess.Popen(
        args,
        cwd=str(cwd or REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        yield line.rstrip("\n")
    return_code = process.wait()
    yield f"__EXIT_CODE__:{return_code}"


def run_job_streaming(job: str, extra_args: dict | None = None, *,
                       line_sink: Callable[[str], None] | None = None,
                       cwd: Path | None = None) -> int:
    """Convenience non-generator wrapper: drains run_job(), calling
    line_sink(line) for every non-sentinel line, and returns the process
    exit code. Used by pages that want a simple int back rather than
    iterating the generator themselves."""
    exit_code = 0
    for line in run_job(job, extra_args, cwd=cwd):
        if line.startswith("__EXIT_CODE__:"):
            exit_code = int(line.split(":", 1)[1])
            continue
        if line_sink:
            line_sink(line)
    return exit_code


# ---------------------------------------------------------------------------
# Misc lookups shared by multiple pages
# ---------------------------------------------------------------------------

def instrument_exists(conn: sqlite3.Connection, symbol: str) -> bool:
    """True if `symbol` matches an active row in instruments — used by the
    Ideas page to validate a typed symbol before shelling out to the
    orchestrator (clean error instead of a confusing subprocess failure)."""
    if not symbol:
        return False
    row = conn.execute(
        "SELECT 1 FROM instruments WHERE symbol = ? AND active = 1 LIMIT 1",
        (symbol.strip().upper(),),
    ).fetchone()
    return row is not None


def list_active_symbols(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM instruments WHERE active = 1 ORDER BY symbol"
    ).fetchall()
    return [r["symbol"] for r in rows]


def latest_agent_output(conn: sqlite3.Connection, role: str, *, batch_id: str | None = None) -> dict | None:
    """Best-effort load of the most recent COMPLETED output JSON for a role
    (idea_gen/synthesis/critique/fund_manager) from data/packets/<batch>/
    outputs/<id>_<role>_output.json, newest agent_runs row first. Returns
    None gracefully if nothing has been ingested yet — the Ideas viewer's
    empty state, not an exception."""
    query = (
        "SELECT id, run_batch_id FROM agent_runs WHERE role = ? AND status = 'COMPLETED'"
    )
    params: list = [role]
    if batch_id:
        query += " AND run_batch_id = ?"
        params.append(batch_id)
    query += " ORDER BY id DESC LIMIT 1"
    row = conn.execute(query, tuple(params)).fetchone()
    if row is None:
        return None
    out_path = REPO_ROOT / "data" / "packets" / row["run_batch_id"] / "outputs" / f"{row['id']}_{role}_output.json"
    if not out_path.exists():
        return None
    import json

    try:
        return json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_batch_id_for_trigger(conn: sqlite3.Connection, *, role: str = "idea_gen") -> str | None:
    """Most recent run_batch_id that produced a COMPLETED (or PREPARED) row
    for `role` — used to scope the side-by-side idea/synthesis/critique
    viewer to one coherent cycle run rather than mixing runs."""
    row = conn.execute(
        "SELECT run_batch_id FROM agent_runs WHERE role = ? ORDER BY id DESC LIMIT 1",
        (role,),
    ).fetchone()
    return row["run_batch_id"] if row else None
