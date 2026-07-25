"""Local, sanitized history for workbench strategy runs."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.strategy import StrategyResult

_db_override = os.getenv("TRADER_WORKBENCH_DB", "").strip()
DEFAULT_DB_PATH = (
    Path(_db_override)
    if _db_override
    else Path(__file__).resolve().parents[1] / ".trader_workbench" / "runs.sqlite3"
)
_SENSITIVE_MARKERS = ("token", "secret", "password", "api_key", "apikey")


def save_run(
    result: StrategyResult,
    params: Dict[str, Any],
    *,
    duration_ms: int,
    db_path: Path = DEFAULT_DB_PATH,
) -> str:
    run_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO runs (
                id, strategy_id, status, created_at, duration_ms,
                params_json, report, data_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                result.strategy_id,
                result.status,
                created_at,
                int(duration_ms),
                json.dumps(sanitize(params), default=str),
                result.report,
                json.dumps(result.data, default=str),
                result.error,
            ),
        )
    return run_id


def list_runs(
    *,
    limit: int = 25,
    strategy_id: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict]:
    query = (
        "SELECT id, strategy_id, status, created_at, duration_ms, error " "FROM runs"
    )
    values: list[Any] = []
    if strategy_id:
        query += " WHERE strategy_id = ?"
        values.append(strategy_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    values.append(max(1, int(limit)))
    with _connect(db_path) as connection:
        rows = connection.execute(query, values).fetchall()
    return [dict(row) for row in rows]


def get_run(
    run_id: str,
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> Optional[dict]:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    record = dict(row)
    record["params"] = json.loads(record.pop("params_json"))
    record["data"] = json.loads(record.pop("data_json"))
    return record


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            cleaned[key] = (
                "[REDACTED]"
                if any(marker in normalized for marker in _SENSITIVE_MARKERS)
                else sanitize(item)
            )
        return cleaned
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return value


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            params_json TEXT NOT NULL,
            report TEXT NOT NULL,
            data_json TEXT NOT NULL,
            error TEXT
        )
        """
    )
    return connection
