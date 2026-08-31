"""Deterministic due-job scheduler over config/settings.yaml -> cadences.

Cadence string formats supported:
  "daily HH:MM"   — due every calendar day (the HH:MM is a hint for the
                     external OS scheduler — see scripts/register_tasks.ps1
                     — not evaluated here since due_jobs() takes a date, not
                     a datetime).
  "weekly DDD"    — due once a week on the named weekday (MON/TUE/.../SUN).
  "monthly D"     — due once a month on calendar day D (e.g. "monthly 6").
  "quarterly"     — due within the first 5 days of Jan/Apr/Jul/Oct.

due_jobs() additionally consults `last_run` (job_name -> last ISO date run,
typically sourced from job_runs) so a job already run within its current
cadence window is not flagged due again — e.g. a weekly job run on Monday
should not still show "due" on Tuesday-Friday of the same week.
"""
from __future__ import annotations

import datetime as dt

from afund.config import load_settings

_WEEKDAY_ABBR = {
    "MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6,
}

QUARTER_START_MONTHS = {1, 4, 7, 10}
QUARTERLY_WINDOW_DAYS = 5  # first 5 days of the quarter-start month


def _parse_cadence(cadence: str) -> tuple[str, str | None]:
    """Split a cadence string into (kind, arg). arg is None for 'quarterly'."""
    parts = cadence.strip().split(None, 1)
    kind = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else None
    return kind, arg


def _week_start(on_date: dt.date) -> dt.date:
    """Monday of the ISO week containing on_date."""
    return on_date - dt.timedelta(days=on_date.weekday())


def _month_start(on_date: dt.date) -> dt.date:
    return on_date.replace(day=1)


def _quarter_start(on_date: dt.date) -> dt.date | None:
    """The quarter-start date (Jan/Apr/Jul/Oct 1) if on_date falls within the
    first QUARTERLY_WINDOW_DAYS days of a quarter-start month, else None."""
    if on_date.month in QUARTER_START_MONTHS and on_date.day <= QUARTERLY_WINDOW_DAYS:
        return on_date.replace(day=1)
    return None


def _is_due(cadence: str, on_date: dt.date) -> bool:
    """Whether `cadence`'s window includes on_date, ignoring last_run."""
    kind, arg = _parse_cadence(cadence)

    if kind == "daily":
        return True

    if kind == "weekly":
        if not arg:
            return False
        target_weekday = _WEEKDAY_ABBR.get(arg.upper())
        if target_weekday is None:
            return False
        return on_date.weekday() == target_weekday

    if kind == "monthly":
        if not arg:
            return False
        try:
            target_day = int(arg)
        except ValueError:
            return False
        return on_date.day == target_day

    if kind == "quarterly":
        return _quarter_start(on_date) is not None

    return False


def _window_start(cadence: str, on_date: dt.date) -> dt.date | None:
    """The start date of the cadence window containing on_date (used to
    compare against last_run so a job isn't re-flagged mid-window). None for
    'daily' (each day is its own window)."""
    kind, arg = _parse_cadence(cadence)

    if kind == "daily":
        return None
    if kind == "weekly":
        return _week_start(on_date)
    if kind == "monthly":
        return _month_start(on_date)
    if kind == "quarterly":
        return _quarter_start(on_date)
    return None


def due_jobs(
    on_date: dt.date, last_run: dict[str, str] | None = None
) -> list[str]:
    """Return the list of cadence-key job names due on `on_date`.

    last_run: optional dict of job_name -> last-run date (ISO string,
    typically sourced from job_runs' most recent SUCCESS per job_name). When
    provided, a job whose cadence window start is on or before last_run's
    date (i.e. it already ran within the current window) is excluded. Daily
    jobs are always re-evaluated per-day regardless of last_run (running a
    daily job "again" within the same day is a caller-level idempotency
    concern, not a scheduling one).
    """
    settings = load_settings()
    cadences: dict[str, str] = settings.get("cadences", {}) or {}
    last_run = last_run or {}

    due: list[str] = []
    for job_name, cadence in cadences.items():
        if not _is_due(cadence, on_date):
            continue

        window_start = _window_start(cadence, on_date)
        if window_start is not None and job_name in last_run:
            try:
                last_run_date = dt.date.fromisoformat(last_run[job_name][:10])
            except ValueError:
                last_run_date = None
            if last_run_date is not None and last_run_date >= window_start:
                continue  # already run within this cadence's current window

        due.append(job_name)

    return due
