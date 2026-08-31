"""Typed helpers over the 5 memory-store tables.

Tables (all defined in src/afund/db/schema.sql):
  - decision_log     — one row per recommendation put in front of the human.
  - thesis_tracker    — the live invalidation-condition tracker for open ideas.
  - knowledge_base    — free-text notes tagged by instrument/sector/macro/situation.
  - lessons           — proposed (then human-approved) heuristics from meta-research.
  - calibration       — predicted vs. realized outcomes, for Brier scoring.

Every function here takes a sqlite3.Connection as its first positional/keyword
argument and does its own commit — callers don't need to remember to commit.
Nothing in this module makes network or LLM calls; it is pure DB plumbing.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

# ---------------------------------------------------------------------------
# decision_log
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def record_recommendation(
    conn: sqlite3.Connection,
    *,
    instrument_id: int | None,
    sector: str | None,
    action: str,
    strategy_tag: str | None,
    invalidation_condition: str | None,
    fund_manager_rec_json: dict | str | None,
    registry_version: str | None,
) -> int:
    """Insert a new decision_log row with human_decision='PENDING'.

    Returns the new decision_id.
    """
    if isinstance(fund_manager_rec_json, dict):
        fund_manager_rec_json = json.dumps(fund_manager_rec_json)

    cur = conn.execute(
        """
        INSERT INTO decision_log
            (decision_date, instrument_id, sector, action, strategy_tag,
             invalidation_condition, fund_manager_rec_json, human_decision,
             human_notes, registry_version, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL, ?, ?)
        """,
        (
            dt.date.today().isoformat(),
            instrument_id,
            sector,
            action,
            strategy_tag,
            invalidation_condition,
            fund_manager_rec_json,
            registry_version,
            _now_iso(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def record_human_decision(
    conn: sqlite3.Connection, decision_id: int, decision: str, notes: str | None = None
) -> None:
    """Stamp a decision_log row with the human's APPROVE/REJECT/MODIFY call."""
    if decision not in ("APPROVE", "REJECT", "MODIFY"):
        raise ValueError(f"decision must be APPROVE|REJECT|MODIFY, got {decision!r}")
    conn.execute(
        "UPDATE decision_log SET human_decision = ?, human_notes = ? WHERE id = ?",
        (decision, notes, decision_id),
    )
    conn.commit()


def get_precedents(
    conn: sqlite3.Connection,
    *,
    instrument_id: int | None = None,
    sector: str | None = None,
    strategy_tag: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Most-recent-first decision_log rows matching ANY of the given filters.

    If no filters are given, returns an empty list (no global dumps here
    either — callers should always pass at least one scoping value).
    """
    clauses = []
    params: list = []
    if instrument_id is not None:
        clauses.append("instrument_id = ?")
        params.append(instrument_id)
    if sector is not None:
        clauses.append("sector = ?")
        params.append(sector)
    if strategy_tag is not None:
        clauses.append("strategy_tag = ?")
        params.append(strategy_tag)

    if not clauses:
        return []

    query = (
        f"SELECT * FROM decision_log WHERE ({' OR '.join(clauses)}) "
        "ORDER BY created_at DESC, id DESC LIMIT ?"
    )
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# thesis_tracker
# ---------------------------------------------------------------------------


def open_thesis(
    conn: sqlite3.Connection,
    *,
    instrument_id: int,
    decision_id: int,
    thesis_text: str,
    invalidation_condition: str,
) -> int:
    """Open a new ACTIVE thesis. Returns the new thesis id."""
    today = dt.date.today().isoformat()
    cur = conn.execute(
        """
        INSERT INTO thesis_tracker
            (instrument_id, decision_id, thesis_text, invalidation_condition,
             status, opened_date, last_checked)
        VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)
        """,
        (instrument_id, decision_id, thesis_text, invalidation_condition, today, today),
    )
    conn.commit()
    return cur.lastrowid


def set_status(conn: sqlite3.Connection, id: int, status: str, last_checked: str | None = None) -> None:
    """Update a thesis's status (ACTIVE|WATCH|INVALIDATED|CLOSED) and last_checked date."""
    if status not in ("ACTIVE", "WATCH", "INVALIDATED", "CLOSED"):
        raise ValueError(f"status must be ACTIVE|WATCH|INVALIDATED|CLOSED, got {status!r}")
    last_checked = last_checked or dt.date.today().isoformat()
    conn.execute(
        "UPDATE thesis_tracker SET status = ?, last_checked = ? WHERE id = ?",
        (status, last_checked, id),
    )
    conn.commit()


def active_theses(conn: sqlite3.Connection) -> list[dict]:
    """All theses with status ACTIVE or WATCH (the ones position monitoring
    needs to keep an eye on), most-recently-opened first."""
    rows = conn.execute(
        """
        SELECT * FROM thesis_tracker
         WHERE status IN ('ACTIVE', 'WATCH')
         ORDER BY opened_date DESC, id DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# knowledge_base
# ---------------------------------------------------------------------------


def add_note(
    conn: sqlite3.Connection,
    *,
    tag_type: str,
    tag_value: str,
    content: str,
    source_ref: str | None = None,
) -> int:
    """Insert a new knowledge_base note. Returns the new note id."""
    if tag_type not in ("INSTRUMENT", "SECTOR", "MACRO", "SITUATION"):
        raise ValueError(f"tag_type must be INSTRUMENT|SECTOR|MACRO|SITUATION, got {tag_type!r}")
    cur = conn.execute(
        """
        INSERT INTO knowledge_base (tag_type, tag_value, content, source_ref, created_at, superseded)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (tag_type, tag_value, content, source_ref, _now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def get_notes(conn: sqlite3.Connection, tag_type: str, tag_value: str, limit: int = 10) -> list[dict]:
    """Most-recent-first, non-superseded notes for one (tag_type, tag_value)."""
    rows = conn.execute(
        """
        SELECT * FROM knowledge_base
         WHERE tag_type = ? AND tag_value = ? AND superseded = 0
         ORDER BY created_at DESC, id DESC
         LIMIT ?
        """,
        (tag_type, tag_value, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def supersede(conn: sqlite3.Connection, note_id: int) -> None:
    """Mark a note as superseded (excluded from future get_notes() results,
    kept for audit history rather than deleted)."""
    conn.execute("UPDATE knowledge_base SET superseded = 1 WHERE id = ?", (note_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# lessons
# ---------------------------------------------------------------------------


def propose_lesson(
    conn: sqlite3.Connection,
    *,
    heuristic: str,
    context_tag: str,
    evidence_json: dict | list | str | None,
    confidence: float,
) -> int:
    """Insert a new proposed (not yet human-approved) lesson. Returns the new id."""
    if isinstance(evidence_json, (dict, list)):
        evidence_json = json.dumps(evidence_json)
    cur = conn.execute(
        """
        INSERT INTO lessons (heuristic, context_tag, evidence_json, confidence, approved_by_human, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (heuristic, context_tag, evidence_json, confidence, _now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def approve_lesson(conn: sqlite3.Connection, id: int) -> None:
    """Human approval gate: flips approved_by_human to 1."""
    conn.execute("UPDATE lessons SET approved_by_human = 1 WHERE id = ?", (id,))
    conn.commit()


def lessons_for(conn: sqlite3.Connection, context_tag: str, approved_only: bool = True) -> list[dict]:
    """Lessons matching a context_tag, most-recent-first. Approved-only by default."""
    if approved_only:
        rows = conn.execute(
            """
            SELECT * FROM lessons
             WHERE context_tag = ? AND approved_by_human = 1
             ORDER BY created_at DESC, id DESC
            """,
            (context_tag,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM lessons WHERE context_tag = ? ORDER BY created_at DESC, id DESC",
            (context_tag,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------------


def record_prediction(
    conn: sqlite3.Connection, *, decision_id: int, predicted_outcome: str, predicted_prob: float
) -> int:
    """Insert a new calibration row for a decision (realized fields left NULL
    until record_outcome() is called). Returns the new calibration id."""
    cur = conn.execute(
        """
        INSERT INTO calibration (decision_id, predicted_outcome, predicted_prob, realized_outcome, realized_at)
        VALUES (?, ?, ?, NULL, NULL)
        """,
        (decision_id, predicted_outcome, predicted_prob),
    )
    conn.commit()
    return cur.lastrowid


def record_outcome(conn: sqlite3.Connection, id: int, realized_outcome: str, realized_at: str | None = None) -> None:
    """Stamp a calibration row with what actually happened."""
    realized_at = realized_at or dt.date.today().isoformat()
    conn.execute(
        "UPDATE calibration SET realized_outcome = ?, realized_at = ? WHERE id = ?",
        (realized_outcome, realized_at, id),
    )
    conn.commit()


def brier_score(conn: sqlite3.Connection, period_start: str, period_end: str) -> float | None:
    """Brier score over calibration rows realized within [period_start, period_end].

    Outcome-encoding convention: predicted_prob is the model's probability
    that predicted_outcome occurs; the realized binary label is 1 if
    realized_outcome == predicted_outcome (the prediction "came true" exactly
    as stated), else 0. This treats predicted_outcome as a single stated
    scenario (e.g. "thesis plays out", "stock up >10% in 90d") — the caller
    is responsible for making predicted_outcome and realized_outcome directly
    comparable strings. Brier score = mean((predicted_prob - binary_label)^2)
    over all rows with a non-null realized_outcome/realized_at in the window;
    lower is better (0 = perfect, 1 = worst possible).

    Returns None if there are no qualifying rows (nothing to score).
    """
    rows = conn.execute(
        """
        SELECT predicted_outcome, predicted_prob, realized_outcome
          FROM calibration
         WHERE realized_at IS NOT NULL
           AND realized_at >= ? AND realized_at <= ?
        """,
        (period_start, period_end),
    ).fetchall()

    if not rows:
        return None

    squared_errors = []
    for row in rows:
        if row["predicted_prob"] is None:
            continue
        binary_label = 1.0 if row["realized_outcome"] == row["predicted_outcome"] else 0.0
        squared_errors.append((row["predicted_prob"] - binary_label) ** 2)

    if not squared_errors:
        return None
    return sum(squared_errors) / len(squared_errors)


def calibration_counts(conn: sqlite3.Connection, period_start: str, period_end: str) -> dict:
    """Prediction volume/resolution counts for calibration rows CREATED within
    [period_start, period_end] (matched on the calibration row's decision's
    decision_date, since calibration itself has no created_at column) —
    n_predictions (total rows in the window), n_resolved (realized_at is not
    null), n_pending (realized_at is null). Used by the meta_research packet
    alongside brier_score() (which scores by realized_at instead — a
    deliberately different window semantic, since a prediction can be made in
    one period and resolved in a later one).

    Returns {"n_predictions": int, "n_resolved": int, "n_pending": int}.
    """
    rows = conn.execute(
        """
        SELECT c.realized_at
          FROM calibration c
          JOIN decision_log d ON d.id = c.decision_id
         WHERE d.decision_date >= ? AND d.decision_date <= ?
        """,
        (period_start, period_end),
    ).fetchall()

    n_predictions = len(rows)
    n_resolved = sum(1 for r in rows if r["realized_at"] is not None)
    return {
        "n_predictions": n_predictions,
        "n_resolved": n_resolved,
        "n_pending": n_predictions - n_resolved,
    }


def record_outcome_for_decision(
    conn: sqlite3.Connection, decision_id: int, realized_outcome: str, realized_at: str | None = None
) -> int:
    """Convenience wrapper: find the calibration row(s) for `decision_id` and
    stamp them with the realized outcome via record_outcome(). If more than
    one calibration row exists for the decision (multiple predictions logged
    against the same decision), all are updated. Returns the number of rows
    updated. Raises ValueError if no calibration row exists for decision_id —
    callers should record_prediction() first."""
    rows = conn.execute(
        "SELECT id FROM calibration WHERE decision_id = ?", (decision_id,)
    ).fetchall()
    if not rows:
        raise ValueError(f"No calibration row(s) found for decision_id={decision_id}")
    for row in rows:
        record_outcome(conn, row["id"], realized_outcome, realized_at=realized_at)
    return len(rows)
