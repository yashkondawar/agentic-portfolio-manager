"""Orchestration for the quarterly-results strategy.

Ties the pieces together for one run: load long-term memory + ledger, mark open
positions against current prices, discover the day's result-declarers, verify
their numbers on screener.in, select strong results, assign PE-rerating targets
with a trailing stop, update the ledger, render a report and persist memory.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from qtr_results import config
from qtr_results import ledger as ledger_mod
from qtr_results import memory as memory_mod
from qtr_results.analysis import AnalysisResult, analyze_symbol
from qtr_results.conviction import evaluate_conviction
from qtr_results.discovery import discover_result_declarers
from qtr_results.targets import build_target_plan
from qtr_results.universe import is_liquid
from qtr_results.util import fmt_pct, fmt_price

logger = logging.getLogger("qtr_results.engine")


def _prioritize_declarers(declarers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order declarers so the ones worth the (capped) verification budget win.

    On a busy earnings day NSE returns 100+ declarers, mostly illiquid micro-caps,
    but only ``max_analyze`` of them get verified on screener.in. Ranking them so
    explicitly-requested (watchlist) and liquid index names come first ensures a
    notable large/mid-cap (e.g. GESHIP) is never truncated behind a wall of
    micro-caps declared the same day. The sort is stable, so within a priority
    tier the original recency order is preserved. Nothing is dropped -- only
    reordered -- so off-index names are still verified if budget remains.
    """
    def rank(entry: Dict[str, Any]) -> tuple:
        sources = entry.get("sources") or []
        symbol = str(entry.get("symbol", ""))
        return (
            "watchlist" in sources,   # explicit user request first
            "web_search" in sources,  # LLM-surfaced (already liquidity-biased)
            is_liquid(symbol),        # in the broad liquid universe
        )

    return sorted(declarers, key=rank, reverse=True)


def _default_price_fn(symbol: str) -> Optional[float]:
    from scraper.market_data import get_stock_price

    data = get_stock_price(symbol)
    if isinstance(data, dict) and "error" not in data:
        return data.get("current_price") or data.get("previous_close")
    return None


def run(params: Optional[Dict[str, Any]] = None, price_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Execute one strategy run and return ``{"report": str, "data": dict}``."""
    params = dict(params or {})
    price_fn = price_fn or _default_price_fn
    _apply_overrides(params)

    watchlist: List[str] = params.get("watchlist") or []
    use_llm: bool = bool(params.get("use_llm", True))
    use_nse: bool = bool(params.get("use_nse", True))
    nse_delta: bool = bool(params.get("nse_delta", True))
    lookback_days: int = int(params.get("lookback_days") or config.DEFAULT_LOOKBACK_DAYS)
    upcoming_days: int = int(params.get("upcoming_days", 14) or 0)
    model: Optional[str] = params.get("model") or None
    dry_run: bool = bool(params.get("dry_run", False))
    max_new: int = int(params.get("max_new") or 10)
    max_analyze: int = int(params.get("max_analyze") or 40)
    use_conviction: bool = bool(params.get("use_conviction", config.USE_CONVICTION_LLM))
    today = date.today()

    config.ensure_state_dir()
    mem = memory_mod.load_memory()
    picks = ledger_mod.load_ledger()

    # 1) Manage existing open positions.
    closed_now = ledger_mod.update_open_positions(picks, price_fn, as_of=today)

    # 2) Discover result-declarers (assured NSE feed + web search + watchlist).
    declarers = discover_result_declarers(
        as_of=today,
        lookback_days=lookback_days,
        watchlist=watchlist,
        use_llm=use_llm,
        use_nse=use_nse,
        nse_delta=nse_delta,
        model=model,
    )

    # Forward-looking heads-up: companies scheduled to declare soon (NSE).
    upcoming = _fetch_upcoming(upcoming_days) if (use_nse and upcoming_days > 0) else []

    # Prioritise the capped verification budget: watchlist + liquid index names
    # first, so a notable large/mid-cap is never truncated behind same-day
    # micro-caps. Stable, so recency order is preserved within each tier.
    declarers = _prioritize_declarers(declarers)

    # 3) Verify + select strong results.
    strong: List[AnalysisResult] = []
    rejected = 0
    errored = 0
    for d in declarers[:max_analyze]:
        analysis = analyze_symbol(d["symbol"])
        analysis._result_date = d.get("result_date", today.isoformat())  # type: ignore[attr-defined]
        analysis._sources = d.get("sources", [])  # type: ignore[attr-defined]
        if analysis.error:
            errored += 1
            continue
        if analysis.is_strong:
            strong.append(analysis)
        else:
            rejected += 1

    strong.sort(key=lambda a: a.strength_score, reverse=True)

    # 3b) Tier-2 LLM qualitative conviction — a point-in-time read of the actual
    # filing (results PDF / investor presentation / concall) + recent news /
    # order-book / sector sentiment. Only the mechanically-qualified shortlist is
    # scored, so the LLM can only REMOVE or SIZE picks, never add un-vetted names.
    conviction_rejected = 0
    conviction_evaluated = 0
    if use_conviction and strong:
        for analysis in strong[: config.MAX_CONVICTION_EVALS]:
            verdict = evaluate_conviction(
                {
                    "symbol": analysis.symbol,
                    "company": analysis.company_name,
                    "result_date": getattr(analysis, "_result_date", today.isoformat()),
                },
                analysis,
                as_of=today,
                model=model,
            )
            conviction_evaluated += 1
            analysis.conviction = verdict.conviction
            analysis.conviction_verdict = verdict.verdict
            analysis.conviction_summary = verdict.summary
            analysis.conviction_risks = verdict.risks
            analysis._conviction_gate = verdict.passes_gate  # type: ignore[attr-defined]
        # Gate: drop shortlisted names the qualitative read rejects. Names beyond
        # the eval cap were never scored (gate defaults to pass) so they still
        # rank below any positively-scored name via the conviction-weighted key.
        kept = [a for a in strong if getattr(a, "_conviction_gate", True)]
        conviction_rejected = len(strong) - len(kept)
        strong = kept
        # Re-rank by conviction × strength (unscored names use a neutral 0.5).
        strong.sort(
            key=lambda a: (a.conviction if a.conviction is not None else 0.5) * a.strength_score,
            reverse=True,
        )

    # 4) Build targets + add new picks.
    new_picks: List[Dict[str, Any]] = []
    for analysis in strong:
        if len(new_picks) >= max_new:
            break
        if ledger_mod.has_open(picks, analysis.symbol):
            continue
        entry_price = analysis.current_price or price_fn(analysis.symbol)
        if not entry_price or entry_price <= 0:
            logger.warning("No entry price for %s; skipping.", analysis.symbol)
            continue
        plan = build_target_plan(
            analysis, entry_price, conviction=getattr(analysis, "conviction", None)
        )
        if plan is None:
            continue
        result_date = getattr(analysis, "_result_date", today.isoformat())
        pick = ledger_mod.add_pick(picks, analysis, plan, result_date=result_date)
        if pick:
            pick["sources"] = getattr(analysis, "_sources", [])
            new_picks.append(pick)

    # 5) Persist (unless dry-run) + report.
    if not dry_run:
        memory_mod.record_run(
            mem, picks=picks, new_picks=new_picks, closed_picks=closed_now,
            note=f"discovered {len(declarers)}, strong {len(strong)}",
        )
        ledger_mod.save_ledger(picks)
        memory_mod.save_memory(mem)

    report = _render_report(
        today=today,
        declarers=declarers,
        strong=strong,
        new_picks=new_picks,
        closed_now=closed_now,
        picks=picks,
        mem=mem,
        rejected=rejected,
        errored=errored,
        dry_run=dry_run,
        upcoming=upcoming,
        conviction_evaluated=conviction_evaluated,
        conviction_rejected=conviction_rejected,
    )
    data = {
        "num_declarers": len(declarers),
        "num_strong": len(strong),
        "num_new_picks": len(new_picks),
        "num_closed": len(closed_now),
        "num_open": len(ledger_mod.open_positions(picks)),
        "num_conviction_evaluated": conviction_evaluated,
        "num_conviction_rejected": conviction_rejected,
        "new_picks": new_picks,
        "closed": closed_now,
        "declarers": declarers,
        "upcoming": upcoming,
        "dry_run": dry_run,
    }
    return {"report": report, "data": data}


def _fetch_upcoming(days_ahead: int) -> List[Dict[str, Any]]:
    try:
        from scraper.nse_events import upcoming_result_declarations

        return upcoming_result_declarations(days_ahead=days_ahead)
    except Exception as e:  # noqa: BLE001 - never let the heads-up break a run
        logger.warning("NSE upcoming-declarations fetch failed (%s).", e)
        return []


def _apply_overrides(params: Dict[str, Any]) -> None:
    """Allow per-run tuning of the key thresholds via params."""
    overrides = {
        "min_yoy_profit_growth": "MIN_YOY_PROFIT_GROWTH",
        "target_min_pct": "TARGET_MIN_PCT",
        "target_max_pct": "TARGET_MAX_PCT",
        "trailing_stop_ratio": "TRAILING_STOP_RATIO",
        "max_holding_days": "MAX_HOLDING_DAYS",
    }
    for pkey, cattr in overrides.items():
        val = params.get(pkey)
        if val is not None and val != "":
            try:
                setattr(config, cattr, float(val) if "days" not in pkey else int(val))
            except (TypeError, ValueError):
                pass


# ── report rendering ───────────────────────────────────────────────────────
def _render_report(**kw) -> str:
    today = kw["today"]
    lines: List[str] = [
        f"# Quarterly-Results Momentum - {today.isoformat()}",
        "",
        (
            f"Discovered **{len(kw['declarers'])}** result-declarers | "
            f"**{len(kw['strong'])}** strong | "
            f"**{len(kw['new_picks'])}** new buys | "
            f"**{len(kw['closed_now'])}** closed this run | "
            f"**{len(ledger_mod.open_positions(kw['picks']))}** open."
        ),
    ]
    if kw.get("conviction_evaluated"):
        lines.append(
            f"\n_Tier-2 LLM conviction: scored **{kw['conviction_evaluated']}** shortlisted, "
            f"rejected **{kw.get('conviction_rejected', 0)}**._"
        )
    if kw["dry_run"]:
        lines.append("\n> _Dry run - ledger and memory were NOT persisted._")

    lines += ["", "## New buys", ""]
    if kw["new_picks"]:
        lines.append("| Symbol | Entry | Target % | Target Rs | Trail stop % | Conv | Method | Strength | Source | Rationale |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for p in kw["new_picks"]:
            src = ", ".join(p.get("sources", [])) or "-"
            conv = p.get("conviction")
            conv_s = f"{conv:.2f} {p.get('conviction_verdict','')}".strip() if conv is not None else "-"
            rationale = p["rationale"]
            if p.get("conviction_summary"):
                rationale = f"{rationale} — {p['conviction_summary']}"
            lines.append(
                f"| {p['symbol']} | {fmt_price(p['entry_price'])} | {p['target_pct']:.1f}% | "
                f"{fmt_price(p['target_price'])} | {p['trailing_stop_pct']:.1f}% | {conv_s} | {p['method']} | "
                f"{p['strength_score']:.0f} | {src} | {rationale} |"
            )
    else:
        lines.append("_No new qualifying result-based buys this run._")

    lines += ["", "## Closed this run", ""]
    if kw["closed_now"]:
        lines.append("| Symbol | Reason | Entry | Exit | Realized % |")
        lines.append("|---|---|---|---|---|")
        for p in kw["closed_now"]:
            lines.append(
                f"| {p['symbol']} | {p.get('exit_reason')} | {fmt_price(p['entry_price'])} | "
                f"{fmt_price(p.get('exit_price'))} | {fmt_pct(p.get('realized_pct'))} |"
            )
    else:
        lines.append("_No positions closed this run._")

    open_pos = ledger_mod.open_positions(kw["picks"])
    lines += ["", "## Open positions", ""]
    if open_pos:
        lines.append("| Symbol | Entry | Last | Target Rs | Stop Rs | Target % | Trail % |")
        lines.append("|---|---|---|---|---|---|---|")
        for p in open_pos:
            lines.append(
                f"| {p['symbol']} | {fmt_price(p['entry_price'])} | {fmt_price(p.get('last_price'))} | "
                f"{fmt_price(p['target_price'])} | {fmt_price(p['stop_price'])} | "
                f"{p['target_pct']:.1f}% | {p['trailing_stop_pct']:.1f}% |"
            )
    else:
        lines.append("_No open positions._")

    lines += ["", "## Long-term memory", "", "```", memory_mod.summarize_memory(kw["mem"]), "```", ""]

    upcoming = kw.get("upcoming") or []
    if upcoming:
        lines += ["", "## Upcoming NSE result declarations", ""]
        lines.append("| Symbol | Company | Meeting date | Purpose |")
        lines.append("|---|---|---|---|")
        for e in upcoming[:25]:
            lines.append(
                f"| {e['symbol']} | {e.get('company','')} | {e.get('event_date','')} | {e.get('purpose','')} |"
            )
        if len(upcoming) > 25:
            lines.append(f"\n_...and {len(upcoming) - 25} more scheduled._")

    lines.append("")
    lines.append(
        "> Educational/analytical use only - NOT investment advice."
    )
    return "\n".join(lines)
