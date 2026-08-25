"""
engine.py
=========

The live runner.

The single most important design decision in this file is what it *does not*
contain: there is no live copy of the entry rule, the ranking, the stop, the
exit ladder, the sector cap or the sizing. All of that is imported from
``backtesting.gfs`` and executed by ``GFSBacktestEngine.run`` - the same daily
loop, in the same order, over the same pre-computed causal panels.

A live run is therefore literally "resume the backtest":

1. Load the persisted book (cash, positions, tradebook, and crucially the
   pending entry/exit queues).
2. Download bars up to today and rebuild the panels.
3. Restore the book into a fresh engine.
4. Replay every trading session between the last simulated one and today.
5. Capture the engine's state back into the book and save it.

Because step 4 uses the engine unmodified, a gap of one day, a weekend, or a
fortnight of neglect are all the same thing: the missed sessions are simply
replayed. There is no "catch-up" code path to get wrong.

What the operator actually executes
-----------------------------------
The backtest never fills a signal on the bar that produced it. A candidate found
at Monday's close is filled at Tuesday's *open*. So the output of a post-close
run is not "buy these now" - it is **"place these orders at the next open"**, and
those orders live in the pending queues until the next run fills them against the
open that actually printed. That is the only way the live book can claim to be
the thing that was measured.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from backtesting.gfs import strategy as gfs_strategy
from backtesting.gfs.config import GFSConfig
from backtesting.gfs.engine import GFSBacktestEngine
from backtesting.gfs.metrics import compute_metrics
from backtesting.gfs.service import prepare_data
from backtesting.gfs.universe import universe_bias_note

from .config import (
    LIVE_DEFAULTS,
    STRATEGY_ID,
    build_config,
    default_bootstrap_start,
    shadow_exit_rsi,
)
from .state import Book, load_book, load_last_run, reset_book, save_book, save_last_run

logger = logging.getLogger("gfs.live")

#: A book younger than this cannot support an annualised number; reporting one
#: would turn a good fortnight into a 900% CAGR.
MIN_DAYS_FOR_CAGR = 90


# ── small read-only helpers ──────────────────────────────────────────────────


def _close_on(panel, ts: pd.Timestamp) -> Optional[float]:
    sliced = panel.frame["Close"].loc[:ts]
    return None if sliced.empty else float(sliced.iloc[-1])


def _f(value) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _rsi_triplet(row: Optional[pd.Series]) -> Dict[str, Optional[float]]:
    if row is None:
        return {"rsi_d": None, "rsi_w": None, "rsi_m": None}
    return {
        "rsi_d": _f(row.get("rsi_d")),
        "rsi_w": _f(row.get("rsi_w")),
        "rsi_m": _f(row.get("rsi_m")),
    }


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    return None if value is None else round(value, digits)


# ── the run ──────────────────────────────────────────────────────────────────


def run(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute one daily update. Returns ``{"report": str, "data": dict}``."""
    params = dict(params or {})
    today = _resolve_today(params)
    dry_run = bool(params.get("dry_run"))

    if params.get("reset_book"):
        reset_book()

    book = load_book()
    start = _resume_from(book, params, today)

    if start > today:
        # Already up to date. Still worth rendering the book, because that is
        # what the user came to look at.
        data = _snapshot_payload(book, params, today, up_to_date=True)
        return {"report": render_report(data), "data": data}

    cfg = build_config(params, start=start, end=max(today, start + timedelta(days=1)))
    logger.info("GFS live: replaying %s -> %s", start, today)

    prepared = prepare_data(cfg)
    panels, calendar, sector_panel, regime_panel, qualify = prepared.panels_for(cfg)

    sessions = [ts for ts in calendar if start <= ts.date() <= today]
    if not sessions:
        data = _snapshot_payload(book, params, today, up_to_date=True)
        data["note"] = (
            f"No trading session between {start.isoformat()} and {today.isoformat()}."
        )
        return {"report": render_report(data), "data": data}

    engine = GFSBacktestEngine(
        cfg, panels, sector_panel, regime_panel, qualify, calendar
    )
    if book.is_empty:
        book.open_with(cfg.starting_capital, sessions[0].date())
    book.restore_into(engine)

    before_closed = len(engine.pf.closed)
    before_open = set(engine.pf.positions)

    engine.run(start, today)

    last_ts = sessions[-1]
    new_trades = engine.pf.closed[before_closed:]
    opened_now = [
        sym for sym in engine.pf.positions if sym not in before_open
    ]

    book.capture_from(engine)
    book.last_session = last_ts.date()

    data = _build_payload(
        book=book,
        cfg=cfg,
        params=params,
        engine=engine,
        panels=panels,
        sector_panel=sector_panel,
        regime_panel=regime_panel,
        qualify=qualify,
        last_ts=last_ts,
        sessions=sessions,
        new_trades=new_trades,
        opened_now=opened_now,
        prepared_universe=len(prepared.universe),
        today=today,
        dry_run=dry_run,
    )
    if not dry_run:
        # Saved only after the payload is assembled, because building it also
        # stamps the display marks onto the book.
        save_book(book)
        save_last_run(
            {
                "as_of": data["as_of"],
                "ran_at": date.today().isoformat(),
                "sessions": len(sessions),
                "orders": len(data["orders"]),
                "open_positions": len(data["holdings"]),
                "equity": data["book"]["equity"],
            }
        )
    return {"report": render_report(data), "data": data}


def _resolve_today(params: Dict[str, Any]) -> date:
    value = params.get("as_of")
    if value:
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    return date.today()


def _resume_from(book: Book, params: Dict[str, Any], today: date) -> date:
    if not book.is_empty:
        return book.last_session + timedelta(days=1)
    bootstrap = params.get("bootstrap_from")
    if bootstrap:
        parsed = (
            bootstrap if isinstance(bootstrap, date) else date.fromisoformat(str(bootstrap))
        )
        if parsed >= today:
            raise ValueError("bootstrap_from must be before today")
        return parsed
    return default_bootstrap_start(today)


# ── payload assembly ─────────────────────────────────────────────────────────


def _build_payload(
    *,
    book: Book,
    cfg: GFSConfig,
    params: Dict[str, Any],
    engine: GFSBacktestEngine,
    panels: Dict[str, Any],
    sector_panel,
    regime_panel,
    qualify: pd.DataFrame,
    last_ts: pd.Timestamp,
    sessions: List[pd.Timestamp],
    new_trades: List[Any],
    opened_now: List[str],
    prepared_universe: int,
    today: date,
    dry_run: bool,
) -> Dict[str, Any]:
    shadow = shadow_exit_rsi(params)
    holdings = _holdings(engine, panels, last_ts, shadow)
    # Display-only carry-over so the offline panel can mark positions at the
    # last close this run saw rather than at their entry price.
    book.marks = {
        h["symbol"]: {
            "price": h["last_price"],
            "rsi_d": h["rsi_d"],
            "rsi_w": h["rsi_w"],
            "rsi_m": h["rsi_m"],
        }
        for h in holdings
    }
    orders = _orders(engine, panels, last_ts, cfg)
    watchlist = _watchlist(
        engine, panels, sector_panel, qualify, last_ts, cfg, regime_panel
    )
    regime_row = regime_panel.row(last_ts)

    equity = sum(h["value"] for h in holdings) + book.cash
    metrics = compute_metrics(book.equity_curve, book.closed, book.starting_capital)
    if _book_age_days(book) < MIN_DAYS_FOR_CAGR:
        metrics.pop("cagr_pct", None)
        metrics.pop("calmar", None)

    return {
        "strategy_id": STRATEGY_ID,
        "as_of": last_ts.date().isoformat(),
        "generated_for": today.isoformat(),
        "dry_run": dry_run,
        "up_to_date": False,
        "sessions_replayed": [ts.date().isoformat() for ts in sessions],
        "book": {
            "equity": round(equity, 2),
            "cash": round(book.cash, 2),
            "deployed": round(equity - book.cash, 2),
            "exposure_pct": round((equity - book.cash) / equity * 100.0, 1)
            if equity > 0
            else 0.0,
            "starting_capital": round(book.starting_capital, 2),
            "opened_on": book.opened_on.isoformat() if book.opened_on else None,
            "open_positions": len(holdings),
            "closed_trades": len(book.closed),
            "realized_pnl": round(sum(t.pnl for t in book.closed), 2),
            "total_return_pct": _round(
                (equity / book.starting_capital - 1.0) * 100.0
                if book.starting_capital > 0
                else None
            ),
        },
        "metrics": metrics,
        "holdings": holdings,
        "orders": orders,
        "fills": _fills(new_trades, opened_now, holdings),
        "tradebook": _tradebook(book.closed),
        "watchlist": watchlist,
        "funnel": _funnel(prepared_universe, len(panels), watchlist, orders),
        "diagnostics": {
            "regime_ok": bool(regime_row["regime_ok"]) if regime_row is not None else None,
            "breadth_pct": _round(_f(regime_row["breadth_pct"]))
            if regime_row is not None
            else None,
            "min_breadth_pct": cfg.min_breadth_pct,
            "regime_mode": cfg.regime_mode,
            "qualifying_today": len(watchlist),
            "rejections": dict(
                sorted(engine.rejections.items(), key=lambda kv: -kv[1])
            ),
            "signal_log": engine.signal_log[-10:],
            "universe_note": universe_bias_note(cfg),
        },
        "shadow": _shadow_block(shadow, holdings),
        "config": _config_summary(cfg, params),
        "equity_curve": book.equity_curve[-500:],
    }


def _snapshot_payload(
    book: Book, params: Dict[str, Any], today: date, *, up_to_date: bool
) -> Dict[str, Any]:
    """Book-only view: no download, no panels. Used when nothing new happened."""
    snap = ledger_snapshot()
    shadow = shadow_exit_rsi(params)
    holdings = snap.get("holdings") or []
    # The snapshot was built with the default shadow threshold; re-flag against
    # the one this run actually asked for.
    for row in holdings:
        rsi_d = row.get("rsi_d")
        row["shadow_exit"] = bool(
            shadow is not None and rsi_d is not None and float(rsi_d) >= shadow
        )
    snap.update(
        {
            "strategy_id": STRATEGY_ID,
            "generated_for": today.isoformat(),
            "up_to_date": up_to_date,
            "dry_run": bool(params.get("dry_run")),
            "sessions_replayed": [],
            "orders": _pending_orders_from_book(book),
            "fills": [],
            "watchlist": [],
            "funnel": [],
            "diagnostics": {},
            "shadow": _shadow_block(shadow, holdings),
            "config": {},
        }
    )
    return snap


def _book_age_days(book: Book) -> int:
    if not book.equity_curve:
        return 0
    first = date.fromisoformat(book.equity_curve[0]["date"])
    last = date.fromisoformat(book.equity_curve[-1]["date"])
    return (last - first).days


# ── views over engine state ──────────────────────────────────────────────────


def _holdings(
    engine: GFSBacktestEngine,
    panels: Dict[str, Any],
    ts: pd.Timestamp,
    shadow: Optional[float],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for symbol, pos in engine.pf.positions.items():
        panel = panels.get(symbol)
        row = panel.row(ts) if panel is not None else None
        price = _close_on(panel, ts) if panel is not None else None
        mark = price if price is not None else pos.entry_price
        rsi = _rsi_triplet(row)
        rsi_d = rsi["rsi_d"]
        rows.append(
            {
                "symbol": symbol,
                "sector": pos.sector,
                "quantity": int(pos.quantity),
                "entry_date": pos.entry_date.isoformat(),
                "entry_price": round(pos.entry_price, 2),
                "last_price": _round(mark),
                "value": round(pos.quantity * mark, 2),
                "unrealized_pct": _round((mark / pos.entry_price - 1.0) * 100.0),
                "stop_price": round(pos.stop_loss, 2),
                "stop_distance_pct": _round((mark / pos.stop_loss - 1.0) * 100.0)
                if pos.stop_loss > 0
                else None,
                "target_price": round(pos.target_price, 2),
                "days_held": (ts.date() - pos.entry_date).days,
                "entry_rsi_d": _round(pos.entry_rsi_d, 1),
                "entry_rsi_w": _round(pos.entry_rsi_w, 1),
                "entry_rsi_m": _round(pos.entry_rsi_m, 1),
                "rsi_d": _round(rsi_d, 1),
                "rsi_w": _round(rsi["rsi_w"], 1),
                "rsi_m": _round(rsi["rsi_m"], 1),
                "shadow_exit": (
                    bool(shadow is not None and rsi_d is not None and rsi_d >= shadow)
                ),
            }
        )
    rows.sort(key=lambda r: r["unrealized_pct"] or 0.0, reverse=True)
    return rows


def _orders(
    engine: GFSBacktestEngine,
    panels: Dict[str, Any],
    ts: pd.Timestamp,
    cfg: GFSConfig,
) -> List[Dict[str, Any]]:
    """What to place at the next open.

    Quantities are indicative: the engine re-derives the stop and the size from
    the *actual* opening print when it fills, exactly as the backtest does, so a
    gap changes the size rather than silently changing the risk.
    """
    orders: List[Dict[str, Any]] = []
    for symbol, op in engine.pending_exits:
        pos = engine.pf.positions.get(symbol)
        if pos is None:
            continue
        orders.append(
            {
                "action": "SELL",
                "symbol": symbol,
                "sector": pos.sector,
                "quantity": int(pos.quantity * op.fraction) or int(pos.quantity),
                "reference_price": _round(op.price),
                "reason": op.reason,
                "detail": f"Exit signalled at {ts.date().isoformat()} close ({op.reason}).",
            }
        )
    equity = engine.pf.total_equity(lambda s: _close_on(panels[s], ts) if s in panels else None)
    for sig in engine.pending_entries:
        stop = sig.stop_hint
        qty = gfs_strategy.size_position(sig.close, stop, equity, cfg)
        orders.append(
            {
                "action": "BUY",
                "symbol": sig.symbol,
                "sector": sig.sector,
                "quantity": int(qty),
                "reference_price": _round(sig.close),
                "stop_price": _round(stop),
                "rsi_d": _round(sig.rsi_d, 1),
                "rsi_w": _round(sig.rsi_w, 1),
                "rsi_m": _round(sig.rsi_m, 1),
                "resistance": _round(sig.resistance),
                "reason": "gfs_entry",
                "detail": (
                    "Queued from "
                    f"{ts.date().isoformat()} close; fills at the next open, "
                    "capacity and sector cap permitting."
                ),
            }
        )
    return orders


def _pending_orders_from_book(book: Book) -> List[Dict[str, Any]]:
    """Same queue, rendered without an engine (snapshot path)."""
    orders: List[Dict[str, Any]] = []
    for symbol, op in book.pending_exits:
        pos = book.positions.get(symbol)
        orders.append(
            {
                "action": "SELL",
                "symbol": symbol,
                "sector": pos.sector if pos else None,
                "quantity": int(pos.quantity) if pos else None,
                "reference_price": _round(op.price),
                "reason": op.reason,
                "detail": "Carried over from the last run.",
            }
        )
    for sig in book.pending_entries:
        orders.append(
            {
                "action": "BUY",
                "symbol": sig.symbol,
                "sector": sig.sector,
                "quantity": None,
                "reference_price": _round(sig.close),
                "stop_price": _round(sig.stop_hint),
                "rsi_d": _round(sig.rsi_d, 1),
                "rsi_w": _round(sig.rsi_w, 1),
                "rsi_m": _round(sig.rsi_m, 1),
                "reason": "gfs_entry",
                "detail": "Carried over from the last run.",
            }
        )
    return orders


def _fills(
    new_trades: List[Any], opened_now: List[str], holdings: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """What the replay actually executed since the previous run."""
    by_symbol = {h["symbol"]: h for h in holdings}
    fills: List[Dict[str, Any]] = []
    for sym in opened_now:
        h = by_symbol.get(sym)
        if h is None:
            continue
        fills.append(
            {
                "action": "BOUGHT",
                "symbol": sym,
                "date": h["entry_date"],
                "quantity": h["quantity"],
                "price": h["entry_price"],
                "detail": f"Stop {h['stop_price']}, target {h['target_price']}.",
            }
        )
    for t in new_trades:
        fills.append(
            {
                "action": "SOLD",
                "symbol": t.symbol,
                "date": t.exit_date.isoformat(),
                "quantity": int(t.quantity),
                "price": round(t.exit_price, 2),
                "detail": f"{t.exit_reason} | {t.pnl_pct:+.2f}% over {t.holding_days}d.",
            }
        )
    return fills


def _watchlist(
    engine: GFSBacktestEngine,
    panels: Dict[str, Any],
    sector_panel,
    qualify: pd.DataFrame,
    ts: pd.Timestamp,
    cfg: GFSConfig,
    regime_panel,
) -> List[Dict[str, Any]]:
    """Every name that met the mechanical GFS condition on the latest close.

    The ``status`` column is *descriptive only* - it explains, after the fact,
    why a qualifying name did or did not become an order. The actual decision was
    already made by the engine; nothing here can change it.
    """
    if qualify.empty or ts not in qualify.index:
        return []
    flags = qualify.loc[ts]
    symbols = list(flags.index[flags.to_numpy()])
    if not symbols:
        return []

    queued = {sig.symbol for sig in engine.pending_entries}
    regime_ok = regime_panel.ok_on(ts)
    capacity = cfg.max_positions - len(engine.pf.positions)
    exposure = engine.pf.sector_exposure()

    rows: List[Dict[str, Any]] = []
    for symbol in symbols:
        panel = panels.get(symbol)
        if panel is None:
            continue
        row = panel.row(ts)
        if row is None:
            continue
        rank = sector_panel.rank_of(panel.sector, ts)
        if symbol in queued:
            status = "queued"
        elif symbol in engine.pf.positions:
            status = "already_held"
        elif cfg.use_regime_filter and not regime_ok:
            status = "regime_closed"
        elif cfg.use_sector_filter and (rank is None or rank > cfg.sector_top_n):
            status = "sector_weak"
        elif not gfs_strategy.can_open_sector(panel.sector, exposure, cfg):
            status = "sector_cap"
        elif capacity <= 0:
            status = "portfolio_full"
        else:
            status = "ranked_out"
        rsi = _rsi_triplet(row)
        rows.append(
            {
                "symbol": symbol,
                "sector": panel.sector,
                "sector_rank": None if rank is None else int(rank),
                "close": _round(_f(row.get("Close"))),
                "rsi_d": _round(rsi["rsi_d"], 1),
                "rsi_w": _round(rsi["rsi_w"], 1),
                "rsi_m": _round(rsi["rsi_m"], 1),
                "headroom_pct": _round(_f(row.get("headroom_pct"))),
                "resistance": _round(_f(row.get("resistance"))),
                "status": status,
            }
        )
    rows.sort(key=lambda r: (r["status"] != "queued", r["sector_rank"] or 99))
    return rows


def _funnel(
    universe_size: int,
    panels_built: int,
    watchlist: List[Dict[str, Any]],
    orders: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    tradable = [w for w in watchlist if w["status"] != "regime_closed"]
    in_sector = [w for w in tradable if w["status"] != "sector_weak"]
    buys = [o for o in orders if o["action"] == "BUY"]
    stages = [
        ("Universe", universe_size),
        ("With history", panels_built),
        ("GFS condition", len(watchlist)),
        ("Regime open", len(tradable)),
        ("Strong sector", len(in_sector)),
        ("Queued to buy", len(buys)),
    ]
    out: List[Dict[str, Any]] = []
    prev: Optional[int] = None
    for name, count in stages:
        out.append(
            {
                "stage": name,
                "count": count,
                "dropped": (prev - count) if prev is not None and prev >= count else 0,
            }
        )
        prev = count
    return out


def _tradebook(closed: List[Any]) -> List[Dict[str, Any]]:
    rows = []
    for t in closed:
        rows.append(
            {
                "symbol": t.symbol,
                "sector": t.sector,
                "entry_date": t.entry_date.isoformat(),
                "exit_date": t.exit_date.isoformat(),
                "quantity": int(t.quantity),
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "pnl": round(t.pnl, 2),
                "pnl_pct": round(t.pnl_pct, 2),
                "r_multiple": round(t.r_multiple, 2),
                "holding_days": t.holding_days,
                "exit_reason": t.exit_reason,
                "entry_rsi": f"{t.entry_rsi_m:.0f}/{t.entry_rsi_w:.0f}/{t.entry_rsi_d:.0f}",
                "exit_rsi": f"{t.exit_rsi_m:.0f}/{t.exit_rsi_w:.0f}/{t.exit_rsi_d:.0f}",
            }
        )
    rows.sort(key=lambda r: r["exit_date"], reverse=True)
    return rows


def _shadow_block(
    shadow: Optional[float], holdings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """What the *other* exit threshold would be saying right now.

    The research could not separate exit-60 from exit-70 out of sample, so the
    live book trades one and reports the other rather than pretending the
    question is settled.
    """
    if shadow is None:
        return {"exit_rsi": None, "would_exit": []}
    return {
        "exit_rsi": shadow,
        "would_exit": [h["symbol"] for h in holdings if h["shadow_exit"]],
    }


def _config_summary(cfg: GFSConfig, params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "universe": cfg.universe_index,
        "benchmark": cfg.benchmark,
        "entry": f"G>={cfg.g_rsi_min:.0f}, F>={cfg.f_rsi_min:.0f}, S<={cfg.s_rsi_entry:.0f}",
        "min_headroom_pct": cfg.min_headroom_pct,
        "exit_rsi": cfg.exit_rsi,
        "shadow_exit_rsi": shadow_exit_rsi(params),
        "stop": f"{cfg.atr_stop_mult:g}x ATR({cfg.atr_period})",
        "time_stop": "none",
        "regime": f"{cfg.regime_mode} (breadth >= {cfg.min_breadth_pct:.0f}%)",
        "sector_gate": f"top {cfg.sector_top_n}, max {cfg.max_per_sector} per sector",
        "sizing": f"{cfg.max_positions} positions x {cfg.max_position_pct:.0f}% max",
        "htf_mode": cfg.htf_mode,
        "cash_yield_pct": cfg.cash_yield_pct,
        "costs": f"{cfg.commission_pct}% commission, {cfg.slippage_bps:g} bps slippage",
    }


# ── offline snapshot (no network, no panels) ─────────────────────────────────


def ledger_snapshot() -> Dict[str, Any]:
    """Read the persisted book straight from the DB.

    Used by the always-on portfolio panel so the page renders without running
    the strategy. Positions are marked at their last known run price, which is
    why the UI labels it as such.
    """
    book = load_book()
    last_run = load_last_run()
    shadow = float(LIVE_DEFAULTS.get("shadow_exit_rsi") or 0.0)
    ref_day = book.last_session or date.today()
    holdings: List[Dict[str, Any]] = []
    deployed = 0.0
    for symbol, pos in book.positions.items():
        # No network here, so positions are marked at the close the last run
        # saw. The UI says so rather than implying a live quote.
        mark_row = book.marks.get(symbol) or {}
        mark = float(mark_row.get("price") or pos.entry_price)
        rsi_d = mark_row.get("rsi_d")
        value = pos.quantity * mark
        deployed += value
        holdings.append(
            {
                "symbol": symbol,
                "sector": pos.sector,
                "quantity": int(pos.quantity),
                "entry_date": pos.entry_date.isoformat(),
                "entry_price": round(pos.entry_price, 2),
                "last_price": round(mark, 2),
                "value": round(value, 2),
                "unrealized_pct": round((mark / pos.entry_price - 1.0) * 100.0, 2),
                "stop_price": round(pos.stop_loss, 2),
                "stop_distance_pct": round((mark / pos.stop_loss - 1.0) * 100.0, 2)
                if pos.stop_loss > 0
                else None,
                "target_price": round(pos.target_price, 2),
                "days_held": (ref_day - pos.entry_date).days,
                "entry_rsi_d": round(pos.entry_rsi_d, 1),
                "entry_rsi_w": round(pos.entry_rsi_w, 1),
                "entry_rsi_m": round(pos.entry_rsi_m, 1),
                "rsi_d": rsi_d,
                "rsi_w": mark_row.get("rsi_w"),
                "rsi_m": mark_row.get("rsi_m"),
                "shadow_exit": bool(
                    shadow > 0 and rsi_d is not None and float(rsi_d) >= shadow
                ),
            }
        )
    holdings.sort(key=lambda r: r["unrealized_pct"] or 0.0, reverse=True)
    equity = book.cash + deployed
    if book.equity_curve:
        equity = float(book.equity_curve[-1]["equity"])
        deployed = float(book.equity_curve[-1]["deployed"])

    metrics = compute_metrics(book.equity_curve, book.closed, book.starting_capital)
    if _book_age_days(book) < MIN_DAYS_FOR_CAGR:
        metrics.pop("cagr_pct", None)
        metrics.pop("calmar", None)

    return {
        "as_of": book.last_session.isoformat() if book.last_session else None,
        "book": {
            "equity": round(equity, 2),
            "cash": round(book.cash, 2),
            "deployed": round(deployed, 2),
            "exposure_pct": round(deployed / equity * 100.0, 1) if equity > 0 else 0.0,
            "starting_capital": round(book.starting_capital, 2),
            "opened_on": book.opened_on.isoformat() if book.opened_on else None,
            "open_positions": len(holdings),
            "closed_trades": len(book.closed),
            "realized_pnl": round(sum(t.pnl for t in book.closed), 2),
            "total_return_pct": round(
                (equity / book.starting_capital - 1.0) * 100.0, 2
            )
            if book.starting_capital > 0
            else None,
        },
        "metrics": metrics,
        "holdings": holdings,
        "shadow": _shadow_block(shadow if shadow > 0 else None, holdings),
        "tradebook": _tradebook(book.closed),
        "num_closed": len(book.closed),
        "pending": len(book.pending_entries) + len(book.pending_exits),
        "last_run": last_run,
        "equity_curve": book.equity_curve[-500:],
    }


# ── report ───────────────────────────────────────────────────────────────────


def render_report(data: Dict[str, Any]) -> str:
    b = data.get("book") or {}
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(" GFS LIVE - Grandfather / Father / Son")
    lines.append("=" * 72)
    as_of = data.get("as_of") or "never run"
    lines.append(f" As of close      : {as_of}")
    if data.get("dry_run"):
        lines.append(" MODE             : DRY RUN - nothing was saved")
    if data.get("up_to_date"):
        lines.append(" Status           : already up to date, no new session replayed")
    else:
        lines.append(f" Sessions replayed: {len(data.get('sessions_replayed') or [])}")
    lines.append("")

    lines.append("-" * 72)
    lines.append(" BOOK")
    lines.append("-" * 72)
    lines.append(
        f" Equity {b.get('equity')}  |  cash {b.get('cash')}  |  deployed "
        f"{b.get('deployed')} ({b.get('exposure_pct')}%)"
    )
    lines.append(
        f" Open {b.get('open_positions')}  |  closed trades {b.get('closed_trades')}"
        f"  |  realised {b.get('realized_pnl')}"
    )
    total = b.get("total_return_pct")
    if total is not None:
        lines.append(f" Total return since inception: {total:+.2f}%")
    m = data.get("metrics") or {}
    if m.get("num_trades"):
        lines.append(
            f" Win rate {m.get('win_rate_pct')}%  |  payoff {m.get('payoff_ratio')}"
            f"  |  expectancy {m.get('expectancy_r')}R"
            f"  |  avg hold {m.get('avg_holding_days')}d"
        )
    if m.get("cagr_pct") is not None:
        lines.append(
            f" CAGR {m['cagr_pct']}%  |  max DD {m.get('max_drawdown_pct')}%"
            f"  |  Sharpe {m.get('sharpe')}"
        )
    lines.append("")

    fills = data.get("fills") or []
    if fills:
        lines.append("-" * 72)
        lines.append(" FILLED SINCE THE LAST RUN")
        lines.append("-" * 72)
        for f in fills:
            lines.append(
                f" {f['date']}  {f['action']:<7} {f['symbol']:<14} "
                f"{f['quantity']} @ {f['price']}   {f['detail']}"
            )
        lines.append("")

    orders = data.get("orders") or []
    lines.append("-" * 72)
    lines.append(" ORDERS FOR THE NEXT OPEN")
    lines.append("-" * 72)
    if not orders:
        lines.append(" Nothing to place. Hold what you have.")
    for o in orders:
        if o["action"] == "BUY":
            lines.append(
                f" BUY   {o['symbol']:<14} qty {o.get('quantity')}  ref "
                f"{o.get('reference_price')}  stop {o.get('stop_price')}"
                f"  RSI m/w/d {o.get('rsi_m')}/{o.get('rsi_w')}/{o.get('rsi_d')}"
            )
        else:
            lines.append(
                f" SELL  {o['symbol']:<14} qty {o.get('quantity')}  ref "
                f"{o.get('reference_price')}  ({o.get('reason')})"
            )
    lines.append("")

    holdings = data.get("holdings") or []
    if holdings:
        lines.append("-" * 72)
        lines.append(" HOLDINGS")
        lines.append("-" * 72)
        lines.append(
            f" {'symbol':<14}{'qty':>6}{'entry':>10}{'last':>10}{'P/L%':>8}"
            f"{'stop':>10}{'RSI d':>7}{'held':>6}"
        )
        for h in holdings:
            lines.append(
                f" {h['symbol']:<14}{h['quantity']:>6}{h['entry_price']:>10.2f}"
                f"{(h['last_price'] or 0):>10.2f}{(h['unrealized_pct'] or 0):>7.1f}%"
                f"{h['stop_price']:>10.2f}{(h['rsi_d'] or 0):>7.1f}{h['days_held']:>6}"
            )
        lines.append("")

    shadow = data.get("shadow") or {}
    if shadow.get("exit_rsi"):
        would = shadow.get("would_exit") or []
        lines.append(
            f" Shadow rule (exit at RSI {shadow['exit_rsi']:.0f}): "
            + (
                f"{len(would)} of {len(holdings)} open positions would be flagged "
                f"to exit - {', '.join(would)}"
                if would
                else "no open position would be flagged to exit"
            )
        )
        lines.append("")

    diag = data.get("diagnostics") or {}
    if diag:
        lines.append("-" * 72)
        lines.append(" DIAGNOSTICS")
        lines.append("-" * 72)
        lines.append(
            f" Regime {'OPEN' if diag.get('regime_ok') else 'CLOSED'}"
            f"  |  breadth {diag.get('breadth_pct')}% (needs >= "
            f"{diag.get('min_breadth_pct')}%)  |  mode {diag.get('regime_mode')}"
        )
        lines.append(f" Names meeting the GFS condition today: {diag.get('qualifying_today')}")
        rej = diag.get("rejections") or {}
        if rej:
            lines.append(
                " Rejections this run: "
                + ", ".join(f"{k}={v}" for k, v in rej.items())
            )
        note = diag.get("universe_note")
        if note:
            lines.append(f" {note}")
        lines.append("")

    cfg = data.get("config") or {}
    if cfg:
        lines.append("-" * 72)
        lines.append(" CONFIGURATION")
        lines.append("-" * 72)
        for key, value in cfg.items():
            lines.append(f" {key:<18}: {value}")
    return "\n".join(lines)
