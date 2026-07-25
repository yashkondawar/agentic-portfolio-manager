"""Read-only Zerodha facade for decision-support surfaces."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import ZerodhaClient


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
                "quantity": item.get("quantity", 0),
                "buy_price": item.get("average_price", 0),
                "last_price": item.get("last_price"),
            }
            for item in self.holdings()
            if item.get("quantity", 0) > 0
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
