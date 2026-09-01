"""Read-only Zerodha facade for decision-support surfaces."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import ZerodhaClient

# Kite reports derivatives on their own exchanges; a swing equity book ignores
# them. Anything without an exchange (e.g. a stubbed client) is treated as cash.
_EQUITY_EXCHANGES = {"NSE", "BSE", "NSE_EQ", "BSE_EQ"}


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _holding_quantity(item: Dict[str, Any]) -> float:
    """Total owned stock, including shares bought in the previous session.

    ``quantity`` counts only settled stock. A buy from the previous session sits
    in ``t1_quantity`` until it settles, so counting ``quantity`` alone hides a
    position that is very much open — and hides it precisely when it matters
    most, right after entry.
    """
    return _as_float(item.get("quantity")) + _as_float(item.get("t1_quantity"))


def _is_equity_delivery(item: Dict[str, Any]) -> bool:
    """True for a cash-segment delivery leg (not an intraday or F&O position)."""
    exchange = str(item.get("exchange") or "").upper()
    if exchange and exchange not in _EQUITY_EXCHANGES:
        return False
    return str(item.get("product") or "").upper() != "MIS"


def _merge_position(
    merged: Dict[str, Dict[str, Any]], item: Dict[str, Any], quantity: float
) -> None:
    """Fold one Kite row into ``merged``, cost-averaging a repeated symbol."""
    symbol = str(item.get("tradingsymbol") or "").strip().upper()
    if not symbol or quantity <= 0:
        return
    price = _as_float(item.get("average_price"))
    existing = merged.get(symbol)
    if existing is None:
        merged[symbol] = {
            "symbol": symbol,
            "quantity": quantity,
            "buy_price": price,
            "last_price": item.get("last_price"),
        }
        return
    total = existing["quantity"] + quantity
    existing["buy_price"] = (
        (existing["buy_price"] * existing["quantity"] + price * quantity) / total
        if total
        else price
    )
    existing["quantity"] = total
    if existing.get("last_price") is None:
        existing["last_price"] = item.get("last_price")


class ReadOnlyZerodha:
    """Expose account data and authentication without any order methods."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        self._client = ZerodhaClient(api_key=api_key, api_secret=api_secret)

    @property
    def is_authenticated(self) -> bool:
        return self._client.is_authenticated

    @property
    def login_url(self) -> str:
        return self._client.login_url

    def authenticate(self, request_token: str) -> bool:
        token = request_token.strip()
        if not token:
            raise ValueError("A Zerodha request token is required")
        return self._client.authenticate(token)

    def authenticate_in_browser(self, timeout: int = 120) -> bool:
        """Open Kite login and complete authentication through the local callback."""
        from .auth_server import run_auth_flow

        self._client = run_auth_flow(
            api_key=self._client.api_key,
            api_secret=self._client.api_secret,
            timeout=timeout,
        )
        return self._client.is_authenticated

    def profile(self) -> Dict[str, Any]:
        return self._client.get_profile()

    def margins(self) -> Dict[str, Any]:
        return self._client.get_margins()

    def available_cash(self) -> float:
        return self._client.get_available_cash()

    def holdings(self) -> List[Dict[str, Any]]:
        return self._client.get_holdings()

    def positions(self) -> Dict[str, List[Dict[str, Any]]]:
        return self._client.get_positions()

    def orders(self) -> List[Dict[str, Any]]:
        return self._client.get_orders()

    def holdings_for_strategy(self) -> List[Dict[str, Any]]:
        return [
            {
                "symbol": item.get("tradingsymbol", ""),
                "quantity": quantity,
                "buy_price": item.get("average_price", 0),
                "last_price": item.get("last_price"),
            }
            for item, quantity in (
                (item, _holding_quantity(item)) for item in self.holdings()
            )
            if quantity > 0
        ]

    def positions_for_strategy(self) -> List[Dict[str, Any]]:
        net = self.positions().get("net", [])
        return [
            {
                "symbol": item.get("tradingsymbol", ""),
                "quantity": abs(item.get("quantity", 0)),
                "buy_price": item.get("average_price", 0),
                "last_price": item.get("last_price"),
            }
            for item in net
            if item.get("quantity", 0) > 0
        ]

    def swing_positions(self) -> List[Dict[str, Any]]:
        """Open multi-day (delivery) trades — what a swing desk actually holds.

        Kite splits one delivery trade across two books depending on its age: a
        CNC buy placed today appears only in ``positions()["net"]`` and migrates
        into ``holdings()`` after settlement. Reading either book alone is wrong:

        * ``positions()`` alone (what the Swing Desk used to read) is **empty**
          for a delivery-only account, because settled stock is not a "position"
          to Kite. That is why the page reported no snapshot while the Portfolio
          page, which reads holdings, loaded fine.
        * ``holdings()`` alone misses a trade opened today.

        So we merge both, keyed by symbol, and combine quantities with a
        cost-weighted average buy price when a symbol appears in each. Intraday
        (MIS) and derivatives legs are excluded — they are not swing trades.
        """
        merged: Dict[str, Dict[str, Any]] = {}
        for item in self.holdings():
            _merge_position(merged, item, _holding_quantity(item))
        for item in self.positions().get("net", []):
            if not _is_equity_delivery(item):
                continue
            _merge_position(merged, item, _as_float(item.get("quantity")))
        return list(merged.values())
