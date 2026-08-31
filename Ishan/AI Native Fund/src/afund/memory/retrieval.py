"""Scoped, budgeted recall across the memory stores.

This is the token-frugality gate for anything Memory hands to an agent
packet: `get_slices()` NEVER returns an unscoped dump. It only returns
content tagged to the instrument/symbol given, that instrument's sector, or
an explicit situation tag — and it stops adding items the moment the
running character budget would be exceeded, rather than truncating content
mid-item.
"""
from __future__ import annotations

import sqlite3

from afund.memory import stores

DEFAULT_BUDGET_CHARS = 8000


def _item_chars(item: dict) -> int:
    """Rough char count for one memory item — sum of all string field values,
    used consistently by both the running total and truncation checks."""
    total = 0
    for v in item.values():
        if isinstance(v, str):
            total += len(v)
        else:
            total += len(str(v))
    return total


def _resolve_sector(conn: sqlite3.Connection, instrument_id: int | None) -> str | None:
    if instrument_id is None:
        return None
    row = conn.execute("SELECT sector FROM instruments WHERE id = ?", (instrument_id,)).fetchone()
    return row["sector"] if row and row["sector"] else None


def _resolve_symbol_tag(conn: sqlite3.Connection, instrument_id: int | None, symbol: str | None) -> str | None:
    """The INSTRUMENT tag_value to use for knowledge_base lookups — prefers
    the explicit symbol if given, else resolves it from instrument_id."""
    if symbol is not None:
        return symbol
    if instrument_id is not None:
        row = conn.execute("SELECT symbol FROM instruments WHERE id = ?", (instrument_id,)).fetchone()
        return row["symbol"] if row else None
    return None


def get_slices(
    conn: sqlite3.Connection,
    *,
    instrument_id: int | None = None,
    symbol: str | None = None,
    sector: str | None = None,
    situation: str | None = None,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
) -> dict:
    """Return budgeted, tag-scoped memory slices.

    Scoping rule: only content tagged to the instrument (by symbol), its
    sector, or the given situation tag is eligible — never a global dump.
    If NO tags are given at all (no instrument_id, no symbol, no sector, no
    situation), every slice is returned empty.

    Ordering: most-recent-first within each store. Items are added across
    all four content slices (knowledge_notes, lessons, precedents,
    active_theses) in that priority order, stopping the moment adding the
    next item would push the running char total over budget_chars — a hard
    budget, not a per-slice one.

    Returns:
        {
          "knowledge_notes": [...], "lessons": [...], "precedents": [...],
          "active_theses": [...], "approx_tokens": int,
        }
    """
    result: dict = {
        "knowledge_notes": [],
        "lessons": [],
        "precedents": [],
        "active_theses": [],
        "approx_tokens": 0,
    }

    resolved_sector = sector or _resolve_sector(conn, instrument_id)
    resolved_symbol = _resolve_symbol_tag(conn, instrument_id, symbol)

    if not any([instrument_id, resolved_symbol, resolved_sector, situation]):
        return result

    running_chars = 0

    def _budget_remaining() -> int:
        return budget_chars - running_chars

    def _add_items(dest_key: str, items: list[dict]) -> bool:
        """Append items to result[dest_key] until budget is exhausted.
        Returns True if the budget was exhausted (caller can stop early)."""
        nonlocal running_chars
        for item in items:
            size = _item_chars(item)
            if running_chars + size > budget_chars:
                return True
            result[dest_key].append(item)
            running_chars += size
        return False

    # --- knowledge_base notes: instrument, then sector, then situation -----
    kb_candidates: list[dict] = []
    seen_ids: set[int] = set()

    def _extend_kb(rows: list[dict]) -> None:
        for row in rows:
            if row["id"] not in seen_ids:
                seen_ids.add(row["id"])
                kb_candidates.append(row)

    if resolved_symbol:
        _extend_kb(stores.get_notes(conn, "INSTRUMENT", resolved_symbol, limit=10))
    if resolved_sector:
        _extend_kb(stores.get_notes(conn, "SECTOR", resolved_sector, limit=10))
    if situation:
        _extend_kb(stores.get_notes(conn, "SITUATION", situation, limit=10))
    # Re-sort the merged candidate pool most-recent-first (each per-tag query
    # was already sorted, but merging tag groups needs a final re-sort).
    kb_candidates.sort(key=lambda r: (r.get("created_at") or "", r.get("id") or 0), reverse=True)

    if _add_items("knowledge_notes", kb_candidates):
        result["approx_tokens"] = running_chars // 4
        return result

    # --- lessons: context_tag matched against sector/situation/symbol ------
    lesson_candidates: list[dict] = []
    seen_lesson_ids: set[int] = set()
    for tag in filter(None, [resolved_symbol, resolved_sector, situation]):
        for row in stores.lessons_for(conn, tag, approved_only=True):
            if row["id"] not in seen_lesson_ids:
                seen_lesson_ids.add(row["id"])
                lesson_candidates.append(row)
    lesson_candidates.sort(key=lambda r: (r.get("created_at") or "", r.get("id") or 0), reverse=True)

    if _add_items("lessons", lesson_candidates):
        result["approx_tokens"] = running_chars // 4
        return result

    # --- decision_log precedents: instrument or sector ----------------------
    precedents = stores.get_precedents(
        conn, instrument_id=instrument_id, sector=resolved_sector, limit=5
    )
    if _add_items("precedents", precedents):
        result["approx_tokens"] = running_chars // 4
        return result

    # --- active theses: filtered to this instrument only -------------------
    if instrument_id is not None:
        theses = [t for t in stores.active_theses(conn) if t["instrument_id"] == instrument_id]
        _add_items("active_theses", theses)

    result["approx_tokens"] = running_chars // 4
    return result
