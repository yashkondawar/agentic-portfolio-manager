"""build_sector_packet() — the sector_researcher agent's context packet.

Sector research needs a different shape of packet than the generic
instrument/regime/registry one `orchestrator.context.build_packet()` builds
(no single instrument, no memory retrieval keyed on a symbol) — so this
module assembles its own packet dict directly, rather than routing through
`build_packet()`. It deliberately mirrors that module's conventions where
they still apply: same `data/packets/{batch_id}/{seq:02d}_{role}.json`
persistence location/shape, same registry-slice-via-Registry.load() pattern,
same "pointer, not prose" rule for knowledge/references, and the same
per-role character budget enforced from config/settings.yaml ->
packet_budgets (sector_researcher: 16000).

Nothing here calls an LLM — this module only decides what bytes the
sector_researcher agent gets to see.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from afund.config import REPO_ROOT, load_settings
from afund.derive.screener import run_screen
from afund.orchestrator.context import PACKETS_DIR, SECTOR_TO_KPI_KEY, _build_cycle_context
from afund.research.interpretation import (
    FACTS_VS_INTERPRETATION_REF,
    load_er_registry,
    resolve_frame,
)

DEFAULT_BUDGET_CHARS = 16000

_registry_added = False
_knowledge_added = False


def _load_registry():
    global _registry_added
    if not _registry_added:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        _registry_added = True
    from registry.registry import Registry

    return Registry


def _load_knowledge():
    global _knowledge_added
    if not _knowledge_added:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        _knowledge_added = True
    from knowledge.loader import Knowledge

    return Knowledge


# Reverse of context.SECTOR_TO_KPI_KEY: registry sector slug -> the set of raw
# NSE Industry strings (instruments.sector) that map to it. Built once here
# rather than hand-duplicated, so it can never drift from the canonical
# mapping context.py already owns.
def _raw_sectors_for_kpi_key(kpi_key: str) -> set[str]:
    return {raw for raw, key in SECTOR_TO_KPI_KEY.items() if key == kpi_key}


def _packet_budget_chars(role: str = "sector_researcher") -> int:
    settings = load_settings()
    budgets = settings.get("packet_budgets", {}) or {}
    return int(budgets.get(role, budgets.get("default", DEFAULT_BUDGET_CHARS)))


def _json_chars(obj: Any) -> int:
    return len(json.dumps(obj, default=str))


def _sector_cycle_context(conn: sqlite3.Connection, sector: str) -> dict | None:
    return _build_cycle_context(conn, scope=sector, sector=sector)


def _sector_company_rows(conn: sqlite3.Connection, sector: str) -> list[dict]:
    """Sector-filtered screener candidates: run the bottom-up screen once and
    keep only rows whose raw instruments.sector maps to this registry sector
    slug. Uses the screener's own scoring/flags — this is a research context
    packet, not a fresh computation, so we don't recompute per-instrument
    metrics here."""
    raw_sectors = _raw_sectors_for_kpi_key(sector)
    screen = run_screen(conn)
    rows = []
    for candidate in screen["candidates"]:
        if candidate.get("sector") in raw_sectors:
            rows.append(
                {
                    "symbol": candidate["symbol"],
                    "pe": candidate.get("pe"),
                    "roce": candidate.get("roce"),
                    "roe": candidate.get("roe"),
                    "ret_1y": candidate.get("ret_1y"),
                    "flags": candidate.get("flags", []),
                }
            )
    return rows


def _latest_derived_ratios_for_sector(conn: sqlite3.Connection, sector: str) -> list[dict]:
    """Per-company latest derived_ratios snapshot for every active
    STOCK instrument in this registry sector (beyond just the screener's
    contrarian-flagged subset) — gives sector_researcher full peer coverage,
    not just the names that happen to be flagged by the bottom-up screen."""
    raw_sectors = _raw_sectors_for_kpi_key(sector)
    if not raw_sectors:
        return []
    placeholders = ",".join("?" for _ in raw_sectors)
    rows = conn.execute(
        f"""
        SELECT i.symbol AS symbol, dr.metric_name AS metric_name,
               dr.metric_value AS metric_value, dr.as_of_date AS as_of_date
          FROM instruments i
          JOIN derived_ratios dr ON dr.instrument_id = i.id
         WHERE i.active = 1 AND i.instrument_type = 'STOCK' AND i.sector IN ({placeholders})
        """,
        tuple(raw_sectors),
    ).fetchall()

    by_symbol: dict[str, dict[str, tuple[str, float]]] = {}
    for r in rows:
        sym = r["symbol"]
        by_symbol.setdefault(sym, {})
        existing = by_symbol[sym].get(r["metric_name"])
        if existing is None or r["as_of_date"] > existing[0]:
            by_symbol[sym][r["metric_name"]] = (r["as_of_date"], r["metric_value"])

    return [
        {"symbol": sym, "metrics": {name: val for name, (_, val) in metrics.items()}}
        for sym, metrics in sorted(by_symbol.items())
    ]


def _reference_pointer(rel_path: str) -> dict | None:
    """Path + 1-line summary for a knowledge/references/<rel_path> doc — a
    pointer, never the prose itself (token frugality; CLAUDE.md hard rule).
    Returns None if no such reference doc exists."""
    Knowledge = _load_knowledge()
    k = Knowledge.load()
    for ref in k.references:
        if ref.path == rel_path:
            return {"path": f"knowledge/references/{ref.path}", "summary": ref.summary}
    return None


def _knowledge_reference_pointer(sector: str) -> dict | None:
    """knowledge/references/sectors/<sector>.md. Returns None if no matching
    reference doc exists (sector may resolve only via 'generic')."""
    return _reference_pointer(f"sectors/{sector}.md")


def _divergence_reference(sector: str) -> dict | None:
    """Where the sector's canonical same-fact/different-reading pairs live.

    A pointer set, deliberately: each ER playbook's "## Divergence cases"
    section is prose, and the packet budget for this role is 16k chars total.
    The frame in the packet tells the agent WHICH multiple and WHICH
    conditioners the family is judged on; this tells it where to read the
    worked pairs when a specific number is contested.

    Lists only the tier-2 playbooks under this family that actually exist on
    disk — a dead pointer is worse than an absent one, and the ER subsystem
    is vendored, so a checkout may lag the upstream registry.
    """
    playbooks = (load_er_registry().get("playbooks") or {})
    playbook_dir = (
        REPO_ROOT / "research" / "equity_researcher" / "prompts" / "sector_playbooks"
    )
    children = []
    for slug in sorted(playbooks):
        block = playbooks[slug]
        if not isinstance(block, dict) or block.get("family") != sector:
            continue
        path = playbook_dir / f"{slug}.md"
        if path.exists():
            children.append({"playbook": slug, "path": str(path)})

    methodology = _reference_pointer(FACTS_VS_INTERPRETATION_REF)
    if not children and methodology is None:
        return None
    return {
        "methodology": methodology,
        "sector_playbooks": children,
        "summary": (
            "Each playbook's '## Divergence cases' section carries 2-3 canonical "
            "same-fact/different-reading pairs for that sub-sector with the "
            "discriminator named. Read one when a specific number in the "
            "comparison table is contested; the frame above says which multiple "
            "and conditioners the family is judged on."
        ),
    }


def _registry_kpi_slice(sector: str) -> dict | None:
    Registry = _load_registry()
    reg = Registry.load()
    kpi_set = reg.kpis.get(sector) or reg.kpis.get("generic")
    return kpi_set.model_dump() if kpi_set is not None else None


def build_sector_packet(conn: sqlite3.Connection, sector: str, *, batch_id: str | None = None) -> dict:
    """Assemble, budget-cap, and persist the sector_researcher context packet
    for one registry sector slug (e.g. "it_technology", "bfsi").

    Returns {"path": str, "approx_tokens": int, "packet": dict}, matching the
    shape orchestrator.context.build_packet() returns, so run.py's step
    dispatch can treat both the same way.
    """
    as_of = dt.date.today().isoformat()
    budget_chars = _packet_budget_chars()
    truncation_notes: list[str] = []

    packet: dict = {
        "role": "sector_researcher",
        "sector": sector,
        "as_of": as_of,
        "cycle_context": _sector_cycle_context(conn, sector),
        "comparison_table": _sector_company_rows(conn, sector),
        "sector_financials": _latest_derived_ratios_for_sector(conn, sector),
        "knowledge_reference": _knowledge_reference_pointer(sector),
        "registry_slice": {"kpi_set": _registry_kpi_slice(sector)},
        # Additive (facts/interpretation layer). Family-level only: the fund's
        # 8 slugs ARE the tier-1 families, and the 32 tier-2 playbooks stay
        # owned by ER triage T2 — this packet has no ticker to classify, so it
        # carries the family convention and points at the playbooks rather
        # than picking one. Both are small and sit outside the truncation
        # order below: dropping the lens that says how to read the comparison
        # table, while keeping the table, would be the wrong trade.
        "interpretation_frame": resolve_frame(family=sector),
        "divergence_reference": _divergence_reference(sector),
        "truncation_notes": truncation_notes,
    }

    total_chars = _json_chars(packet)

    # Enforcement order: drop the widest-coverage, lowest-marginal-value slice
    # first (full sector_financials snapshot — comparison_table already
    # carries the screener-flagged subset), then trim comparison_table from
    # the bottom, then drop the registry kpi_set as a last resort — mirrors
    # build_packet()'s "drop biggest optional slice first" philosophy.
    if total_chars > budget_chars and packet["sector_financials"]:
        while total_chars > budget_chars and len(packet["sector_financials"]) > 0:
            packet["sector_financials"].pop()
            truncation_notes.append("sector_financials: truncated 1 item for budget")
            total_chars = _json_chars(packet)

    if total_chars > budget_chars and packet["comparison_table"]:
        while total_chars > budget_chars and len(packet["comparison_table"]) > 1:
            packet["comparison_table"].pop()
            truncation_notes.append("comparison_table: truncated 1 item for budget")
            total_chars = _json_chars(packet)

    if total_chars > budget_chars and packet["registry_slice"].get("kpi_set"):
        packet["registry_slice"] = {}
        truncation_notes.append("registry_slice.kpi_set: dropped for budget")
        total_chars = _json_chars(packet)

    # Last rungs: the divergence pointers go before the frame does, and the
    # frame never goes at all. The playbook list is a convenience (the agent
    # can find them from the frame's family slug); the frame is the only thing
    # in the packet that says how to read a multiple, and a comparison table
    # with no lens is how "P/E 30 looks high" gets written.
    if total_chars > budget_chars and (packet.get("divergence_reference") or {}).get(
        "sector_playbooks"
    ):
        packet["divergence_reference"]["sector_playbooks"] = []
        truncation_notes.append("divergence_reference.sector_playbooks: dropped for budget")
        total_chars = _json_chars(packet)

    if total_chars > budget_chars and packet.get("divergence_reference"):
        packet["divergence_reference"] = None
        truncation_notes.append("divergence_reference: dropped for budget")
        total_chars = _json_chars(packet)

    packet["approx_tokens"] = total_chars // 4

    batch_id = batch_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = PACKETS_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(batch_dir.glob("[0-9][0-9]_*.json"))
    seq = len(existing) + 1
    out_path = batch_dir / f"{seq:02d}_sector_researcher.json"
    out_path.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")

    return {"path": str(out_path), "approx_tokens": packet["approx_tokens"], "packet": packet}
