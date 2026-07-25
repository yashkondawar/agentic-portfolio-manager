"""Daily scanner and persisted paper-portfolio workflow for 52-week breakouts."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo

from backtesting.swing_trading.data import PointInTimeData
from backtesting.swing_trading.portfolio import Portfolio, Position
from backtesting.swing_trading.watchlist import UniverseStock, load_universe

from . import strategy
from .calendar import EarningsCalendar
from .config import DATA_CACHE_DIR, BreakoutConfig

DEFAULT_STATE_PATH = (
    Path(__file__).resolve().parents[2]
    / ".trader_workbench"
    / "breakout_52w_portfolio.json"
)
STATE_VERSION = 3


def empty_state(capital: float) -> dict:
    return {
        "version": STATE_VERSION,
        "cash": float(capital),
        "positions": [],
        "pending_entries": [],
        "last_run_date": None,
    }


def load_state(path: Path, capital: float) -> dict:
    if not path.exists():
        return empty_state(capital)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read breakout portfolio state: {exc}") from exc
    return normalize_state(payload, capital)


def normalize_state(payload: Any, capital: float) -> dict:
    if payload in (None, {}):
        return empty_state(capital)
    if not isinstance(payload, dict):
        raise ValueError("portfolio_state must be a JSON object")

    positions = payload.get("positions", [])
    source_version = int(payload.get("version", 1))
    pending = (
        payload.get("pending_entries", []) if source_version >= STATE_VERSION else []
    )
    if not isinstance(positions, list) or not isinstance(pending, list):
        raise ValueError("portfolio_state positions and pending_entries must be lists")

    normalized_positions = [_normalize_position(item) for item in positions]
    normalized_pending = [_normalize_signal(item) for item in pending]
    last_run = payload.get("last_run_date")
    if last_run:
        last_run = date.fromisoformat(str(last_run)).isoformat()
    cash = float(payload.get("cash", capital))
    if cash < 0:
        raise ValueError("portfolio_state cash cannot be negative")

    return {
        "version": STATE_VERSION,
        "cash": cash,
        "positions": normalized_positions,
        "pending_entries": normalized_pending,
        "last_run_date": last_run,
    }


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_daily(
    cfg: BreakoutConfig,
    *,
    portfolio_state: Optional[dict] = None,
    symbols: Optional[Iterable[str]] = None,
    as_of: Optional[date] = None,
    max_new_entries: int = 5,
    persist_state: bool = True,
    reset_state: bool = False,
    adopt_state_override: bool = False,
    state_path: Path = DEFAULT_STATE_PATH,
) -> Dict[str, Any]:
    requested_day = _completed_session_cutoff(as_of)
    if reset_state:
        state = empty_state(cfg.starting_capital)
    elif portfolio_state:
        state = normalize_state(portfolio_state, cfg.starting_capital)
    else:
        state = load_state(state_path, cfg.starting_capital)

    custom_symbols = _normalize_symbols(symbols or [])
    universe = (
        [UniverseStock(symbol=symbol) for symbol in custom_symbols]
        if custom_symbols
        else load_universe(cfg)
    )
    tracked_symbols = {
        item["symbol"] for item in state["positions"] + state["pending_entries"]
    }
    existing = {item.symbol for item in universe}
    universe.extend(
        UniverseStock(symbol=symbol) for symbol in sorted(tracked_symbols - existing)
    )
    if not universe:
        raise ValueError("Daily breakout universe is empty")

    forward_days = max(10, cfg.earnings_blackout_sessions * 3)
    market_data = PointInTimeData(DATA_CACHE_DIR)
    market_data.load_or_download(
        symbols=[item.symbol for item in universe],
        benchmark=cfg.benchmark,
        start=requested_day,
        end=requested_day,
        warmup_days=cfg.warmup_days,
        forward_days=forward_days,
        use_cache=cfg.use_cache,
    )
    if market_data.benchmark is None or market_data.benchmark.empty:
        raise RuntimeError("Benchmark price data is unavailable")
    benchmark = market_data.benchmark.loc[: str(requested_day)]
    if benchmark.empty:
        raise RuntimeError(f"No completed market session on or before {requested_day}")
    session_day = benchmark.index[-1].date()

    earnings = EarningsCalendar(DATA_CACHE_DIR)
    if cfg.enforce_earnings_blackout:
        earnings.load_or_download(
            [item.symbol for item in universe],
            session_day,
            session_day + timedelta(days=forward_days),
            use_cache=cfg.use_cache,
        )
        if not earnings.available:
            raise RuntimeError(
                "NSE earnings calendar is unavailable; refusing to bypass "
                "the configured earnings-blackout guardrail"
            )

    portfolio = _portfolio_from_state(state, cfg)
    pending = [
        strategy.EntrySignal(**_signal_kwargs(item))
        for item in state["pending_entries"]
    ]
    last_run = (
        date.fromisoformat(state["last_run_date"])
        if state.get("last_run_date")
        else None
    )
    if last_run is not None and session_day < last_run:
        raise ValueError(
            f"portfolio_state was already processed through {last_run}; "
            f"cannot run it backward through {session_day}"
        )
    sessions = _unseen_sessions(market_data, last_run, session_day)

    filled: list[dict] = []
    rejected: list[dict] = []
    exits: list[dict] = []
    for day in sessions:
        opened = _fill_pending(
            day,
            pending,
            portfolio,
            market_data,
            cfg,
            filled,
            rejected,
            exits,
        )
        _manage_positions(
            day,
            opened,
            portfolio,
            market_data,
            cfg,
            exits,
        )

    regime_allows_entries = strategy.market_regime_allows_entries(
        market_data.benchmark_as_of(session_day), cfg
    )
    new_candidates: list[dict] = []
    if sessions and regime_allows_entries:
        new_candidates = _scan_new_entries(
            session_day,
            universe,
            pending,
            portfolio,
            market_data,
            earnings,
            cfg,
            max_new_entries,
        )
        pending.extend(
            strategy.EntrySignal(**_signal_kwargs(item)) for item in new_candidates
        )

    position_actions = exits + _hold_actions(session_day, portfolio, market_data)
    next_state = {
        "version": STATE_VERSION,
        "cash": round(portfolio.cash, 2),
        "positions": [
            _serialize_position(position) for position in portfolio.positions.values()
        ],
        "pending_entries": [_serialize_signal(signal) for signal in pending],
        "last_run_date": session_day.isoformat(),
    }
    may_write_override = not portfolio_state or adopt_state_override
    if (
        persist_state
        and may_write_override
        and (sessions or reset_state or portfolio_state)
    ):
        save_state(state_path, next_state)

    equity = portfolio.total_equity(_close_lookup(market_data, session_day))
    open_risk = _open_risk(portfolio)
    data = {
        "as_of": session_day.isoformat(),
        "universe": cfg.universe_index if not custom_symbols else "custom",
        "universe_size": len(universe),
        "regime_allows_entries": regime_allows_entries,
        "portfolio_equity": round(equity, 2),
        "cash": round(portfolio.cash, 2),
        "open_positions": len(portfolio.positions),
        "pending_entries_count": len(pending),
        "pending_entries": [_serialize_signal(signal) for signal in pending],
        "open_risk_pct": round(open_risk / equity * 100.0 if equity else 0.0, 2),
        "position_actions": position_actions,
        "new_entries": new_candidates,
        "filled_entries": filled,
        "rejected_entries": rejected,
        "portfolio_state": next_state,
        "state_path": (
            str(state_path) if persist_state and may_write_override else None
        ),
    }
    data["report"] = _render_report(data)
    return data


def _normalize_position(item: Any) -> dict:
    if not isinstance(item, dict):
        raise ValueError("Each portfolio position must be a JSON object")
    required = (
        "symbol",
        "quantity",
        "entry_price",
        "entry_date",
        "stop_loss",
        "initial_stop",
        "atr_at_entry",
        "breakout_level",
    )
    missing = [key for key in required if item.get(key) in (None, "")]
    if missing:
        raise ValueError(f"Position is missing required fields: {', '.join(missing)}")
    entry_date = date.fromisoformat(str(item["entry_date"])).isoformat()
    return {
        "symbol": _plain_symbol(item["symbol"]),
        "quantity": float(item["quantity"]),
        "entry_price": float(item["entry_price"]),
        "entry_date": entry_date,
        "stop_loss": float(item["stop_loss"]),
        "initial_stop": float(item["initial_stop"]),
        "atr_at_entry": float(item["atr_at_entry"]),
        "target_price": (
            float(item["target_price"])
            if item.get("target_price") is not None
            else None
        ),
        "breakout_level": float(item["breakout_level"]),
        "breakout_signal_date": (
            date.fromisoformat(str(item["breakout_signal_date"])).isoformat()
            if item.get("breakout_signal_date")
            else None
        ),
        "highest_high": float(item.get("highest_high") or item["entry_price"]),
        "below_breakout_closes": int(item.get("below_breakout_closes", 0)),
        "bars_held": int(item.get("bars_held", 0)),
        "trailing_active": bool(item.get("trailing_active", False)),
    }


def _normalize_signal(item: Any) -> dict:
    if not isinstance(item, dict):
        raise ValueError("Each pending entry must be a JSON object")
    required = {
        "symbol",
        "signal_date",
        "signal_close",
        "signal_low",
        "breakout_level",
        "atr",
        "volume_ratio",
        "average_volume_50",
        "average_turnover_cr",
        "score",
    }
    missing = sorted(required - set(item))
    if missing:
        raise ValueError(
            f"Pending entry is missing required fields: {', '.join(missing)}"
        )
    normalized = dict(item)
    normalized["symbol"] = _plain_symbol(item["symbol"])
    normalized["signal_date"] = date.fromisoformat(str(item["signal_date"])).isoformat()
    for key in required - {"symbol", "signal_date"}:
        normalized[key] = float(item[key])
    return normalized


def _portfolio_from_state(state: dict, cfg: BreakoutConfig) -> Portfolio:
    portfolio = Portfolio(cash=float(state["cash"]), commission_pct=cfg.commission_pct)
    for item in state["positions"]:
        position = Position(
            symbol=item["symbol"],
            quantity=float(item["quantity"]),
            entry_price=float(item["entry_price"]),
            entry_date=date.fromisoformat(item["entry_date"]),
            stop_loss=float(item["stop_loss"]),
            target_price=(
                float(item["target_price"])
                if item.get("target_price") is not None
                else strategy.profit_target(
                    float(item["entry_price"]), float(item["atr_at_entry"]), cfg
                )
            ),
            initial_stop=float(item["initial_stop"]),
            atr_at_entry=float(item["atr_at_entry"]),
            setup="52W Breakout",
            breakout_level=float(item["breakout_level"]),
            breakout_signal_date=(
                date.fromisoformat(item["breakout_signal_date"])
                if item.get("breakout_signal_date")
                else None
            ),
            highest_high=float(item["highest_high"]),
            below_breakout_closes=int(item["below_breakout_closes"]),
            bars_held=int(item["bars_held"]),
            trailing_active=bool(item["trailing_active"]),
        )
        portfolio.positions[position.symbol] = position
    return portfolio


def _unseen_sessions(
    data: PointInTimeData, last_run: Optional[date], session_day: date
) -> list[date]:
    if last_run is not None and last_run >= session_day:
        return []
    start = last_run + timedelta(days=1) if last_run else session_day
    return data.trading_days(start, session_day)


def _fill_pending(
    day: date,
    pending: list[strategy.EntrySignal],
    portfolio: Portfolio,
    data: PointInTimeData,
    cfg: BreakoutConfig,
    filled: list[dict],
    rejected: list[dict],
    exits: list[dict],
) -> set[str]:
    opened: set[str] = set()
    remaining: list[strategy.EntrySignal] = []
    equity = portfolio.total_equity(_open_lookup(data, day))
    for signal in pending:
        if signal.signal_date >= day:
            remaining.append(signal)
            continue
        bar = data.bar_on(signal.symbol, day)
        if bar is None:
            remaining.append(signal)
            continue
        if (
            signal.symbol in portfolio.positions
            or len(portfolio.positions) >= cfg.max_positions
        ):
            rejected.append(
                {
                    "symbol": signal.symbol,
                    "action": "ENTRY-REJECTED",
                    "reason": "position capacity",
                    "date": day.isoformat(),
                }
            )
            continue
        fill = float(bar["Open"])
        if not (
            signal.breakout_level
            < fill
            <= signal.breakout_level + cfg.max_extension_atr * signal.atr
        ):
            rejected.append(
                {
                    "symbol": signal.symbol,
                    "action": "ENTRY-REJECTED",
                    "reason": "opening price outside breakout entry zone",
                    "date": day.isoformat(),
                    "open": round(fill, 2),
                }
            )
            continue
        shares, stop = strategy.size_position(
            fill,
            signal,
            equity,
            portfolio.cash,
            _open_risk(portfolio),
            cfg,
        )
        if shares <= 0:
            rejected.append(
                {
                    "symbol": signal.symbol,
                    "action": "ENTRY-REJECTED",
                    "reason": "insufficient cash or portfolio risk capacity",
                    "date": day.isoformat(),
                }
            )
            continue
        position = Position(
            symbol=signal.symbol,
            quantity=shares,
            entry_price=fill,
            entry_date=day,
            stop_loss=stop,
            target_price=strategy.profit_target(fill, signal.atr, cfg),
            initial_stop=stop,
            atr_at_entry=signal.atr,
            setup="52W Breakout",
            breakout_level=signal.breakout_level,
            breakout_signal_date=signal.signal_date,
            highest_high=fill,
        )
        if not portfolio.open_position(position):
            rejected.append(
                {
                    "symbol": signal.symbol,
                    "action": "ENTRY-REJECTED",
                    "reason": "insufficient cash after costs",
                    "date": day.isoformat(),
                }
            )
            continue
        opened.add(signal.symbol)
        equity = portfolio.total_equity(_open_lookup(data, day))
        filled.append(
            {
                "symbol": signal.symbol,
                "action": "ENTERED",
                "date": day.isoformat(),
                "quantity": shares,
                "entry_price": round(fill, 2),
                "stop_loss": round(stop, 2),
                "target_price": round(position.target_price, 2),
                "breakout_level": round(signal.breakout_level, 2),
            }
        )
        if float(bar["Low"]) <= stop:
            trade = portfolio.close_position(signal.symbol, stop, day, "ENTRY-DAY-STOP")
            opened.discard(signal.symbol)
            if trade is not None:
                exits.append(
                    {
                        "symbol": signal.symbol,
                        "action": "EXIT",
                        "reason": "ENTRY-DAY-STOP",
                        "date": day.isoformat(),
                        "exit_price": round(stop, 2),
                        "pnl": round(trade.pnl, 2),
                        "pnl_pct": round(trade.pnl_pct, 2),
                    }
                )
        elif float(bar["High"]) >= position.target_price:
            trade = portfolio.close_position(
                signal.symbol,
                position.target_price,
                day,
                "ENTRY-DAY-TARGET",
            )
            opened.discard(signal.symbol)
            if trade is not None:
                exits.append(
                    {
                        "symbol": signal.symbol,
                        "action": "EXIT",
                        "reason": "ENTRY-DAY-TARGET",
                        "date": day.isoformat(),
                        "exit_price": round(position.target_price, 2),
                        "pnl": round(trade.pnl, 2),
                        "pnl_pct": round(trade.pnl_pct, 2),
                    }
                )
    pending[:] = remaining
    return opened


def _manage_positions(
    day: date,
    opened: set[str],
    portfolio: Portfolio,
    data: PointInTimeData,
    cfg: BreakoutConfig,
    exits: list[dict],
) -> None:
    for symbol in list(portfolio.positions):
        if symbol in opened:
            continue
        bar = data.bar_on(symbol, day)
        history = data.as_of(symbol, day, lookback_rows=300)
        if bar is None or history is None or history.empty:
            continue
        position = portfolio.positions[symbol]
        for operation in strategy.evaluate_exit(position, bar, history, cfg):
            trade = portfolio.close_position(
                symbol, operation.price, day, operation.reason
            )
            if trade is not None:
                exits.append(
                    {
                        "symbol": symbol,
                        "action": "EXIT",
                        "reason": operation.reason,
                        "date": day.isoformat(),
                        "exit_price": round(operation.price, 2),
                        "pnl": round(trade.pnl, 2),
                        "pnl_pct": round(trade.pnl_pct, 2),
                    }
                )


def _scan_new_entries(
    day: date,
    universe: list[UniverseStock],
    pending: list[strategy.EntrySignal],
    portfolio: Portfolio,
    data: PointInTimeData,
    earnings: EarningsCalendar,
    cfg: BreakoutConfig,
    max_new_entries: int,
) -> list[dict]:
    trading_days = _future_business_sessions(day, cfg.earnings_blackout_sessions)
    unavailable = set(portfolio.positions) | {signal.symbol for signal in pending}
    metadata = {item.symbol: item for item in universe}
    candidates: list[strategy.EntrySignal] = []
    for item in universe:
        if item.symbol in unavailable or data.bar_on(item.symbol, day) is None:
            continue
        if cfg.enforce_earnings_blackout and earnings.has_event_within(
            item.symbol, day, trading_days, cfg.earnings_blackout_sessions
        ):
            continue
        history = data.as_of(item.symbol, day, lookback_rows=400)
        signal = strategy.compute_entry_signal(
            history,
            data.benchmark_as_of(day),
            item.symbol,
            day,
            cfg,
        )
        if signal is not None:
            candidates.append(signal)

    candidates.sort(key=lambda item: item.score, reverse=True)
    capacity = max(0, cfg.max_positions - len(portfolio.positions) - len(pending))
    equity = portfolio.total_equity(_close_lookup(data, day))
    open_risk = _open_risk(portfolio)
    output = []
    for signal in candidates:
        if len(output) >= min(max_new_entries, capacity):
            break
        quantity, stop = strategy.size_position(
            signal.signal_close,
            signal,
            equity,
            portfolio.cash,
            open_risk,
            cfg,
        )
        if quantity <= 0:
            continue
        item = metadata[signal.symbol]
        output.append(
            {
                **_serialize_signal(signal),
                "action": "ENTER-NEXT-OPEN",
                "company": item.company,
                "industry": item.industry,
                "entry_above": round(signal.breakout_level, 2),
                "entry_not_above": round(
                    signal.breakout_level + cfg.max_extension_atr * signal.atr,
                    2,
                ),
                "indicative_quantity": quantity,
                "indicative_stop": round(stop, 2),
                "indicative_target": round(
                    strategy.profit_target(signal.signal_close, signal.atr, cfg),
                    2,
                ),
            }
        )
    return output


def _hold_actions(day: date, portfolio: Portfolio, data: PointInTimeData) -> list[dict]:
    output = []
    for position in portfolio.positions.values():
        bar = data.bar_on(position.symbol, day)
        price = float(bar["Close"]) if bar is not None else position.entry_price
        output.append(
            {
                "symbol": position.symbol,
                "action": "HOLD",
                "current_price": round(price, 2),
                "entry_price": round(position.entry_price, 2),
                "pnl_pct": round(position.pnl_pct(price), 2),
                "stop_loss": round(position.stop_loss, 2),
                "target_price": round(position.target_price, 2),
                "breakout_level": round(position.breakout_level, 2),
                "bars_held": position.bars_held,
                "trailing_active": position.trailing_active,
            }
        )
    return output


def _serialize_position(position: Position) -> dict:
    return {
        "symbol": position.symbol,
        "quantity": position.quantity,
        "entry_price": round(position.entry_price, 4),
        "entry_date": position.entry_date.isoformat(),
        "stop_loss": round(position.stop_loss, 4),
        "initial_stop": round(position.initial_stop, 4),
        "atr_at_entry": round(position.atr_at_entry, 4),
        "target_price": round(position.target_price, 4),
        "breakout_level": round(position.breakout_level, 4),
        "breakout_signal_date": (
            position.breakout_signal_date.isoformat()
            if position.breakout_signal_date
            else None
        ),
        "highest_high": round(position.highest_high, 4),
        "below_breakout_closes": position.below_breakout_closes,
        "bars_held": position.bars_held,
        "trailing_active": position.trailing_active,
    }


def _serialize_signal(signal: strategy.EntrySignal) -> dict:
    payload = asdict(signal)
    payload["signal_date"] = signal.signal_date.isoformat()
    return payload


def _signal_kwargs(item: dict) -> dict:
    allowed = set(strategy.EntrySignal.__dataclass_fields__)
    payload = {key: item[key] for key in allowed}
    payload["signal_date"] = date.fromisoformat(str(payload["signal_date"]))
    return payload


def _open_risk(portfolio: Portfolio) -> float:
    return sum(
        max(position.entry_price - position.stop_loss, 0.0) * position.quantity
        for position in portfolio.positions.values()
    )


def _open_lookup(data: PointInTimeData, day: date):
    def lookup(symbol: str) -> Optional[float]:
        bar = data.bar_on(symbol, day)
        return float(bar["Open"]) if bar is not None else None

    return lookup


def _close_lookup(data: PointInTimeData, day: date):
    def lookup(symbol: str) -> Optional[float]:
        bar = data.bar_on(symbol, day)
        return float(bar["Close"]) if bar is not None else None

    return lookup


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    result = []
    seen = set()
    for raw in symbols:
        symbol = _plain_symbol(raw)
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def _plain_symbol(value: Any) -> str:
    return str(value).strip().upper().replace(".NS", "").replace(".BO", "")


def _future_business_sessions(day: date, count: int) -> list[date]:
    sessions = []
    candidate = day + timedelta(days=1)
    while len(sessions) < count:
        if candidate.weekday() < 5:
            sessions.append(candidate)
        candidate += timedelta(days=1)
    return sessions


def _completed_session_cutoff(as_of: Optional[date]) -> date:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    requested = as_of or now.date()
    if requested > now.date():
        requested = now.date()
    if requested == now.date() and now.time() < time(16, 0):
        requested -= timedelta(days=1)
    return requested


def _render_report(data: dict) -> str:
    regime = "ON" if data["regime_allows_entries"] else "OFF - no new longs"
    lines = [
        "# 52-Week Breakout Daily Review",
        "",
        f"**As of:** {data['as_of']}  ",
        f"**Universe:** {data['universe']} ({data['universe_size']} symbols)  ",
        f"**Market regime:** {regime}  ",
        f"**Portfolio:** ₹{data['portfolio_equity']:,.2f} equity, "
        f"₹{data['cash']:,.2f} cash, {data['open_positions']} open, "
        f"{data['open_risk_pct']:.2f}% open risk",
        "",
        "## Existing positions",
    ]
    actions = data["position_actions"]
    if not actions:
        lines.append("- No open positions or exits this run.")
    for item in actions:
        if item["action"] == "EXIT":
            lines.append(
                f"- **{item['symbol']} EXIT** - {item['reason']} at "
                f"₹{item['exit_price']:,.2f} ({item['pnl_pct']:+.2f}%)."
            )
        else:
            trail = "active" if item["trailing_active"] else "not active"
            lines.append(
                f"- **{item['symbol']} HOLD** at ₹{item['current_price']:,.2f}; "
                f"stop ₹{item['stop_loss']:,.2f}; P&L {item['pnl_pct']:+.2f}%; "
                f"target ₹{item['target_price']:,.2f}; trail {trail}."
            )
    lines.extend(["", "## New entries"])
    if not data["new_entries"]:
        lines.append("- No new qualifying breakouts.")
    for item in data["new_entries"]:
        lines.append(
            f"- **{item['symbol']} ENTER NEXT OPEN** only in "
            f"₹{item['entry_above']:,.2f}-₹{item['entry_not_above']:,.2f}; "
            f"indicative {item['indicative_quantity']} shares, "
            f"stop ₹{item['indicative_stop']:,.2f}, "
            f"target ₹{item['indicative_target']:,.2f}, "
            f"RVOL {item['volume_ratio']:.2f}x."
        )
    if data["pending_entries"]:
        lines.extend(["", "## Pending for next open"])
        for item in data["pending_entries"]:
            lines.append(
                f"- **{item['symbol']}** signal from {item['signal_date']}; "
                f"breakout ₹{item['breakout_level']:,.2f}, "
                f"signal close ₹{item['signal_close']:,.2f}."
            )
    if data["filled_entries"]:
        lines.extend(["", "## Filled from prior signals"])
        for item in data["filled_entries"]:
            lines.append(
                f"- **{item['symbol']} entered** {item['quantity']} shares at "
                f"₹{item['entry_price']:,.2f}; stop ₹{item['stop_loss']:,.2f}; "
                f"target ₹{item['target_price']:,.2f}."
            )
    if data["rejected_entries"]:
        lines.extend(["", "## Lapsed/rejected entries"])
        for item in data["rejected_entries"]:
            lines.append(f"- **{item['symbol']}** - {item['reason']}.")
    return "\n".join(lines)
