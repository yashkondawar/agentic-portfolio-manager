"""Persisted daily schedules for strategy runs.

A schedule is deliberately simpler than a cron expression: a local time of day,
a set of weekdays and a timezone. That covers every case this workbench needs
("GFS at 17:30 on weekdays") while staying trivial to render as a form and
impossible to mis-type.

Firing is *idempotent per occurrence*. Each schedule records the local date of
the occurrence it last fired (``last_fired_key``), and claiming a schedule is a
single conditional ``UPDATE``, so two daemons racing the same minute can never
both run the same job.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.storage import connection_scope

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_CATCH_UP_MINUTES = 720
WEEKDAYS = (0, 1, 2, 3, 4)
ALL_DAYS = (0, 1, 2, 3, 4, 5, 6)
DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_IST = dt_timezone(timedelta(hours=5, minutes=30))

_COLUMNS = (
    "id, name, strategy_id, enabled, run_at, days_of_week, timezone, "
    "catch_up_minutes, params_json, created_at, updated_at, last_fired_key, "
    "last_run_at, last_run_id, last_status, last_error"
)


class ScheduleError(ValueError):
    """Raised when a schedule definition is not usable."""


@dataclass(frozen=True)
class Schedule:
    id: str
    name: str
    strategy_id: str
    run_at: str
    days_of_week: tuple[int, ...] = WEEKDAYS
    timezone: str = DEFAULT_TIMEZONE
    enabled: bool = True
    catch_up_minutes: int = DEFAULT_CATCH_UP_MINUTES
    params: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    last_fired_key: Optional[str] = None
    last_run_at: Optional[str] = None
    last_run_id: Optional[str] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None

    # -- time maths ------------------------------------------------------
    def zone(self) -> Any:
        return _zone(self.timezone)

    def hour_minute(self) -> tuple[int, int]:
        match = _TIME_PATTERN.match(self.run_at)
        if not match:
            raise ScheduleError(f"Invalid run time {self.run_at!r}; expected HH:MM.")
        return int(match.group(1)), int(match.group(2))

    def occurrence_on(self, day: date) -> datetime:
        hour, minute = self.hour_minute()
        return datetime(day.year, day.month, day.day, hour, minute, tzinfo=self.zone())

    def previous_occurrence(self, now: datetime) -> Optional[datetime]:
        """Most recent scheduled moment at or before ``now`` (within a week)."""
        local = now.astimezone(self.zone())
        for offset in range(0, 8):
            day = local.date() - timedelta(days=offset)
            if day.weekday() not in self.days_of_week:
                continue
            moment = self.occurrence_on(day)
            if moment <= local:
                return moment
        return None

    def next_occurrence(self, now: datetime) -> Optional[datetime]:
        """Next scheduled moment strictly after ``now``."""
        local = now.astimezone(self.zone())
        for offset in range(0, 8):
            day = local.date() + timedelta(days=offset)
            if day.weekday() not in self.days_of_week:
                continue
            moment = self.occurrence_on(day)
            if moment > local:
                return moment
        return None

    def due_occurrence(self, now: datetime) -> Optional[datetime]:
        """The occurrence that should fire now, or ``None`` when nothing is due."""
        if not self.enabled or not self.days_of_week:
            return None
        moment = self.previous_occurrence(now)
        if moment is None:
            return None
        if occurrence_key(moment) == self.last_fired_key:
            return None
        late_minutes = (now.astimezone(self.zone()) - moment).total_seconds() / 60
        if late_minutes > max(0, int(self.catch_up_minutes)):
            return None
        return moment

    def is_due(self, now: datetime) -> bool:
        return self.due_occurrence(now) is not None

    def describe(self) -> str:
        if tuple(self.days_of_week) == ALL_DAYS:
            days = "every day"
        elif tuple(self.days_of_week) == WEEKDAYS:
            days = "Mon-Fri"
        else:
            days = ", ".join(DAY_LABELS[d] for d in self.days_of_week)
        return f"{self.run_at} {self.timezone} · {days}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "strategy_id": self.strategy_id,
            "run_at": self.run_at,
            "days_of_week": list(self.days_of_week),
            "timezone": self.timezone,
            "enabled": self.enabled,
            "catch_up_minutes": self.catch_up_minutes,
            "params": dict(self.params),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_fired_key": self.last_fired_key,
            "last_run_at": self.last_run_at,
            "last_run_id": self.last_run_id,
            "last_status": self.last_status,
            "last_error": self.last_error,
        }


def occurrence_key(moment: datetime) -> str:
    """Stable identity for one scheduled occurrence."""
    return moment.date().isoformat()


def _zone(name: str) -> Any:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        # Windows ships no IANA database; tzdata is normally present via pandas,
        # but a fixed IST offset keeps the scheduler usable if it is not.
        return _IST if name == DEFAULT_TIMEZONE else dt_timezone.utc


def _utc_now() -> str:
    return datetime.now(dt_timezone.utc).isoformat()


def normalize_time(value: str) -> str:
    text = str(value).strip()
    if len(text) == 4 and text.isdigit():
        text = f"{text[:2]}:{text[2:]}"
    if not _TIME_PATTERN.match(text):
        raise ScheduleError(f"Invalid run time {value!r}; expected 24h HH:MM.")
    return text


def normalize_days(days: Iterable[int]) -> tuple[int, ...]:
    cleaned = sorted({int(day) for day in days})
    if not cleaned:
        raise ScheduleError("A schedule needs at least one weekday.")
    if any(day < 0 or day > 6 for day in cleaned):
        raise ScheduleError("Weekdays must be 0 (Monday) through 6 (Sunday).")
    return tuple(cleaned)


def _row_to_schedule(row: Mapping[str, Any]) -> Schedule:
    raw_days = str(row["days_of_week"] or "")
    days = tuple(int(part) for part in raw_days.split(",") if part.strip() != "")
    return Schedule(
        id=row["id"],
        name=row["name"],
        strategy_id=row["strategy_id"],
        run_at=row["run_at"],
        days_of_week=days,
        timezone=row["timezone"] or DEFAULT_TIMEZONE,
        enabled=bool(row["enabled"]),
        catch_up_minutes=int(row["catch_up_minutes"]),
        params=json.loads(row["params_json"] or "{}"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_fired_key=row["last_fired_key"],
        last_run_at=row["last_run_at"],
        last_run_id=row["last_run_id"],
        last_status=row["last_status"],
        last_error=row["last_error"],
    )


def list_schedules(
    *,
    enabled_only: bool = False,
    db_path: Optional[Path] = None,
) -> list[Schedule]:
    query = f"SELECT {_COLUMNS} FROM schedules"
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY run_at ASC, name ASC"
    with connection_scope(db_path) as connection:
        rows = connection.execute(query).fetchall()
    return [_row_to_schedule(row) for row in rows]


def get_schedule(
    schedule_id: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[Schedule]:
    with connection_scope(db_path) as connection:
        row = connection.execute(
            f"SELECT {_COLUMNS} FROM schedules WHERE id = ?",
            (schedule_id,),
        ).fetchone()
    return None if row is None else _row_to_schedule(row)


def save_schedule(
    schedule: Schedule,
    *,
    db_path: Optional[Path] = None,
) -> Schedule:
    """Insert or update ``schedule``, validating and normalizing it first."""
    if not str(schedule.strategy_id).strip():
        raise ScheduleError("A schedule needs a strategy.")
    prepared = replace(
        schedule,
        id=schedule.id or uuid.uuid4().hex,
        name=(schedule.name or schedule.strategy_id).strip(),
        run_at=normalize_time(schedule.run_at),
        days_of_week=normalize_days(schedule.days_of_week),
        timezone=(schedule.timezone or DEFAULT_TIMEZONE).strip(),
        catch_up_minutes=max(0, int(schedule.catch_up_minutes)),
        created_at=schedule.created_at or _utc_now(),
        updated_at=_utc_now(),
    )
    with connection_scope(db_path) as connection:
        connection.execute(
            """
            INSERT INTO schedules (
                id, name, strategy_id, enabled, run_at, days_of_week, timezone,
                catch_up_minutes, params_json, created_at, updated_at,
                last_fired_key, last_run_at, last_run_id, last_status, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                strategy_id = excluded.strategy_id,
                enabled = excluded.enabled,
                run_at = excluded.run_at,
                days_of_week = excluded.days_of_week,
                timezone = excluded.timezone,
                catch_up_minutes = excluded.catch_up_minutes,
                params_json = excluded.params_json,
                updated_at = excluded.updated_at
            """,
            (
                prepared.id,
                prepared.name,
                prepared.strategy_id,
                1 if prepared.enabled else 0,
                prepared.run_at,
                ",".join(str(day) for day in prepared.days_of_week),
                prepared.timezone,
                prepared.catch_up_minutes,
                json.dumps(dict(prepared.params), default=str),
                prepared.created_at,
                prepared.updated_at,
                prepared.last_fired_key,
                prepared.last_run_at,
                prepared.last_run_id,
                prepared.last_status,
                prepared.last_error,
            ),
        )
    return prepared


def create_schedule(
    *,
    strategy_id: str,
    run_at: str,
    name: str = "",
    days_of_week: Iterable[int] = WEEKDAYS,
    timezone: str = DEFAULT_TIMEZONE,
    enabled: bool = True,
    catch_up_minutes: int = DEFAULT_CATCH_UP_MINUTES,
    params: Optional[Mapping[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> Schedule:
    return save_schedule(
        Schedule(
            id="",
            name=name or strategy_id,
            strategy_id=strategy_id,
            run_at=run_at,
            days_of_week=tuple(days_of_week),
            timezone=timezone,
            enabled=enabled,
            catch_up_minutes=catch_up_minutes,
            params=dict(params or {}),
        ),
        db_path=db_path,
    )


def delete_schedule(schedule_id: str, *, db_path: Optional[Path] = None) -> bool:
    with connection_scope(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM schedules WHERE id = ?", (schedule_id,)
        )
    return cursor.rowcount > 0


def set_enabled(
    schedule_id: str,
    enabled: bool,
    *,
    db_path: Optional[Path] = None,
) -> None:
    with connection_scope(db_path) as connection:
        connection.execute(
            "UPDATE schedules SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, _utc_now(), schedule_id),
        )


def claim_occurrence(
    schedule_id: str,
    key: str,
    *,
    db_path: Optional[Path] = None,
) -> bool:
    """Atomically mark an occurrence as taken. ``False`` means someone beat us."""
    with connection_scope(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE schedules
               SET last_fired_key = ?, updated_at = ?
             WHERE id = ?
               AND enabled = 1
               AND (last_fired_key IS NULL OR last_fired_key != ?)
            """,
            (key, _utc_now(), schedule_id, key),
        )
    return cursor.rowcount > 0


def record_outcome(
    schedule_id: str,
    *,
    status: str,
    run_id: Optional[str] = None,
    error: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    now = _utc_now()
    with connection_scope(db_path) as connection:
        connection.execute(
            """
            UPDATE schedules
               SET last_run_at = ?, last_run_id = ?, last_status = ?,
                   last_error = ?, updated_at = ?
             WHERE id = ?
            """,
            (now, run_id, status, error, now, schedule_id),
        )


# ---------------------------------------------------------------------------
# Recommended defaults
# ---------------------------------------------------------------------------
# Both jobs are post-close jobs. A signal seen at today's close is acted on at
# the *next* open, so the report has to be sitting in the database before the
# bell rather than being computed at it.
DEFAULT_SCHEDULES: tuple[dict[str, Any], ...] = (
    {
        "name": "GFS multi-timeframe (post-close)",
        "strategy_id": "gfs_live",
        "run_at": "17:30",
        "days_of_week": WEEKDAYS,
        "params": {},
        "why": (
            "NSE closes at 15:30 IST and the bar store needs the exchange to "
            "publish today's candle (~16:00). 17:30 leaves headroom, and the "
            "engine's orders are for tomorrow's open anyway."
        ),
    },
    {
        "name": "Quarterly results ledger (evening)",
        "strategy_id": "qtr_results",
        "run_at": "19:30",
        "days_of_week": ALL_DAYS,
        "params": {},
        "why": (
            "Indian boards approve results after the close, and filings keep "
            "landing all evening. 19:30 catches the day's batch, and running "
            "all seven days picks up the Saturday board meetings banks and "
            "NBFCs favour. Exit management still uses the last available close."
        ),
    },
    {
        "name": "Quarterly results ledger (pre-open refresh)",
        "strategy_id": "qtr_results",
        "run_at": "08:15",
        "days_of_week": WEEKDAYS,
        "enabled": False,
        "params": {},
        "why": (
            "Optional second pass for filings that land late at night, so the "
            "action list is current when you open the app at 09:15. Off by "
            "default because the evening run usually already has them."
        ),
    },
)


def ensure_defaults(*, db_path: Optional[Path] = None) -> list[Schedule]:
    """Seed the recommended schedules once. Existing rows are never touched."""
    existing = list_schedules(db_path=db_path)
    if existing:
        return existing
    for spec in DEFAULT_SCHEDULES:
        create_schedule(
            strategy_id=spec["strategy_id"],
            run_at=spec["run_at"],
            name=spec["name"],
            days_of_week=spec["days_of_week"],
            enabled=spec.get("enabled", True),
            params=spec.get("params", {}),
            db_path=db_path,
        )
    return list_schedules(db_path=db_path)
