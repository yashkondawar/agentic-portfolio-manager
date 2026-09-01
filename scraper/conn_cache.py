"""A per-connection memo for expensive scans of the market tape.

Several modules derive a lookup table by reading all of ``market_bars`` --
symbol/ISIN cross-references, canonical-name groups -- which costs 30-100
seconds on a 6M-row store. Those tables only change when new bars are
imported, so they want to be built once per connection and reused.

The obvious way to do that is to hang the value off the connection object.
That silently does not work: ``sqlite3.Connection`` is a C type with neither
``__dict__`` nor weak-reference support, so ``connection._cache = value``
raises ``AttributeError``. Code that wraps the assignment in a ``try`` (as this
project's first attempt did) therefore looks cached, passes its tests, and
rebuilds the table on every single call.

So the memo lives here instead, keyed by ``id(connection)``. The connection is
kept alongside its value, which pins it for as long as the entry lives and
stops a later object from reusing a freed id and colliding.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Callable, Dict, Tuple

_CACHE: Dict[Tuple[int, str], Tuple[sqlite3.Connection, Any]] = {}


def cached(
    connection: sqlite3.Connection, name: str, build: Callable[[], Any]
) -> Any:
    """Return ``build()`` for this connection, computing it at most once."""
    key = (id(connection), name)
    entry = _CACHE.get(key)
    if entry is not None and entry[0] is connection:
        return entry[1]
    value = build()
    _CACHE[key] = (connection, value)
    return value


def clear(connection: sqlite3.Connection = None, name: str = None) -> None:
    """Drop memoised values. Call after importing new bars.

    With no arguments the whole memo is dropped, which is what tests want.
    """
    if connection is None and name is None:
        _CACHE.clear()
        return
    for key in [
        key for key in _CACHE
        if (connection is None or key[0] == id(connection))
        and (name is None or key[1] == name)
    ]:
        del _CACHE[key]
