"""Cached NSE result dates used by the earnings-blackout guardrail."""

from __future__ import annotations

import pickle
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Dict, Iterable, Set


def _plain_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".NS", "").replace(".BO", "")


class EarningsCalendar:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.events: Dict[str, Set[date]] = {}
        self.available = False

    def load_or_download(
        self,
        symbols: Iterable[str],
        start: date,
        end: date,
        *,
        use_cache: bool = True,
    ) -> None:
        wanted = sorted({_plain_symbol(symbol) for symbol in symbols})
        identity = sha256("|".join(wanted).encode("utf-8")).hexdigest()[:12]
        path = self.cache_dir / (
            f"earnings_{identity}_{start.isoformat()}_{end.isoformat()}.pkl"
        )
        if use_cache and path.exists():
            with path.open("rb") as handle:
                payload = pickle.load(handle)
            self.events = payload["events"]
            self.available = bool(payload["available"])
            return

        from scraper.nse_events import results_event_calendar

        market = results_event_calendar(start, end)
        self.available = bool(market)
        self.events = {
            symbol: set(market.get(symbol, {}).values()) for symbol in wanted
        }
        with path.open("wb") as handle:
            pickle.dump(
                {"events": self.events, "available": self.available},
                handle,
            )

    def has_event_within(
        self,
        symbol: str,
        day: date,
        trading_days: list[date],
        sessions: int,
    ) -> bool:
        future = [session for session in trading_days if session > day]
        if not future or sessions <= 0:
            return False
        cutoff = future[min(sessions, len(future)) - 1]
        return any(
            day < event_day <= cutoff
            for event_day in self.events.get(_plain_symbol(symbol), set())
        )
