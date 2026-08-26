"""
state.py
========

The persisted book.

The live strategy is the backtest engine resumed. That only works if *all* of
the engine's mutable state survives between runs - not just the positions:

* ``cash`` and the realised tradebook, obviously.
* ``pending_entries`` / ``pending_exits``. These are the whole reason the
  backtest is causal. A signal seen at Monday's close is filled at Tuesday's
  open; if the queue were dropped between runs, the live strategy would either
  lose the trade or fill it at the wrong price, and it would no longer be the
  thing that was tested.
* ``equity_curve``, so the strategy can report its own track record rather than
  re-deriving one.
* ``last_session`` - the last date already simulated. The next run resumes from
  the session after it, which makes a missed day, a weekend or a two-week
  holiday self-healing: the engine simply replays the gap.

Storage is ``core.storage``'s document table under the ``gfs`` namespace, the
same key-value mechanism ``qtr_results`` uses. Adding a bespoke table would
require bumping the schema version, which existing databases reject outright.
"""

from __future__ import annotations

import logging
from dataclasses import fields, is_dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from backtesting.gfs.engine import GFSBacktestEngine
from backtesting.gfs.portfolio import ClosedTrade, Position
from backtesting.gfs.strategy import EntrySignal, ExitOp

from core.storage import delete_document, get_document, set_document

from .config import DOC_NAMESPACE

logger = logging.getLogger("gfs.state")

BOOK_KEY = "book"
LAST_RUN_KEY = "last_run"

#: Bumped when the serialised shape changes in a way older books cannot satisfy.
BOOK_VERSION = 1


# ── (de)serialisation ────────────────────────────────────────────────────────


def _dump(obj: Any) -> Dict[str, Any]:
    """Dataclass -> JSON-safe dict (dates become ISO strings)."""
    out: Dict[str, Any] = {}
    for f in fields(obj):
        value = getattr(obj, f.name)
        out[f.name] = value.isoformat() if isinstance(value, date) else value
    return out


def _load(cls, payload: Dict[str, Any]):
    """JSON-safe dict -> dataclass, tolerating fields added since it was written.

    Unknown keys are dropped and missing keys fall back to the dataclass default,
    so a book written by an older build still opens.
    """
    if not is_dataclass(cls):  # pragma: no cover - defensive
        raise TypeError(f"{cls!r} is not a dataclass")
    kwargs: Dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in payload:
            continue
        value = payload[f.name]
        if f.type in ("date", date) and isinstance(value, str):
            value = date.fromisoformat(value)
        kwargs[f.name] = value
    return cls(**kwargs)


class Book:
    """Everything that has to survive between two daily runs."""

    def __init__(self) -> None:
        self.version: int = BOOK_VERSION
        self.cash: float = 0.0
        self.positions: Dict[str, Position] = {}
        self.closed: List[ClosedTrade] = []
        self.equity_curve: List[dict] = []
        self.pending_entries: List[EntrySignal] = []
        self.pending_exits: List[Tuple[str, ExitOp]] = []
        self.last_session: Optional[date] = None
        self.opened_on: Optional[date] = None
        self.starting_capital: float = 0.0
        # Display-only. The last run's close and RSI triplet per open symbol, so
        # the offline panel can show a real mark instead of the entry price.
        # Never restored into the engine - it cannot affect a decision.
        self.marks: Dict[str, Dict[str, Any]] = {}

    # ── lifecycle ────────────────────────────────────────────────────────────

    @property
    def is_empty(self) -> bool:
        """True when no session has ever been simulated into this book."""
        return self.last_session is None

    def open_with(self, capital: float, first_session: date) -> None:
        self.cash = float(capital)
        self.starting_capital = float(capital)
        self.opened_on = first_session

    # ── engine bridge ────────────────────────────────────────────────────────

    def restore_into(self, engine: GFSBacktestEngine) -> None:
        """Seed a fresh engine with this book's state.

        ``engine.daily_log`` is the *same list object* as
        ``engine.pf.equity_curve`` (the engine binds them deliberately), so the
        curve is restored by mutating in place rather than rebinding - rebinding
        would silently split the two and the daily log would stop growing.
        """
        engine.pf.cash = self.cash
        engine.pf.positions = {sym: pos for sym, pos in self.positions.items()}
        engine.pf.closed = list(self.closed)
        engine.pf.equity_curve.clear()
        engine.pf.equity_curve.extend(self.equity_curve)
        engine.pending_entries = list(self.pending_entries)
        engine.pending_exits = list(self.pending_exits)

    def capture_from(self, engine: GFSBacktestEngine) -> None:
        self.cash = float(engine.pf.cash)
        self.positions = dict(engine.pf.positions)
        self.closed = list(engine.pf.closed)
        self.equity_curve = list(engine.pf.equity_curve)
        self.pending_entries = list(engine.pending_entries)
        self.pending_exits = list(engine.pending_exits)

    # ── documents ────────────────────────────────────────────────────────────

    def to_document(self) -> Dict[str, Any]:
        """Serialise. Nothing here is rounded on purpose.

        Rounding the cash balance to four decimals was enough, on its own, to
        make a resumed book diverge from a one-shot run - a resumed position
        could then be sized one share differently. Anything the engine reads
        back is stored at full precision; rounding belongs in the report, not in
        the state.
        """
        return {
            "version": self.version,
            "cash": self.cash,
            "starting_capital": self.starting_capital,
            "opened_on": self.opened_on.isoformat() if self.opened_on else None,
            "last_session": self.last_session.isoformat() if self.last_session else None,
            "positions": [_dump(p) for p in self.positions.values()],
            "closed": [_dump(t) for t in self.closed],
            "equity_curve": self.equity_curve,
            "pending_entries": [_dump(s) for s in self.pending_entries],
            "pending_exits": [
                {"symbol": sym, "op": _dump(op)} for sym, op in self.pending_exits
            ],
            "marks": self.marks,
        }

    @classmethod
    def from_document(cls, doc: Optional[Dict[str, Any]]) -> "Book":
        book = cls()
        if not doc:
            return book
        version = int(doc.get("version") or 0)
        if version > BOOK_VERSION:
            raise RuntimeError(
                f"The saved GFS book is version {version}, but this build only "
                f"understands {BOOK_VERSION}. Upgrade the app or reset the book."
            )
        book.version = BOOK_VERSION
        book.cash = float(doc.get("cash") or 0.0)
        book.starting_capital = float(doc.get("starting_capital") or 0.0)
        opened = doc.get("opened_on")
        book.opened_on = date.fromisoformat(opened) if opened else None
        last = doc.get("last_session")
        book.last_session = date.fromisoformat(last) if last else None
        book.positions = {
            p["symbol"]: _load(Position, p) for p in (doc.get("positions") or [])
        }
        book.closed = [_load(ClosedTrade, t) for t in (doc.get("closed") or [])]
        book.equity_curve = list(doc.get("equity_curve") or [])
        book.pending_entries = [
            _load(EntrySignal, s) for s in (doc.get("pending_entries") or [])
        ]
        book.pending_exits = [
            (row["symbol"], _load(ExitOp, row["op"]))
            for row in (doc.get("pending_exits") or [])
        ]
        book.marks = dict(doc.get("marks") or {})
        return book


# ── module-level API ─────────────────────────────────────────────────────────


def load_book() -> Book:
    return Book.from_document(get_document(DOC_NAMESPACE, BOOK_KEY))


def save_book(book: Book) -> None:
    set_document(DOC_NAMESPACE, BOOK_KEY, book.to_document())


def reset_book() -> None:
    """Delete the book. Irreversible - the tradebook goes with it."""
    delete_document(DOC_NAMESPACE, BOOK_KEY)
    logger.warning("GFS book deleted.")


def load_last_run() -> Dict[str, Any]:
    return get_document(DOC_NAMESPACE, LAST_RUN_KEY, {}) or {}


def save_last_run(payload: Dict[str, Any]) -> None:
    set_document(DOC_NAMESPACE, LAST_RUN_KEY, payload)
