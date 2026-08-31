"""narrative_intensity agent packet builder (source doc section 2.5).

This module builds the CONTEXT PACKET the narrative_intensity agent reads
— it does NOT call an LLM and does NOT compute a Narrative Intensity Score
itself (that's the agent's own qualitative judgment, validated afterward
via afund.agents.contracts.NarrativeIntensityOutput). Pure packet assembly:
sanitized news_items (tag-matched to the scope), MACRO knowledge_base
notes, and the computed quantitative phase for the scope, all budget-capped.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass, field

from afund.agents.sanitize import sanitize_untrusted

DEFAULT_NEWS_LIMIT = 15
DEFAULT_NOTES_LIMIT = 10
DEFAULT_BUDGET_CHARS = 14000  # mirrors config/settings.yaml packet_budgets.narrative_intensity


@dataclass
class NarrativePacket:
    scope: str
    as_of_date: str
    quant_phase_id: str | None
    quant_percentile: float | None
    quant_directional_lean: int | None
    news_items: list[dict] = field(default_factory=list)
    macro_notes: list[dict] = field(default_factory=list)
    sanitize_flags: list[str] = field(default_factory=list)
    approx_tokens: int = 0
    truncation_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "as_of_date": self.as_of_date,
            "quant_phase_id": self.quant_phase_id,
            "quant_percentile": self.quant_percentile,
            "quant_directional_lean": self.quant_directional_lean,
            "news_items": self.news_items,
            "macro_notes": self.macro_notes,
            "sanitize_flags": self.sanitize_flags,
            "approx_tokens": self.approx_tokens,
            "truncation_notes": self.truncation_notes,
        }


def _fetch_relevant_news(conn: sqlite3.Connection, scope: str, limit: int) -> list[sqlite3.Row]:
    """News rows tag-matched to the scope (tag ILIKE-equivalent match on the
    registry sector slug / index name / 'market'), most recent first."""
    like_pattern = f"%{scope}%"
    rows = conn.execute(
        """
        SELECT id, event_scope, tag, impact, description, event_date, source, raw_title
          FROM news_items
         WHERE (tag LIKE ? OR event_scope = 'MACRO')
         ORDER BY event_date DESC
         LIMIT ?
        """,
        (like_pattern, limit),
    ).fetchall()
    return rows


def _fetch_macro_notes(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT id, tag_value, content, source_ref, created_at
          FROM knowledge_base
         WHERE tag_type = 'MACRO' AND superseded = 0
         ORDER BY created_at DESC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return rows


def build_narrative_packet(
    conn: sqlite3.Connection,
    *,
    scope: str,
    as_of_date: str | None = None,
    quant_phase_id: str | None = None,
    quant_percentile: float | None = None,
    quant_directional_lean: int | None = None,
    news_limit: int = DEFAULT_NEWS_LIMIT,
    notes_limit: int = DEFAULT_NOTES_LIMIT,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
) -> NarrativePacket:
    """Assemble the narrative_intensity agent's packet: sanitized news_items
    tag-matched to `scope`, MACRO knowledge_base notes, and the pre-computed
    quantitative phase (so the agent can reconcile qualitative narrative
    against the quant read per source doc section 2.6 — but the RECONCILE
    computation itself happens in composite.apply_reconciliation, in
    Python, after the agent's output is ingested; the agent only needs the
    quant phase as read-only context, never asked to redo the reconciliation
    math itself)."""
    as_of_date = as_of_date or dt.date.today().isoformat()

    packet = NarrativePacket(
        scope=scope,
        as_of_date=as_of_date,
        quant_phase_id=quant_phase_id,
        quant_percentile=quant_percentile,
        quant_directional_lean=quant_directional_lean,
    )

    news_rows = _fetch_relevant_news(conn, scope, news_limit)
    running_chars = 0
    for row in news_rows:
        raw_title = row["raw_title"] or ""
        wrapped, flags = sanitize_untrusted(raw_title, source_ref=f"news_items.id={row['id']}", max_chars=500)
        item = {
            "id": row["id"],
            "event_scope": row["event_scope"],
            "tag": row["tag"],
            "impact": row["impact"],
            "description": row["description"],
            "event_date": row["event_date"],
            "source": row["source"],
            "raw_title_sanitized": wrapped,
        }
        item_chars = sum(len(str(v)) for v in item.values())
        if running_chars + item_chars > budget_chars * 0.6:
            packet.truncation_notes.append(
                f"news_items truncated at {len(packet.news_items)} of {len(news_rows)} available (budget)"
            )
            break
        packet.news_items.append(item)
        packet.sanitize_flags.extend(flags)
        running_chars += item_chars

    notes_rows = _fetch_macro_notes(conn, notes_limit)
    for row in notes_rows:
        note = {
            "id": row["id"],
            "tag_value": row["tag_value"],
            "content": row["content"],
            "source_ref": row["source_ref"],
            "created_at": row["created_at"],
        }
        note_chars = sum(len(str(v)) for v in note.values())
        if running_chars + note_chars > budget_chars * 0.9:
            packet.truncation_notes.append(
                f"macro_notes truncated at {len(packet.macro_notes)} of {len(notes_rows)} available (budget)"
            )
            break
        packet.macro_notes.append(note)
        running_chars += note_chars

    packet.approx_tokens = running_chars // 4  # rough chars-to-tokens heuristic, matches context.py convention
    return packet
