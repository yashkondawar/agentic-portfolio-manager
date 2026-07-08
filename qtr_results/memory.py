"""Long-term agent memory for the quarterly-results strategy.

A durable store (``memory.json`` + human-readable ``memory.md``) that survives
across runs. It accumulates realized outcomes, running win/return statistics and
dated learnings, and produces a compact summary that is fed back into the LLM
discovery prompt and the per-run report so the agent "remembers" what has
worked.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List

from qtr_results import config
from qtr_results import ledger as ledger_mod

logger = logging.getLogger("qtr_results.memory")


def _empty_memory() -> Dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "created_at": now,
        "updated_at": now,
        "runs": 0,
        "stats": {},
        "learnings": [],
        "events": [],
    }


def load_memory() -> Dict[str, Any]:
    if not config.MEMORY_JSON_PATH.exists():
        return _empty_memory()
    try:
        mem = json.loads(config.MEMORY_JSON_PATH.read_text(encoding="utf-8"))
        for k, v in _empty_memory().items():
            mem.setdefault(k, v)
        return mem
    except (ValueError, OSError) as e:
        logger.warning("Could not read memory (%s); starting fresh.", e)
        return _empty_memory()


def _compute_stats(closed: List[Dict[str, Any]]) -> Dict[str, Any]:
    realized = [p for p in closed if isinstance(p.get("realized_pct"), (int, float))]
    if not realized:
        return {"closed": 0, "wins": 0, "losses": 0, "win_rate": None, "avg_return": None}
    wins = [p for p in realized if p["realized_pct"] > 0]
    returns = [p["realized_pct"] for p in realized]
    best = max(realized, key=lambda p: p["realized_pct"])
    worst = min(realized, key=lambda p: p["realized_pct"])
    return {
        "closed": len(realized),
        "wins": len(wins),
        "losses": len(realized) - len(wins),
        "win_rate": round(len(wins) / len(realized) * 100.0, 1),
        "avg_return": round(sum(returns) / len(returns), 2),
        "best": {"symbol": best["symbol"], "realized_pct": best["realized_pct"]},
        "worst": {"symbol": worst["symbol"], "realized_pct": worst["realized_pct"]},
    }


def record_run(
    mem: Dict[str, Any],
    *,
    picks: List[Dict[str, Any]],
    new_picks: List[Dict[str, Any]],
    closed_picks: List[Dict[str, Any]],
    note: str = "",
) -> Dict[str, Any]:
    """Update memory with this run's activity and recompute lifetime stats."""
    today = date.today().isoformat()
    mem["runs"] = int(mem.get("runs", 0)) + 1
    mem["stats"] = _compute_stats(ledger_mod.closed_positions(picks))
    mem["updated_at"] = datetime.now().isoformat(timespec="seconds")

    for p in new_picks:
        mem["events"].append({
            "date": today, "type": "entry", "symbol": p["symbol"],
            "detail": f"{p['method']} target {p['target_pct']:.1f}% @ Rs {p['entry_price']}",
        })
    for p in closed_picks:
        mem["events"].append({
            "date": today, "type": "exit", "symbol": p["symbol"],
            "detail": f"{p.get('exit_reason')} → {p.get('realized_pct')}%",
        })

    learning = _run_learning(today, new_picks, closed_picks, note)
    if learning:
        mem["learnings"].append(learning)
    # Keep memory bounded.
    mem["learnings"] = mem["learnings"][-100:]
    mem["events"] = mem["events"][-500:]
    return mem


def _run_learning(today, new_picks, closed_picks, note) -> str:
    bits = [f"{today}: +{len(new_picks)} new, {len(closed_picks)} closed"]
    if closed_picks:
        wins = sum(1 for p in closed_picks if (p.get("realized_pct") or 0) > 0)
        bits.append(f"{wins}/{len(closed_picks)} winners this run")
        for p in closed_picks:
            bits.append(f"{p['symbol']} {p.get('exit_reason')} {p.get('realized_pct')}%")
    if note:
        bits.append(note.strip())
    return "; ".join(bits)


def summarize_memory(mem: Dict[str, Any]) -> str:
    """Compact text summary for the LLM prompt and the per-run report."""
    stats = mem.get("stats") or {}
    lines = [
        f"Runs so far: {mem.get('runs', 0)}",
    ]
    if stats.get("closed"):
        lines.append(
            f"Closed trades: {stats['closed']} | win rate {stats.get('win_rate')}% "
            f"| avg return {stats.get('avg_return')}%"
        )
        if stats.get("best"):
            lines.append(
                f"Best: {stats['best']['symbol']} {stats['best']['realized_pct']}% | "
                f"Worst: {stats['worst']['symbol']} {stats['worst']['realized_pct']}%"
            )
    else:
        lines.append("No closed trades yet.")
    recent = mem.get("learnings", [])[-5:]
    if recent:
        lines.append("Recent learnings:")
        lines.extend(f"  - {l}" for l in recent)
    return "\n".join(lines)


def save_memory(mem: Dict[str, Any]) -> None:
    config.ensure_state_dir()
    config.MEMORY_JSON_PATH.write_text(
        json.dumps(mem, indent=2, default=str), encoding="utf-8"
    )
    config.MEMORY_MD_PATH.write_text(_render_md(mem), encoding="utf-8")


def _render_md(mem: Dict[str, Any]) -> str:
    stats = mem.get("stats") or {}
    md = [
        "# Quarterly-Results Strategy — Long-Term Memory",
        "",
        f"_Updated: {mem.get('updated_at')} · Runs: {mem.get('runs', 0)}_",
        "",
        "## Lifetime stats",
        "",
    ]
    if stats.get("closed"):
        md += [
            f"- Closed trades: **{stats['closed']}**",
            f"- Win rate: **{stats.get('win_rate')}%**",
            f"- Average return: **{stats.get('avg_return')}%**",
        ]
        if stats.get("best"):
            md.append(f"- Best: {stats['best']['symbol']} ({stats['best']['realized_pct']}%)")
            md.append(f"- Worst: {stats['worst']['symbol']} ({stats['worst']['realized_pct']}%)")
    else:
        md.append("- No closed trades yet.")
    md += ["", "## Learnings", ""]
    md += [f"- {l}" for l in mem.get("learnings", [])[-30:]] or ["- (none yet)"]
    return "\n".join(md) + "\n"
