"""Local, sanitized history for workbench strategy runs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.storage import connection_scope, database_path
from core.strategy import StrategyResult

DEFAULT_DB_PATH = database_path()
_SENSITIVE_MARKERS = ("token", "secret", "password", "api_key", "apikey")

#: Reserved ``params_json`` keys recording which AI backend produced a run.
#:
#: Reports are portable -- the SETUP guide encourages sharing the SQLite file
#: with friends -- and the three backends are different models, so a row with
#: no provenance is not reproducible or comparable. These live in the params
#: blob rather than a new column so existing databases keep working untouched.
BACKEND_PARAM_KEY = "_ai_backend"
MODEL_PARAM_KEY = "_ai_model"


def _provenance() -> Dict[str, Any]:
    """Best-effort record of the backend in force, never fatal to a save."""
    try:
        from core.agent.detect import detect_backend

        choice = detect_backend()
    except Exception:  # pragma: no cover - provenance must never break a save
        return {}
    if not choice.resolved:
        return {}
    record: Dict[str, Any] = {BACKEND_PARAM_KEY: choice.backend}
    if choice.model:
        record[MODEL_PARAM_KEY] = choice.model
    return record


def save_run(
    result: StrategyResult,
    params: Dict[str, Any],
    *,
    duration_ms: int,
    db_path: Optional[Path] = None,
) -> str:
    run_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()
    recorded = {**sanitize(params), **_provenance()}
    with connection_scope(db_path) as connection:
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
                json.dumps(recorded, default=str),
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
    db_path: Optional[Path] = None,
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
    with connection_scope(db_path) as connection:
        rows = connection.execute(query, values).fetchall()
    return [dict(row) for row in rows]


def get_run(
    run_id: str,
    *,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    with connection_scope(db_path) as connection:
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
