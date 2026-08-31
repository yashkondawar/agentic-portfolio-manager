"""Position-monitoring stub: cheap deterministic invalidation-condition check.

Phase 2 scope is intentionally narrow: pull every ACTIVE/WATCH thesis from
thesis_tracker, look up each instrument's latest close, and flag anything
where we have no recent price at all (a data-quality breach worth a human's
attention) — this is NOT the full invalidation-condition parser (that needs
to interpret free-text conditions like "breaks below 50 DMA" against live
technicals, which is Phase 3 scope per the task spec). What this stub gives
the router is a real, callable py: step with a stable output contract that
escalation.py and the weekly HUMAN checkpoint can already build on.
"""
from __future__ import annotations

import sqlite3

from afund.derive.technicals import compute_technicals
from afund.memory import stores

STALE_PRICE_DAYS_FLAG = "no_recent_price"


def check_invalidations(conn: sqlite3.Connection) -> dict:
    """Check every active/watch thesis's instrument for a computable current
    price. Returns:

        {
          "checked": int,
          "breaches": [
            {"thesis_id": int, "instrument_id": int, "reason": str}
          ],
        }

    A "breach" here means the underlying price series couldn't be read at
    all (last_close is None) — a genuine gap that should surface to a human
    rather than silently be treated as "no signal." Real invalidation-text
    parsing (e.g. "if it closes below X") is future scope (Phase 3).
    """
    theses = stores.active_theses(conn)
    breaches: list[dict] = []

    for thesis in theses:
        instrument_id = thesis["instrument_id"]
        technicals = compute_technicals(conn, instrument_id=instrument_id)
        if technicals["last_close"] is None:
            breaches.append(
                {
                    "thesis_id": thesis["id"],
                    "instrument_id": instrument_id,
                    "reason": STALE_PRICE_DAYS_FLAG,
                }
            )

    return {"checked": len(theses), "breaches": breaches}
