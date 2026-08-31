"""build_packet() — the token-frugality workhorse.

Assembles the SMALLEST sufficient context packet for one agent role/step:
compact regime signals, a relevant registry slice (never the whole
registry), a computed (never raw-series) price summary, budget-scoped
memory slices, the prior role's output verbatim, and (for news_processor)
a capped batch of unprocessed news_items. Every packet is written to
data/packets/{batch_id}/{seq:02d}_{role}.json and enforced against a
per-role character budget from config/settings.yaml -> packet_budgets.

Nothing here calls an LLM. This module's only job is deciding what bytes an
agent gets to see.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from afund.agents.sanitize import embed_untrusted, sanitize_untrusted
from afund.config import REPO_ROOT, load_settings
from afund.derive.regime import evaluate_regime
from afund.derive.returns import cagr, trailing_return
from afund.cycles.funnel import run_funnel
from afund.derive.technicals import compute_technicals
from afund.memory import retrieval

sys_path_registry_added = False


def _load_registry():
    """Lazy import of registry.registry.Registry — registry/ lives at the
    repo root, not under src/, so this mirrors the sys.path bootstrap other
    entry points (scripts/init_db.py, tests) use."""
    global sys_path_registry_added
    if not sys_path_registry_added:
        import sys

        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        sys_path_registry_added = True
    from registry.registry import Registry

    return Registry


PACKETS_DIR = REPO_ROOT / "data" / "packets"

DEFAULT_BUDGET_CHARS = 12000

# Roles that get the relevant sector's KPI slice (research/idea/synthesis/critique family).
KPI_SLICE_ROLES = {
    "research_head",
    "equity_researcher",
    "sector_researcher",
    "idea_gen",
    "synthesis",
    "critique",
}

# Roles that get risk_limits rules instead of a KPI slice.
RISK_RULES_ROLES = {"risk_mgmt", "allocator", "fund_manager"}

# Roles that get strategy definitions (in addition to whatever else applies).
STRATEGY_ROLES = {"idea_gen", "fund_manager"}

MAX_NEWS_PENDING_ITEMS = 40

# Canonical mapping lives in afund.sectors (single definition, no layering
# issues). Re-exported here because sector_assembler and older callers import
# it from this module.
from afund.sectors import SECTOR_TO_KPI_KEY, kpi_key_for_sector as _kpi_key_for_sector  # noqa: E402


# Roles whose packet is built from Memory's episodic/calibration record for a
# fixed calendar period rather than from an instrument/regime slice.
PERIOD_ROLES = {"meta_research"}

# Roles that get a compact cycle_context slice (latest composite_decisions +
# sector cycle_assessments phases) — Phase 7 cycle engine light wiring.
CYCLE_CONTEXT_ROLES = {"risk_mgmt", "allocator", "idea_gen"}

# narrative_intensity is scope-based (a cycle-assessment scope like "NIFTY 50"
# or a sector slug like "bfsi"), not instrument/symbol-based — its packet is
# built entirely from afund.cycles.narrative.build_narrative_packet rather
# than the instrument/regime/registry machinery below.
NARRATIVE_INTENSITY_ROLE = "narrative_intensity"

MAX_META_DECISION_ROWS = 50
MIN_DECISION_ROWS_FOR_SUFFICIENT_DATA = 5

_QUARTER_START_MONTH = {1: 1, 2: 4, 3: 7, 4: 10}
_QUARTER_END_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}


def parse_period(period: str) -> tuple[str, str]:
    """Parse a period string into an inclusive (start_date, end_date) ISO
    date pair.

    Supported shapes:
      "YYYY-QN"  — calendar quarter, e.g. "2026-Q2" -> (2026-04-01, 2026-06-30)
      "YYYY-MM"  — calendar month, e.g. "2026-06"   -> (2026-06-01, 2026-06-30)
      "YYYY"     — calendar year,  e.g. "2026"      -> (2026-01-01, 2026-12-31)

    Raises ValueError for anything else.
    """
    import calendar

    text = period.strip().upper()

    if "-Q" in text:
        year_str, q_str = text.split("-Q", 1)
        try:
            year = int(year_str)
            quarter = int(q_str)
        except ValueError as exc:
            raise ValueError(f"Invalid period {period!r}: expected YYYY-QN") from exc
        if quarter not in _QUARTER_START_MONTH:
            raise ValueError(f"Invalid period {period!r}: quarter must be 1-4")
        start_month = _QUARTER_START_MONTH[quarter]
        end_month = _QUARTER_END_MONTH[quarter]
        start = dt.date(year, start_month, 1)
        end = dt.date(year, end_month, calendar.monthrange(year, end_month)[1])
        return start.isoformat(), end.isoformat()

    if "-" in text:
        year_str, month_str = text.split("-", 1)
        try:
            year = int(year_str)
            month = int(month_str)
        except ValueError as exc:
            raise ValueError(f"Invalid period {period!r}: expected YYYY-MM") from exc
        if not (1 <= month <= 12):
            raise ValueError(f"Invalid period {period!r}: month must be 1-12")
        start = dt.date(year, month, 1)
        end = dt.date(year, month, calendar.monthrange(year, month)[1])
        return start.isoformat(), end.isoformat()

    try:
        year = int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid period {period!r}: expected YYYY-QN, YYYY-MM, or YYYY") from exc
    return dt.date(year, 1, 1).isoformat(), dt.date(year, 12, 31).isoformat()


@dataclass
class Packet:
    role: str
    trigger: str
    as_of: str
    regime: dict
    registry_slice: dict
    price_summary: dict
    memory: dict
    prior_output: dict | None
    pending_items: list | None
    approx_tokens: int = 0
    truncation_notes: list[str] = field(default_factory=list)
    sanitize_flags: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {
            "role": self.role,
            "trigger": self.trigger,
            "as_of": self.as_of,
            "regime": self.regime,
            "registry_slice": self.registry_slice,
            "price_summary": self.price_summary,
            "memory": self.memory,
            "prior_output": self.prior_output,
            "pending_items": self.pending_items,
            "approx_tokens": self.approx_tokens,
            "truncation_notes": self.truncation_notes,
            "sanitize_flags": self.sanitize_flags,
        }
        out.update(self.extra)
        return out


def _packet_budget_chars(role: str) -> int:
    settings = load_settings()
    budgets = settings.get("packet_budgets", {}) or {}
    return int(budgets.get(role, budgets.get("default", DEFAULT_BUDGET_CHARS)))


def _compact_regime(conn: sqlite3.Connection) -> dict:
    """Compact regime dict for NIFTY 50 + NIFTY 500 — signals + headline
    numbers only, never a raw series."""
    out = {}
    for index_name in ("NIFTY 50", "NIFTY 500"):
        r = evaluate_regime(conn, index_name)
        out[index_name] = {
            "pe": r["pe"],
            "pe_percentile_5y": r["pe_percentile_5y"],
            "ret_1y": r["ret_1y"],
            "cagr_5y": r["cagr_5y"],
            "signals": r["signals"],
            "insufficient_history": r["insufficient_history"],
        }
    return out


def _instrument_price_summary(conn: sqlite3.Connection, instrument_id: int) -> dict:
    """Computed price summary for one instrument — last close, 1m/1y return,
    52w hi/lo distance, 50/200 DMA position. Never a raw price series."""
    technicals = compute_technicals(conn, instrument_id=instrument_id)
    ret_1m = trailing_return(conn, instrument_id=instrument_id, years=1 / 12)
    ret_1y = trailing_return(conn, instrument_id=instrument_id, years=1.0)
    cagr_5y = cagr(conn, instrument_id=instrument_id, years=5.0)

    last_close = technicals["last_close"]
    dma_50 = technicals["dma_50"]
    dma_200 = technicals["dma_200"]

    above_50dma = None
    above_200dma = None
    if last_close is not None and dma_50 is not None:
        above_50dma = last_close >= dma_50
    if last_close is not None and dma_200 is not None:
        above_200dma = last_close >= dma_200

    return {
        "last_close": last_close,
        "last_date": technicals["last_date"],
        "ret_1m": ret_1m,
        "ret_1y": ret_1y,
        "cagr_5y": cagr_5y,
        "pct_from_52w_high": technicals["pct_from_52w_high"],
        "pct_from_52w_low": technicals["pct_from_52w_low"],
        "above_50dma": above_50dma,
        "above_200dma": above_200dma,
    }


def _resolve_instrument(conn: sqlite3.Connection, instrument_id: int | None, symbol: str | None) -> sqlite3.Row | None:
    if instrument_id is not None:
        return conn.execute("SELECT * FROM instruments WHERE id = ?", (instrument_id,)).fetchone()
    if symbol is not None:
        return conn.execute(
            "SELECT * FROM instruments WHERE symbol = ? ORDER BY id LIMIT 1", (symbol,)
        ).fetchone()
    return None


def _registry_slice_for_role(role: str, kpi_key: str) -> dict:
    """Build the role-appropriate registry slice: KPI sector set, risk
    rules, and/or strategy definitions, per the role -> content mapping."""
    Registry = _load_registry()
    reg = Registry.load()
    slice_: dict = {}

    if role in KPI_SLICE_ROLES:
        kpi_set = reg.kpis.get(kpi_key) or reg.kpis.get("generic")
        if kpi_set is not None:
            slice_["kpi_set"] = kpi_set.model_dump()

    if role in RISK_RULES_ROLES:
        slice_["risk_limits"] = reg.rules.model_dump()

    if role in STRATEGY_ROLES:
        slice_["strategies"] = {sid: s.model_dump() for sid, s in reg.strategies.items()}

    slice_["registry_version"] = reg.version
    return slice_


def _build_cycle_context(conn: sqlite3.Connection, *, scope: str | None, sector: str | None) -> dict | None:
    """Compact Phase 7 cycle-engine slice for risk_mgmt/allocator/idea_gen:
    the latest composite_decisions row for the relevant scope(s) plus each
    live (non-data_pending) cycle_assessments phase for that scope. Never
    the raw history — just the latest as_of_date's row. Returns None if the
    cycle_assessments/composite_decisions tables have no rows yet for any
    resolved scope (tables exist from Phase 0 migration, but may be empty
    before the first weekly_cycle_assessment run)."""
    candidate_scopes = []
    if scope:
        candidate_scopes.append(scope)
    if sector:
        candidate_scopes.append(sector)
    candidate_scopes.extend(["NIFTY 500", "NIFTY 50"])
    # de-dup, preserving order
    seen = set()
    scopes = [s for s in candidate_scopes if s and not (s in seen or seen.add(s))]

    for candidate in scopes:
        composite_row = conn.execute(
            """
            SELECT scope, as_of_date, regime_cluster, regime_unknown, composite_score,
                   alignment_score, evi_value, evi_components_missing_json,
                   recommended_action, requires_human_review
              FROM composite_decisions
             WHERE scope = ?
             ORDER BY as_of_date DESC
             LIMIT 1
            """,
            (candidate,),
        ).fetchone()
        if composite_row is None:
            continue

        phase_rows = conn.execute(
            """
            SELECT cycle_id, phase_id, directional_lean, percentile, data_pending
              FROM cycle_assessments
             WHERE scope = ? AND as_of_date = ?
             ORDER BY cycle_id ASC
            """,
            (candidate, composite_row["as_of_date"]),
        ).fetchall()

        return {
            "scope": composite_row["scope"],
            "as_of_date": composite_row["as_of_date"],
            "regime_cluster": composite_row["regime_cluster"],
            "regime_unknown": bool(composite_row["regime_unknown"]),
            "composite_score": composite_row["composite_score"],
            "alignment_score": composite_row["alignment_score"],
            "evi_value": composite_row["evi_value"],
            "evi_components_missing": json.loads(composite_row["evi_components_missing_json"] or "[]"),
            "recommended_action": composite_row["recommended_action"],
            "requires_human_review": bool(composite_row["requires_human_review"]),
            "cycles": [
                {
                    "cycle_id": r["cycle_id"],
                    "phase_id": r["phase_id"],
                    "directional_lean": r["directional_lean"],
                    "percentile": r["percentile"],
                }
                for r in phase_rows
                if not r["data_pending"]
            ],
        }

    return None


def _resolve_premortem_requirement(conn: sqlite3.Connection, *, scope: str | None, sector: str | None) -> dict:
    """Phase 10: does critique's packet need to flag requires_premortem=True?

    Reads the latest valuation_cycle cycle_assessments row's
    reconciliation_flags_json for the resolved scope (sector -> NIFTY 500 ->
    NIFTY 50 fallback, same order used elsewhere in this module) and surfaces
    its requires_premortem/contrarian_sweet_spot flags verbatim. Per
    cycle_framework.yaml governance.premortem_trigger, requires_premortem is
    also true for any new high-conviction position regardless of the
    reconciliation quadrant, but this function only sees the reconciliation
    signal — the "new high-conviction position" half of that trigger isn't
    knowable at critique time (conviction/size come later), so it's left for
    fund_manager's own judgment checklist to catch, not asserted here.

    Returns {"requires_premortem": bool, "reconciliation_quadrant": str|None,
    "flags": dict, "scope_used": str|None} — never raises; an empty/unknown
    result (no cycle_assessments row for any fallback scope) reads
    requires_premortem=False with scope_used=None rather than erroring, since
    a missing reconciliation read should never block a critique from running.
    """
    candidate_scopes = []
    if scope:
        candidate_scopes.append(scope)
    if sector:
        candidate_scopes.append(sector)
    candidate_scopes.extend(["NIFTY 500", "NIFTY 50"])
    seen: set[str] = set()
    scopes = [s for s in candidate_scopes if s and not (s in seen or seen.add(s))]

    for candidate in scopes:
        row = conn.execute(
            """
            SELECT reconciliation_quadrant, reconciliation_flags_json
              FROM cycle_assessments
             WHERE cycle_id = 'valuation_cycle' AND scope = ? AND data_pending = 0
             ORDER BY as_of_date DESC LIMIT 1
            """,
            (candidate,),
        ).fetchone()
        if row is None:
            continue
        flags = json.loads(row["reconciliation_flags_json"] or "{}")
        return {
            "requires_premortem": bool(flags.get("requires_premortem", False)),
            "reconciliation_quadrant": row["reconciliation_quadrant"],
            "flags": flags,
            "scope_used": candidate,
        }

    return {"requires_premortem": False, "reconciliation_quadrant": None, "flags": {}, "scope_used": None}


def _compact_funnel(funnel: dict) -> dict:
    """Slim afund.cycles.funnel.run_funnel()'s output down to what idea_gen
    actually needs: per-candidate gate RESULTS (not the full nested detail
    dicts — e.g. gate1's scope_used/as_of_date, gate2's note text) plus the
    handful of screener fields idea_gen reasons over. Keeps packets small
    without losing the "why did/didn't this clear" signal."""
    candidates = []
    for c in funnel["candidates"]:
        gates = c["gates"]
        candidates.append({
            "instrument_id": c["instrument_id"],
            "symbol": c["symbol"],
            "sector": c["sector"],
            "ret_1y": c["ret_1y"],
            "cagr_5y": c["cagr_5y"],
            "pe": c.get("pe"),
            "roce": c.get("roce"),
            "roe": c.get("roe"),
            "gate1_result": gates["gate1_quant_cycle"]["result"],
            "gate1_phase": gates["gate1_quant_cycle"].get("phase_id"),
            "gate2_quality": gates["gate2_quality"]["quality"],
            "gate3_percentile": gates["gate3_idiosyncratic"]["percentile"],
            "gate3_proxy": gates["gate3_idiosyncratic"]["proxy_used"],
            "gate4_result": gates["gate4_neglect"]["result"],
            "gate4_reason": gates["gate4_neglect"]["reason"],
            "gates_passed": c["gates_passed"],
        })
    return {
        "as_of": funnel["as_of"],
        "universe_scanned": funnel["universe_scanned"],
        "candidates": candidates,
    }


def _pending_news_items(conn: sqlite3.Connection, limit: int = MAX_NEWS_PENDING_ITEMS) -> tuple[list[dict], list[str]]:
    """Pending (processed=0) news_items rows, with each item's raw_title run
    through sanitize_untrusted() (raw_title is untrusted external text —
    scraped headlines). Returns (items, sanitize_flags)."""
    rows = conn.execute(
        """
        SELECT id, raw_title, source, event_date, url
          FROM news_items
         WHERE processed = 0
         ORDER BY fetched_at ASC, id ASC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()
    items = [dict(r) for r in rows]
    all_flags: list[str] = []
    for item in items:
        source_ref = item.get("url") or item.get("source") or f"news_item:{item.get('id')}"
        wrapped, flags = sanitize_untrusted(item.get("raw_title") or "", source_ref)
        item["raw_title"] = wrapped
        if flags:
            all_flags.extend(f"news_item id={item.get('id')}: {f}" for f in flags)
    return items, all_flags


def _meta_episodic_summary(conn: sqlite3.Connection, period_start: str, period_end: str) -> tuple[list[dict], bool]:
    """Compact decision_log rows in [period_start, period_end], capped at
    MAX_META_DECISION_ROWS (most recent first). Returns (rows,
    insufficient_data) where insufficient_data is True if the TOTAL row
    count in the period (before capping) is under
    MIN_DECISION_ROWS_FOR_SUFFICIENT_DATA."""
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM decision_log WHERE decision_date >= ? AND decision_date <= ?",
        (period_start, period_end),
    ).fetchone()["c"]

    rows = conn.execute(
        """
        SELECT id, decision_date, instrument_id, action, strategy_tag,
               human_decision, human_notes
          FROM decision_log
         WHERE decision_date >= ? AND decision_date <= ?
         ORDER BY decision_date DESC, id DESC
         LIMIT ?
        """,
        (period_start, period_end, MAX_META_DECISION_ROWS),
    ).fetchall()

    summary = []
    for row in rows:
        instrument_symbol = None
        if row["instrument_id"] is not None:
            inst = conn.execute(
                "SELECT symbol FROM instruments WHERE id = ?", (row["instrument_id"],)
            ).fetchone()
            instrument_symbol = inst["symbol"] if inst else None
        summary.append(
            {
                "decision_id": row["id"],
                "decision_date": row["decision_date"],
                "action": row["action"],
                "instrument": instrument_symbol,
                "strategy_tag": row["strategy_tag"],
                "human_decision": row["human_decision"],
                "human_notes": row["human_notes"],
            }
        )

    return summary, total < MIN_DECISION_ROWS_FOR_SUFFICIENT_DATA


def _meta_calibration(conn: sqlite3.Connection, period_start: str, period_end: str) -> dict:
    """Calibration section: brier_score() (scored by realized_at within the
    window) plus calibration_counts() (volume, scored by decision_date within
    the window) — see stores.py docstrings for why these two use different
    window semantics."""
    from afund.memory import stores

    return {
        "brier_score": stores.brier_score(conn, period_start, period_end),
        **stores.calibration_counts(conn, period_start, period_end),
    }


def _meta_open_theses_summary(conn: sqlite3.Connection) -> dict:
    """Open thesis_tracker counts — active/watch counts, breached
    (INVALIDATED) count, and the oldest still-unchecked (ACTIVE/WATCH)
    thesis's opened_date, if any. Not period-scoped (a thesis opened before
    the review period can still be open today; meta-research needs to see
    what's currently outstanding regardless of when it was opened)."""
    from afund.memory import stores

    active = [t for t in stores.active_theses(conn) if t["status"] == "ACTIVE"]
    watch = [t for t in stores.active_theses(conn) if t["status"] == "WATCH"]
    breached_count = conn.execute(
        "SELECT COUNT(*) AS c FROM thesis_tracker WHERE status = 'INVALIDATED'"
    ).fetchone()["c"]

    open_theses = active + watch
    oldest_unchecked = None
    if open_theses:
        oldest = min(open_theses, key=lambda t: (t["opened_date"] or "", t["id"]))
        oldest_unchecked = {
            "thesis_id": oldest["id"],
            "instrument_id": oldest["instrument_id"],
            "opened_date": oldest["opened_date"],
            "last_checked": oldest["last_checked"],
        }

    return {
        "active_count": len(active),
        "watch_count": len(watch),
        "breached_count": breached_count,
        "oldest_unchecked": oldest_unchecked,
    }


def _meta_lessons_current(conn: sqlite3.Connection) -> list[dict]:
    """All currently human-approved lessons, most-recent-first."""
    rows = conn.execute(
        "SELECT * FROM lessons WHERE approved_by_human = 1 ORDER BY created_at DESC, id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def _meta_agent_quality(conn: sqlite3.Connection, period_start: str, period_end: str) -> dict:
    """Per-role agent_runs stats (run count, failure count, avg input_tokens)
    plus per-job_name job_runs failure counts, both scoped to
    [period_start, period_end] by started_at."""
    agent_rows = conn.execute(
        """
        SELECT role, status, input_tokens
          FROM agent_runs
         WHERE started_at >= ? AND started_at <= ?
        """,
        (period_start, period_end + "T23:59:59"),
    ).fetchall()

    by_role: dict[str, dict] = {}
    for row in agent_rows:
        role = row["role"]
        entry = by_role.setdefault(role, {"run_count": 0, "failure_count": 0, "_token_sum": 0, "_token_n": 0})
        entry["run_count"] += 1
        if row["status"] == "FAILED":
            entry["failure_count"] += 1
        if row["input_tokens"] is not None:
            entry["_token_sum"] += row["input_tokens"]
            entry["_token_n"] += 1

    agent_quality: dict[str, dict] = {}
    for role, entry in by_role.items():
        avg_tokens = entry["_token_sum"] / entry["_token_n"] if entry["_token_n"] else None
        agent_quality[role] = {
            "run_count": entry["run_count"],
            "failure_count": entry["failure_count"],
            "avg_input_tokens": avg_tokens,
        }

    job_rows = conn.execute(
        """
        SELECT job_name, status
          FROM job_runs
         WHERE started_at >= ? AND started_at <= ?
        """,
        (period_start, period_end + "T23:59:59"),
    ).fetchall()

    pipeline_failures: dict[str, int] = {}
    for row in job_rows:
        if row["status"] == "FAILED":
            pipeline_failures[row["job_name"]] = pipeline_failures.get(row["job_name"], 0) + 1

    return {"by_role": agent_quality, "pipeline_failure_counts": pipeline_failures}


def _meta_registry_inventory() -> dict:
    """Names (not content) of every registry rule/prompt file and agent
    definition file under review, plus the current registry version stamp."""
    Registry = _load_registry()
    reg = Registry.load()

    kpi_files = sorted(p.name for p in (REPO_ROOT / "registry" / "kpis").glob("*.yaml"))
    strategy_files = sorted(
        p.name for p in (REPO_ROOT / "registry" / "strategies").glob("*.yaml") if not p.name.startswith("_")
    )
    rule_files = sorted(p.name for p in (REPO_ROOT / "registry" / "rules").glob("*.yaml"))
    prompt_files = sorted(p.name for p in (REPO_ROOT / "registry" / "prompts").glob("*.md"))
    agent_files = sorted(p.name for p in (REPO_ROOT / ".claude" / "agents").glob("*.md"))

    return {
        "registry_version": reg.version,
        "kpi_files": kpi_files,
        "strategy_files": strategy_files,
        "rule_files": rule_files,
        "prompt_files": prompt_files,
        "agent_definition_files": agent_files,
    }


def _meta_human_decision_patterns(conn: sqlite3.Connection, period_start: str, period_end: str) -> dict:
    """approve/reject/modify counts by action type (NEW/ADD/REDUCE/EXIT/HOLD/
    MONITOR_ONLY), within the period."""
    rows = conn.execute(
        """
        SELECT action, human_decision, COUNT(*) AS c
          FROM decision_log
         WHERE decision_date >= ? AND decision_date <= ?
         GROUP BY action, human_decision
        """,
        (period_start, period_end),
    ).fetchall()

    patterns: dict[str, dict] = {}
    for row in rows:
        action = row["action"] or "UNKNOWN"
        patterns.setdefault(action, {"APPROVE": 0, "REJECT": 0, "MODIFY": 0, "PENDING": 0})
        patterns[action][row["human_decision"]] = row["c"]

    return patterns


def _build_meta_research_extra(conn: sqlite3.Connection, period: str) -> dict:
    """Assemble the meta_research packet's `extra` dict: period,
    episodic_summary, calibration, open_theses_summary, lessons_current,
    agent_quality, registry_inventory, human_decision_patterns, and an
    insufficient_episodic_data flag."""
    period_start, period_end = parse_period(period)

    episodic_summary, insufficient = _meta_episodic_summary(conn, period_start, period_end)

    return {
        "period": period,
        "period_start": period_start,
        "period_end": period_end,
        "episodic_summary": episodic_summary,
        "insufficient_episodic_data": insufficient,
        "calibration": _meta_calibration(conn, period_start, period_end),
        "open_theses_summary": _meta_open_theses_summary(conn),
        "lessons_current": _meta_lessons_current(conn),
        "agent_quality": _meta_agent_quality(conn, period_start, period_end),
        "registry_inventory": _meta_registry_inventory(),
        "human_decision_patterns": _meta_human_decision_patterns(conn, period_start, period_end),
    }


def _json_chars(obj: Any) -> int:
    return len(json.dumps(obj, default=str))


def _truncate_memory(memory: dict, budget_chars: int, current_total: int, notes: list[str]) -> tuple[dict, int]:
    """Progressively drop the tail of memory list-slices (lowest priority
    first: active_theses, then precedents, then lessons, then
    knowledge_notes) until the packet fits budget_chars, or everything in
    memory is gone."""
    order = ["active_theses", "precedents", "lessons", "knowledge_notes"]
    memory = dict(memory)
    total = current_total

    for key in order:
        while total > budget_chars and memory.get(key):
            removed = memory[key].pop()
            total -= _item_json_chars(removed)
            notes.append(f"memory.{key}: truncated 1 item for budget")
        if total <= budget_chars:
            break

    memory["approx_tokens"] = sum(
        _json_chars(memory.get(k, [])) for k in ("knowledge_notes", "lessons", "precedents", "active_theses")
    ) // 4
    return memory, total


def _item_json_chars(item: Any) -> int:
    return len(json.dumps(item, default=str))


def _build_period_scoped_packet(
    conn: sqlite3.Connection,
    *,
    role: str,
    trigger: str,
    batch_id: str,
    period: str | None,
    budget_chars: int,
    as_of: str,
) -> dict:
    """build_packet()'s branch for PERIOD_ROLES (currently just
    meta_research): no instrument/regime/registry-slice/memory machinery —
    the whole packet is the period's episodic/calibration/registry-inventory
    summary, built by _build_meta_research_extra(). `period` defaults to the
    current calendar quarter if not given."""
    if not period:
        today = dt.date.today()
        period = f"{today.year}-Q{(today.month - 1) // 3 + 1}"

    extra = _build_meta_research_extra(conn, period)

    packet = Packet(
        role=role,
        trigger=trigger,
        as_of=as_of,
        regime={},
        registry_slice={},
        price_summary={},
        memory={},
        prior_output=None,
        pending_items=None,
        extra=extra,
    )

    packet_dict = packet.to_dict()
    total_chars = _json_chars(packet_dict)
    truncation_notes: list[str] = []

    # Budget enforcement, lowest-priority-first: episodic_summary rows, then
    # lessons_current, then registry_inventory file-name lists. Each of these
    # is additive detail on top of the always-kept scalar sections
    # (calibration, open_theses_summary, human_decision_patterns,
    # insufficient_episodic_data flag).
    if total_chars > budget_chars:
        episodic = packet.extra.get("episodic_summary") or []
        while total_chars > budget_chars and episodic:
            episodic.pop()
            truncation_notes.append("episodic_summary: truncated 1 row for budget")
            packet_dict = packet.to_dict()
            total_chars = _json_chars(packet_dict)

    if total_chars > budget_chars:
        lessons = packet.extra.get("lessons_current") or []
        while total_chars > budget_chars and lessons:
            lessons.pop()
            truncation_notes.append("lessons_current: truncated 1 item for budget")
            packet_dict = packet.to_dict()
            total_chars = _json_chars(packet_dict)

    if total_chars > budget_chars:
        inventory = packet.extra.get("registry_inventory") or {}
        for key in ("kpi_files", "strategy_files", "rule_files", "prompt_files", "agent_definition_files"):
            while total_chars > budget_chars and inventory.get(key):
                inventory[key].pop()
                truncation_notes.append(f"registry_inventory.{key}: truncated 1 name for budget")
                packet_dict = packet.to_dict()
                total_chars = _json_chars(packet_dict)

    packet.truncation_notes = truncation_notes
    packet.approx_tokens = total_chars // 4
    packet_dict = packet.to_dict()

    batch_dir = PACKETS_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(batch_dir.glob("[0-9][0-9]_*.json"))
    seq = len(existing) + 1
    out_path = batch_dir / f"{seq:02d}_{role}.json"
    out_path.write_text(json.dumps(packet_dict, indent=2, default=str), encoding="utf-8")

    return {"path": str(out_path), "approx_tokens": packet.approx_tokens, "packet": packet_dict}


def _build_narrative_intensity_packet(
    conn: sqlite3.Connection,
    *,
    trigger: str,
    batch_id: str,
    scope: str | None,
    as_of: str,
) -> dict:
    """build_packet()'s branch for role="narrative_intensity": delegates the
    actual packet content to afund.cycles.narrative.build_narrative_packet
    (sanitized news + MACRO notes + the pre-computed quant phase for
    `scope`), then wraps it in the same Packet/persistence envelope every
    other role uses so downstream tooling (runner.prepare_invocation,
    --ingest-output) doesn't need a role-specific special case.

    `scope` defaults to "NIFTY 500" (the broadest market scope) if not given
    — every weekly_cycle_assessment trigger invocation is expected to pass
    an explicit scope per assessed cycle-scope, one packet per scope."""
    from afund.cycles.narrative import build_narrative_packet

    resolved_scope = scope or "NIFTY 500"
    budget_chars = _packet_budget_chars(NARRATIVE_INTENSITY_ROLE)

    quant_phase_id = quant_percentile = quant_directional_lean = None
    latest = conn.execute(
        """
        SELECT as_of_date FROM composite_decisions
         WHERE scope = ? ORDER BY as_of_date DESC LIMIT 1
        """,
        (resolved_scope,),
    ).fetchone()
    if latest is not None:
        valuation_row = conn.execute(
            """
            SELECT phase_id, percentile, directional_lean
              FROM cycle_assessments
             WHERE scope = ? AND as_of_date = ? AND cycle_id = 'valuation_cycle'
            """,
            (resolved_scope, latest["as_of_date"]),
        ).fetchone()
        if valuation_row is not None:
            quant_phase_id = valuation_row["phase_id"]
            quant_percentile = valuation_row["percentile"]
            quant_directional_lean = valuation_row["directional_lean"]

    narrative_packet = build_narrative_packet(
        conn,
        scope=resolved_scope,
        as_of_date=as_of,
        quant_phase_id=quant_phase_id,
        quant_percentile=quant_percentile,
        quant_directional_lean=quant_directional_lean,
        budget_chars=budget_chars,
    )

    packet = Packet(
        role=NARRATIVE_INTENSITY_ROLE,
        trigger=trigger,
        as_of=as_of,
        regime={},
        registry_slice={},
        price_summary={},
        memory={},
        prior_output=None,
        pending_items=None,
        extra={"narrative_packet": narrative_packet.to_dict()},
        sanitize_flags=list(narrative_packet.sanitize_flags),
        truncation_notes=list(narrative_packet.truncation_notes),
        approx_tokens=narrative_packet.approx_tokens,
    )
    packet_dict = packet.to_dict()

    batch_dir = PACKETS_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(batch_dir.glob("[0-9][0-9]_*.json"))
    seq = len(existing) + 1
    out_path = batch_dir / f"{seq:02d}_{NARRATIVE_INTENSITY_ROLE}.json"
    out_path.write_text(json.dumps(packet_dict, indent=2, default=str), encoding="utf-8")

    return {"path": str(out_path), "approx_tokens": packet.approx_tokens, "packet": packet_dict}


def build_packet(
    conn: sqlite3.Connection,
    *,
    role: str,
    trigger: str,
    instrument_id: int | None = None,
    symbol: str | None = None,
    sector: str | None = None,
    scope: str | None = None,
    prior_output: dict | None = None,
    batch_id: str,
    newsletter_text: str | None = None,
    publisher: str | None = None,
    period: str | None = None,
) -> dict:
    """Build, budget-enforce, and persist a context packet for one agent step.

    `newsletter_text` / `publisher` / `period` are only used for
    role="macro_digest"; `period` alone is required for role="meta_research"
    (see below); `scope` is only used for role="narrative_intensity" (a
    cycle-assessment scope, e.g. "NIFTY 50" or a sector slug like "bfsi") —
    every other role ignores these.

    Returns {"path": str, "approx_tokens": int, "packet": dict}.
    """
    as_of = dt.date.today().isoformat()
    budget_chars = _packet_budget_chars(role)
    truncation_notes: list[str] = []
    sanitize_flags: list[str] = []

    if role in PERIOD_ROLES:
        return _build_period_scoped_packet(
            conn, role=role, trigger=trigger, batch_id=batch_id, period=period,
            budget_chars=budget_chars, as_of=as_of,
        )

    if role == NARRATIVE_INTENSITY_ROLE:
        return _build_narrative_intensity_packet(
            conn, trigger=trigger, batch_id=batch_id, scope=scope, as_of=as_of,
        )

    instrument_row = _resolve_instrument(conn, instrument_id, symbol)
    resolved_instrument_id = instrument_row["id"] if instrument_row else instrument_id
    resolved_symbol = instrument_row["symbol"] if instrument_row else symbol
    resolved_sector = sector or (instrument_row["sector"] if instrument_row else None)

    regime = _compact_regime(conn)

    kpi_key = _kpi_key_for_sector(resolved_sector)
    registry_slice = _registry_slice_for_role(role, kpi_key)

    price_summary: dict = {}
    if resolved_instrument_id is not None:
        price_summary[resolved_symbol or str(resolved_instrument_id)] = _instrument_price_summary(
            conn, resolved_instrument_id
        )

    memory = retrieval.get_slices(
        conn,
        instrument_id=resolved_instrument_id,
        symbol=resolved_symbol,
        sector=resolved_sector,
        situation=trigger,
        budget_chars=budget_chars,  # initial pass uses the full role budget as an upper bound
    )

    pending_items = None
    if role == "news_processor":
        pending_items, news_flags = _pending_news_items(conn)
        sanitize_flags.extend(news_flags)

    packet = Packet(
        role=role,
        trigger=trigger,
        as_of=as_of,
        regime=regime,
        registry_slice=registry_slice,
        price_summary=price_summary,
        memory=memory,
        prior_output=prior_output,
        pending_items=pending_items,
    )

    if role == "macro_digest":
        extra: dict = {"publisher": publisher, "period": period}
        # Give the newsletter text most of the role budget (16000 chars) —
        # the rest of a macro_digest packet (regime/memory/etc.) is small.
        text_cap = max(budget_chars - 4000, 4000)
        flags = embed_untrusted(
            extra, "sanitized_text", newsletter_text or "", f"newsletter:{publisher}:{period}",
            max_chars=text_cap,
        )
        sanitize_flags.extend(flags)
        packet.extra = extra

    if role == "idea_gen":
        # Phase 10: the 4-gate funnel (py:afund.cycles.funnel.run_funnel,
        # wired as weekly_idea_cycle's first step) has already ranked and
        # gate-annotated the screener's candidates by the time idea_gen
        # runs — give idea_gen that compact per-gate view instead of the
        # raw screen dump, so it reasons over WHY a name cleared rather
        # than re-deriving gate1/gate3/gate4 itself. Trimmed to fit budget
        # below (drop from the bottom, lowest-priority first).
        packet.extra = {"funnel": _compact_funnel(run_funnel(conn))}

    if role in CYCLE_CONTEXT_ROLES:
        cycle_context = _build_cycle_context(conn, scope=scope, sector=resolved_sector)
        if cycle_context is not None:
            packet.extra = {**packet.extra, "cycle_context": cycle_context}

    if role == "risk_mgmt":
        # Phase 10: cycle-aware position sizing + the mechanical subset of
        # governance.checklist, both computed in Python (never left to the
        # agent to compute/guess) — risk_mgmt runs before allocator/
        # fund_manager have proposed a size, so size-dependent checklist
        # items (size_vs_cycle_adjusted_limit, alignment_vs_size, cash_floor,
        # sector_cap) are honestly NA at this stage; first_time_exposure and
        # anchor_extreme are still meaningful here since they don't depend
        # on a not-yet-proposed size.
        from afund.orchestrator.escalation import mechanical_checklist
        from afund.portfolio.risk import cycle_adjusted_limit

        risk_event = {"instrument_id": resolved_instrument_id, "sector": resolved_sector}
        packet.extra = {
            **packet.extra,
            "cycle_adjusted_limit": cycle_adjusted_limit(
                conn, instrument_id=resolved_instrument_id, sector=resolved_sector
            ),
            "mechanical_checklist": mechanical_checklist(conn, risk_event),
        }

    if role == "critique":
        # Phase 10: surface whether this candidate sits in the reconciliation
        # quadrant's contrarian_sweet_spot (quant cheap + narrative still
        # dismissive) — cycle_framework.yaml governance.premortem_trigger
        # makes a premortem mandatory in that case. critique.md's contract
        # (contracts.CritiqueOutput.premortem) treats this flag as a
        # REQUIRED-not-optional signal; a False here just means "not
        # mandatory from the reconciliation signal alone", not "forbidden" —
        # the agent may still choose to write one.
        premortem_req = _resolve_premortem_requirement(conn, scope=scope, sector=resolved_sector)
        packet.extra = {**packet.extra, "requires_premortem": premortem_req["requires_premortem"],
                         "reconciliation": premortem_req}

    if role == "fund_manager":
        # Phase 10: same mechanical checklist risk_mgmt sees, recomputed here
        # (not passed through the pipeline) since by fund_manager time
        # allocator has actually proposed size_or_weight_pct — pull it from
        # prior_output (AllocatorOutput) when present so size_vs_cycle_
        # adjusted_limit/alignment_vs_size stop reading NA. The JUDGMENT
        # checklist items (cycle_framework.yaml governance.checklist entries
        # tagged type: judgment) are NOT computed here — contracts.
        # FundManagerOutput.checklist_status is where the agent supplies
        # those; run.py's ingestion merges both into decision_log.
        from afund.orchestrator.escalation import mechanical_checklist
        from afund.portfolio.risk import cycle_adjusted_limit

        proposed_size = None
        alignment_score = None
        if isinstance(prior_output, dict):
            proposed_size = prior_output.get("proposed_weight_pct")
        cycle_ctx = packet.extra.get("cycle_context")
        if cycle_ctx:
            alignment_score = cycle_ctx.get("alignment_score")
        fm_event = {
            "instrument_id": resolved_instrument_id,
            "sector": resolved_sector,
            "size_or_weight_pct": proposed_size,
            "alignment_score": alignment_score,
        }
        packet.extra = {
            **packet.extra,
            "cycle_adjusted_limit": cycle_adjusted_limit(
                conn, instrument_id=resolved_instrument_id, sector=resolved_sector
            ),
            "mechanical_checklist": mechanical_checklist(conn, fm_event),
        }

    packet.sanitize_flags = sanitize_flags

    packet_dict = packet.to_dict()
    total_chars = _json_chars(packet_dict)

    # Enforcement order: truncate memory slices first...
    if total_chars > budget_chars:
        packet.memory, total_chars = _truncate_memory(
            packet.memory,
            budget_chars - (total_chars - _json_chars(packet.memory)),
            total_chars,
            truncation_notes,
        )
        packet_dict = packet.to_dict()
        total_chars = _json_chars(packet_dict)

    # ...then the funnel candidate list (idea_gen only), dropping from the
    # bottom (lowest-ranked, per run_funnel's own gate1/gate4/gate3 sort)
    # one at a time...
    if total_chars > budget_chars and packet.extra.get("funnel", {}).get("candidates"):
        candidates = packet.extra["funnel"]["candidates"]
        while total_chars > budget_chars and len(candidates) > 1:
            candidates.pop()
            truncation_notes.append("funnel.candidates: truncated 1 item for budget")
            packet_dict = packet.to_dict()
            total_chars = _json_chars(packet_dict)

    # ...then the (supplementary) cycle_context slice...
    if total_chars > budget_chars and "cycle_context" in packet.extra:
        del packet.extra["cycle_context"]
        truncation_notes.append("extra.cycle_context: dropped for budget")
        packet_dict = packet.to_dict()
        total_chars = _json_chars(packet_dict)

    # ...then the registry slice, as a last resort.
    if total_chars > budget_chars and packet.registry_slice:
        # Drop the largest optional sub-slice first (strategies, then kpi_set),
        # keeping risk_limits (smallest, and load-bearing for risk/allocator/FM roles).
        for drop_key in ("strategies", "kpi_set"):
            if total_chars <= budget_chars:
                break
            if drop_key in packet.registry_slice:
                del packet.registry_slice[drop_key]
                truncation_notes.append(f"registry_slice.{drop_key}: dropped for budget")
                packet_dict = packet.to_dict()
                total_chars = _json_chars(packet_dict)

    packet.truncation_notes = truncation_notes
    packet.approx_tokens = total_chars // 4
    packet_dict = packet.to_dict()

    batch_dir = PACKETS_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(batch_dir.glob("[0-9][0-9]_*.json"))
    seq = len(existing) + 1
    out_path = batch_dir / f"{seq:02d}_{role}.json"
    out_path.write_text(json.dumps(packet_dict, indent=2, default=str), encoding="utf-8")

    return {"path": str(out_path), "approx_tokens": packet.approx_tokens, "packet": packet_dict}
