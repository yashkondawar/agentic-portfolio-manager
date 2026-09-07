"""Durable, queryable record of every Tier-2 conviction verdict.

The conviction layer could not be evaluated. Scores reached the run report and
nothing else: the per-symbol ``analysed`` records have their ``status`` and
``reason`` overwritten by later pipeline stages, so the only surviving trace of
a verdict was prose inside a stored Markdown report. Recovering the live history
meant regex-parsing those reports, and even then the *evidence* behind each call
-- what the model actually found -- was gone.

That makes the gate unfalsifiable, which is the real blocker: you cannot tune a
prompt you cannot score. This module writes one durable row per evaluation,
holding the decision, the structured evidence it was derived from, and the
sources cited, so that months later the question "did the gate earn its keep?"
is a SQL query rather than an archaeology exercise.

Two design notes worth keeping:

* The **components are stored, not just the score.** The weights that turn
  evidence into a number are a judgement call and are not yet validated against
  outcomes. Storing the components means those weights can be re-fitted later
  from the accumulated record WITHOUT re-running a single LLM call.
* The **prompt version is stored.** A verdict is only comparable to another
  verdict produced by the same question, so an unversioned history would silently
  mix incompatible samples the first time the prompt changes.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.storage import connect

logger = logging.getLogger("qtr_results.verdict_log")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conviction_verdicts (
    symbol          TEXT NOT NULL,
    decision_date   TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    conviction      REAL,
    verdict         TEXT NOT NULL DEFAULT '',
    passed_gate     INTEGER NOT NULL DEFAULT 0,
    company         TEXT NOT NULL DEFAULT '',
    quarter         TEXT NOT NULL DEFAULT '',
    result_date     TEXT NOT NULL DEFAULT '',
    beat_quality    TEXT NOT NULL DEFAULT '',
    order_book      TEXT NOT NULL DEFAULT '',
    guidance        TEXT NOT NULL DEFAULT '',
    sector_backdrop TEXT NOT NULL DEFAULT '',
    red_flags       TEXT NOT NULL DEFAULT '',
    components_json TEXT NOT NULL DEFAULT '{}',
    summary         TEXT NOT NULL DEFAULT '',
    sources         TEXT NOT NULL DEFAULT '',
    error           TEXT NOT NULL DEFAULT '',
    recorded_at     TEXT NOT NULL,
    PRIMARY KEY (symbol, decision_date, prompt_version)
);

CREATE INDEX IF NOT EXISTS idx_conviction_date
    ON conviction_verdicts (decision_date);
CREATE INDEX IF NOT EXISTS idx_conviction_symbol
    ON conviction_verdicts (symbol);
"""


def open_store(db_path: Optional[Path] = None) -> sqlite3.Connection:
    connection = connect(db_path)
    connection.executescript(_SCHEMA)
    connection.commit()
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def record_verdict(
    verdict: Any,
    *,
    symbol: str,
    decision_date: date,
    prompt_version: str,
    company: str = "",
    quarter: str = "",
    result_date: str = "",
    connection: Optional[sqlite3.Connection] = None,
) -> bool:
    """Persist one verdict. Returns True when a row was written.

    Never raises: a failure to journal must not break a strategy run, which is
    the same degradation contract the conviction call itself follows. A failed
    write is logged loudly because a silently empty log would recreate exactly
    the blindness this module exists to remove.
    """
    own = connection is None
    conn = connection
    try:
        conn = conn or open_store()
        components = getattr(verdict, "components", None) or {}
        conn.execute(
            """
            INSERT OR REPLACE INTO conviction_verdicts (
                symbol, decision_date, prompt_version, conviction, verdict,
                passed_gate, company, quarter, result_date, beat_quality,
                order_book, guidance, sector_backdrop, red_flags,
                components_json, summary, sources, error, recorded_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                symbol,
                decision_date.isoformat(),
                prompt_version,
                getattr(verdict, "conviction", None),
                _as_text(getattr(verdict, "verdict", "")),
                1 if getattr(verdict, "passes_gate", False) else 0,
                _as_text(company),
                _as_text(quarter),
                _as_text(result_date),
                _as_text(components.get("beat_quality")),
                _as_text(components.get("order_book")),
                _as_text(components.get("guidance")),
                _as_text(components.get("sector_backdrop")),
                _as_text(getattr(verdict, "one_off_flags", None)
                         or components.get("red_flags")),
                json.dumps(components, default=str, sort_keys=True),
                _as_text(getattr(verdict, "summary", "")),
                _as_text(getattr(verdict, "sources", None)),
                _as_text(getattr(verdict, "error", "") or ""),
                _now(),
            ),
        )
        conn.commit()
        return True
    except Exception as exc:  # noqa: BLE001 - journalling must never break a run
        logger.warning("Could not journal conviction verdict for %s: %s",
                       symbol, exc)
        return False
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def load_verdicts(
    *,
    since: Optional[date] = None,
    prompt_version: Optional[str] = None,
    connection: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Read back the verdict history, newest first."""
    own = connection is None
    conn = connection or open_store()
    try:
        sql = "SELECT * FROM conviction_verdicts WHERE 1=1"
        params: List[Any] = []
        if since is not None:
            sql += " AND decision_date >= ?"
            params.append(since.isoformat())
        if prompt_version is not None:
            sql += " AND prompt_version = ?"
            params.append(prompt_version)
        sql += " ORDER BY decision_date DESC, symbol"
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        if own:
            conn.close()
