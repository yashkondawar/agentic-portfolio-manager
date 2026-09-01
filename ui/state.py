"""Shared Streamlit session state."""

from __future__ import annotations

from typing import Iterable

import streamlit as st


def initialize_state() -> None:
    defaults = {
        "symbol_basket": [],
        "latest_results": {},
        "broker": None,
        "broker_holdings": [],
        "broker_positions": [],
        "broker_swing_positions": [],
        "manual_holdings": [
            {"symbol": "", "quantity": 0.0, "buy_price": 0.0, "last_price": None}
        ],
        "manual_positions": [
            {
                "symbol": "",
                "quantity": 0.0,
                "buy_price": 0.0,
                "last_price": None,
                "entry_date": None,
                "target_pct": None,
                "stop_loss": None,
            }
        ],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def add_symbols(symbols: Iterable[str]) -> list[str]:
    existing = list(st.session_state.get("symbol_basket", []))
    seen = set(existing)
    for raw in symbols:
        symbol = str(raw).strip().upper().replace(".NS", "")
        if symbol and symbol not in seen:
            seen.add(symbol)
            existing.append(symbol)
    st.session_state["symbol_basket"] = existing
    return existing


def clear_symbols() -> None:
    st.session_state["symbol_basket"] = []
