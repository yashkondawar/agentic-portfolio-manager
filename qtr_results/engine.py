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
from qtr_results import portfolio as portfolio_mod
from qtr_results import technicals as technicals_mod
from qtr_results.analysis import AnalysisResult, analyze_symbol
from qtr_results.conviction import evaluate_conviction
from qtr_results.discovery import discover_result_declarers
from qtr_results.targets import build_target_plan
from qtr_results.universe import is_liquid
from qtr_results.util import fmt_pct, fmt_price

logger = logging.getLogger("qtr_results.engine")


def _prioritize_declarers(declarers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order declarers so the most notable names are verified FIRST.

    The strategy verifies every discovered declarer by default (``max_analyze=0``),
    so this is not a filter and never drops anyone -- off-index names are still
    analysed, because a genuine multibagger can sit outside the big indices. It is
    purely a resilience ordering: watchlist and liquid index names are scraped
    first, so if a run is interrupted or screener.in starts throttling part-way
    through a busy 100+ declarer day, the names most likely to be traded are
    already done. It also matters if the user sets an explicit ``max_analyze``
    cap for a faster run -- then the cap keeps the notable names. The sort is
    stable, so within a tier the original recency order is preserved.
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
    max_analyze: int = int(params.get("max_analyze") or 0)  # 0 = analyze all
    use_conviction: bool = bool(params.get("use_conviction", config.USE_CONVICTION_LLM))
    # Portfolio sizing knobs (best-experiment defaults; overridable per run).
    capital: Optional[float] = params.get("capital")
    risk_per_trade_pct: float = float(
        params.get("risk_per_trade_pct") or config.RISK_PER_TRADE_PCT
    )
    max_positions: int = int(params.get("max_positions") or config.MAX_POSITIONS)
    max_position_pct: float = float(
        params.get("max_position_pct") or config.MAX_POSITION_PCT
    )
    require_uptrend: bool = bool(params.get("require_uptrend", config.REQUIRE_UPTREND))
    min_liquidity: float = float(
        params.get("min_liquidity") or config.MIN_LIQUIDITY_MEDIAN_20D
    )
    today = date.today()

    config.ensure_state_dir()
    mem = memory_mod.load_memory()
    picks = ledger_mod.load_ledger()
    pf = portfolio_mod.load_portfolio(capital)

    # 1) Manage existing open positions, crediting cash back on every close.
    closed_now = ledger_mod.update_open_positions(picks, price_fn, as_of=today)
    for c in closed_now:
        qty = c.get("quantity") or 0
        if qty and c.get("exit_price"):
            portfolio_mod.apply_close(pf, c["exit_price"], qty)
            portfolio_mod.record_realized(pf, c["entry_price"], c["exit_price"], qty)

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

    # Order declarers so the most notable names (watchlist + liquid index) are
    # verified FIRST. This is resilience ordering, not a filter: by default every
    # declarer is analysed (max_analyze=0), so off-index multibaggers are never
    # gated out by index membership -- mechanical strength + the debt gate + the
    # Tier-2 LLM are what actually decide. If the run is interrupted or screener
    # throttles mid-way, the names most likely to be traded are already done.
    declarers = _prioritize_declarers(declarers)
    candidates = declarers if max_analyze <= 0 else declarers[:max_analyze]
    if len(candidates) > 150:
        logger.warning(
            "Verifying %d declarers on screener.in (~%d min at the 2s/req "
            "throttle); set max_analyze to cap this for a faster run.",
            len(candidates),
            round(len(candidates) * 2.5 / 60),
        )

    # 3) Verify + select strong results.
    strong: List[AnalysisResult] = []
    rejected = 0
    errored = 0
    for d in candidates:
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

    # 4) Build targets + size + add new picks under the portfolio caps.
    equity = portfolio_mod.marked_equity(pf, ledger_mod.open_positions(picks))
    open_count = len(ledger_mod.open_positions(picks))
    new_picks: List[Dict[str, Any]] = []
    skipped_filter = 0
    skipped_nocash = 0
    for analysis in strong:
        if len(new_picks) >= max_new:
            break
        if open_count >= max_positions:
            logger.info("Portfolio at max_positions=%d; no more new buys.", max_positions)
            break
        if ledger_mod.has_open(picks, analysis.symbol):
            continue
        entry_price = analysis.current_price or price_fn(analysis.symbol)
        if not entry_price or entry_price <= 0:
            logger.warning("No entry price for %s; skipping.", analysis.symbol)
            continue

        # Entry-quality filters + ATR sizing share ONE trailing-window fetch.
        tech = technicals_mod.get_technicals(analysis.symbol)
        # Liquidity floor (data-gap-safe: unknown turnover never rejects).
        if (
            tech.median_turnover_20d is not None
            and tech.median_turnover_20d < min_liquidity
        ):
            skipped_filter += 1
            logger.info(
                "Skip %s: 20d turnover Rs %.1fcr < Rs %.1fcr floor.",
                analysis.symbol, tech.median_turnover_20d / 1e7, min_liquidity / 1e7,
            )
            continue
        # Uptrend "not broken" filter (data-gap-safe: unknown trend never rejects).
        if require_uptrend and tech.in_uptrend is False:
            skipped_filter += 1
            logger.info("Skip %s: below SMA%d / not in uptrend.", analysis.symbol,
                        config.TREND_MA_PERIOD)
            continue

        plan = build_target_plan(
            analysis, entry_price,
            conviction=getattr(analysis, "conviction", None),
            atr=tech.atr,
        )
        if plan is None:
            continue

        # Risk-based sizing (shares = risk budget / ATR-stop distance), capped by
        # concentration + available cash. 0 = not takeable with current capital.
        stop_dist = plan.stop_distance_abs or (entry_price * config.FALLBACK_STOP_PCT / 100.0)
        qty = portfolio_mod.size_position(
            entry_price, stop_dist, equity, pf.cash,
            risk_per_trade_pct=risk_per_trade_pct,
            max_position_pct=max_position_pct,
        )
        if qty <= 0:
            skipped_nocash += 1
            logger.info("Skip %s: no cash/room to size a position.", analysis.symbol)
            continue

        result_date = getattr(analysis, "_result_date", today.isoformat())
        invested = portfolio_mod.apply_buy(pf, entry_price, qty)
        pick = ledger_mod.add_pick(
            picks, analysis, plan, result_date=result_date,
            quantity=qty, invested=invested,
        )
        if pick:
            pick["sources"] = getattr(analysis, "_sources", [])
            pick["rupee_risk"] = round(qty * stop_dist, 2)
            new_picks.append(pick)
            open_count += 1

    # 5) Persist (unless dry-run) + report.
    if not dry_run:
        memory_mod.record_run(
            mem, picks=picks, new_picks=new_picks, closed_picks=closed_now,
            note=f"discovered {len(declarers)}, strong {len(strong)}",
        )
        ledger_mod.save_ledger(picks)
        memory_mod.save_memory(mem)
        portfolio_mod.save_portfolio(pf)

    equity_after = portfolio_mod.marked_equity(pf, ledger_mod.open_positions(picks))
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
        portfolio=pf,
        equity=equity_after,
    )
    data = {
        "num_declarers": len(declarers),
        "num_strong": len(strong),
        "num_new_picks": len(new_picks),
        "num_closed": len(closed_now),
        "num_open": len(ledger_mod.open_positions(picks)),
        "num_conviction_evaluated": conviction_evaluated,
        "num_conviction_rejected": conviction_rejected,
        "num_skipped_filter": skipped_filter,
        "num_skipped_nocash": skipped_nocash,
        "cash": round(pf.cash, 2),
        "equity": round(equity_after, 2),
        "realized_pnl": round(pf.realized_pnl, 2),
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
        "risk_per_trade_pct": "RISK_PER_TRADE_PCT",
        "max_positions": "MAX_POSITIONS",
        "max_position_pct": "MAX_POSITION_PCT",
        "atr_stop_multiplier": "ATR_STOP_MULTIPLIER",
        "disable_profit_target": "DISABLE_PROFIT_TARGET",
        "require_uptrend": "REQUIRE_UPTREND",
    }
    int_keys = {"max_holding_days", "max_positions"}
    bool_keys = {"disable_profit_target", "require_uptrend"}
    for pkey, cattr in overrides.items():
        val = params.get(pkey)
        if val is None or val == "":
            continue
        try:
            if pkey in bool_keys:
                setattr(config, cattr, bool(val) if isinstance(val, bool)
                        else str(val).lower() in ("1", "true", "yes"))
            elif pkey in int_keys:
                setattr(config, cattr, int(val))
            else:
                setattr(config, cattr, float(val))
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

    pf = kw.get("portfolio")
    if pf is not None:
        equity = kw.get("equity", pf.cash)
        deployed = max(equity - pf.cash, 0.0)
        util = (deployed / equity * 100.0) if equity > 0 else 0.0
        lines += [
            "",
            (
                f"**Portfolio** — equity Rs {equity:,.0f} | cash Rs {pf.cash:,.0f} "
                f"({util:.0f}% deployed) | realized P&L Rs {pf.realized_pnl:,.0f} | "
                f"risk/trade {config.RISK_PER_TRADE_PCT:.0f}% | max positions "
                f"{config.MAX_POSITIONS} | ATR stop {config.ATR_STOP_MULTIPLIER:.0f}x | "
                f"hold {config.MAX_HOLDING_DAYS}d | "
                f"{'ride-the-wave' if config.DISABLE_PROFIT_TARGET else 'capped-target'}."
            ),
        ]

    lines += ["", "## New buys", ""]
    if kw["new_picks"]:
        lines.append("| Symbol | Entry | Qty | Invested Rs | Rs Risk | Target Rs | Stop Rs | Conv | Method | Strength | Source | Rationale |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for p in kw["new_picks"]:
            src = ", ".join(p.get("sources", [])) or "-"
            conv = p.get("conviction")
            conv_s = f"{conv:.2f} {p.get('conviction_verdict','')}".strip() if conv is not None else "-"
            rationale = p["rationale"]
            if p.get("conviction_summary"):
                rationale = f"{rationale} — {p['conviction_summary']}"
            lines.append(
                f"| {p['symbol']} | {fmt_price(p['entry_price'])} | {p.get('quantity', 0)} | "
                f"{p.get('invested', 0):,.0f} | {p.get('rupee_risk', 0):,.0f} | "
                f"{fmt_price(p['target_price'])} | {fmt_price(p.get('stop_price'))} | {conv_s} | "
                f"{p['method']} | {p['strength_score']:.0f} | {src} | {rationale} |"
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
