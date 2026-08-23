"""
Zerodha Kite Connect client wrapper.

Handles authentication, order management, portfolio queries, and position tracking.
Supports two auth modes:
1. Auto-login: Flask server captures request_token via redirect callback
2. Manual: Paste request_token or access_token in .env

Usage:
    from zerodha.client import ZerodhaClient
    client = ZerodhaClient()
    client.login()  # Opens browser for login
    client.place_order("RELIANCE", "BUY", quantity=10, price=1350)
"""

import os
import json
import logging
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, date

from kiteconnect import KiteConnect
from core.storage import get_document, set_document

logger = logging.getLogger(__name__)

# Legacy token location, imported once when present.
LEGACY_TOKEN_FILE = Path(
    os.getenv("ZERODHA_TOKEN_FILE", "").strip()
    or str(Path.home() / ".agentic-portfolio-manager" / "zerodha_access_token.json")
).expanduser()


class ZerodhaClient:
    """Wrapper around KiteConnect with auth management and order helpers."""

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key or os.getenv("ZERODHA_API_KEY", "")
        self.api_secret = api_secret or os.getenv("ZERODHA_API_SECRET", "")

        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Zerodha API key and secret required. "
                "Set ZERODHA_API_KEY and ZERODHA_API_SECRET in .env"
            )

        self.kite = KiteConnect(api_key=self.api_key)
        self._access_token: Optional[str] = None
        self._is_authenticated = False

        # Try to load saved token
        self._load_saved_token()

    def _load_saved_token(self):
        """Load previously saved access token if still valid (same day)."""
        data = get_document("credentials", "zerodha_access_token")
        if data is None and LEGACY_TOKEN_FILE.exists():
            try:
                data = json.loads(LEGACY_TOKEN_FILE.read_text(encoding="utf-8"))
                set_document("credentials", "zerodha_access_token", data)
            except (json.JSONDecodeError, OSError):
                data = None
        if isinstance(data, dict):
            saved_date = data.get("date", "")
            token = data.get("access_token", "")
            if saved_date == date.today().isoformat() and token:
                self.kite.set_access_token(token)
                self._access_token = token
                self._is_authenticated = True
                logger.info("[ZERODHA] Loaded saved access token (valid for today)")

    def _save_token(self, access_token: str):
        """Save access token for reuse within the same trading day."""
        set_document(
            "credentials",
            "zerodha_access_token",
            {
                "access_token": access_token,
                "date": date.today().isoformat(),
                "saved_at": datetime.now().isoformat(),
            },
        )
        logger.info("[ZERODHA] Access token saved for today")

    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self._is_authenticated

    @property
    def login_url(self) -> str:
        """Get the Kite login URL."""
        return self.kite.login_url()

    def authenticate(self, request_token: str) -> bool:
        """
        Complete authentication with a request_token.
        This is called after the user logs in via browser.
        """
        try:
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            access_token = data["access_token"]
            self.kite.set_access_token(access_token)
            self._access_token = access_token
            self._is_authenticated = True
            self._save_token(access_token)
            logger.info(
                "[ZERODHA] Authentication successful. User: %s",
                data.get("user_name", "N/A"),
            )
            return True
        except Exception as e:
            logger.error(f"[ZERODHA] Authentication failed: {e}")
            return False

    def set_access_token(self, access_token: str):
        """Directly set access token (for manual/pre-authenticated sessions)."""
        self.kite.set_access_token(access_token)
        self._access_token = access_token
        self._is_authenticated = True
        self._save_token(access_token)
        logger.info("[ZERODHA] Access token set manually")

    def login(self, auto_open_browser: bool = True) -> str:
        """
        Initiate login flow.
        Returns the login URL. If auto_open_browser is True, opens it in default browser.
        After login, call authenticate(request_token) with the token from redirect.
        """
        url = self.login_url
        if auto_open_browser:
            webbrowser.open(url)
            logger.info(f"[ZERODHA] Browser opened for login. URL: {url}")
        else:
            logger.info(f"[ZERODHA] Open this URL to login: {url}")
        return url

    # ─── Account Info ────────────────────────────────────────────────────────

    def get_profile(self) -> Dict[str, Any]:
        """Get user profile."""
        self._ensure_auth()
        return self.kite.profile()

    def get_margins(self) -> Dict[str, Any]:
        """Get account margins (available cash, used margin, etc.)."""
        self._ensure_auth()
        return self.kite.margins()

    def get_available_cash(self) -> float:
        """Get available cash for trading."""
        margins = self.get_margins()
        equity = margins.get("equity", {})
        return float(equity.get("available", {}).get("cash", 0))

    # ─── Portfolio & Positions ───────────────────────────────────────────────

    def get_holdings(self) -> List[Dict[str, Any]]:
        """Get long-term holdings (CNC/delivery positions)."""
        self._ensure_auth()
        return self.kite.holdings()

    def get_positions(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get day and net positions."""
        self._ensure_auth()
        return self.kite.positions()

    def get_orders(self) -> List[Dict[str, Any]]:
        """Get all orders for today."""
        self._ensure_auth()
        return self.kite.orders()

    # ─── Order Placement ─────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        transaction_type: str,  # "BUY" or "SELL"
        quantity: int,
        price: Optional[float] = None,
        order_type: str = "MARKET",
        product: str = "CNC",
        exchange: str = "NSE",
        trigger_price: Optional[float] = None,
        stoploss: Optional[float] = None,
        target: Optional[float] = None,
        validity: str = "DAY",
        tag: str = "agentic_system",
    ) -> Dict[str, Any]:
        """
        Place an order on Zerodha.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE", "TCS", "INFY")
            transaction_type: "BUY" or "SELL"
            quantity: Number of shares
            price: Limit price (required for LIMIT orders)
            order_type: "MARKET", "LIMIT", "SL", "SL-M"
            product: "CNC" (delivery), "MIS" (intraday), "NRML" (F&O)
            exchange: "NSE" or "BSE"
            trigger_price: For SL/SL-M orders
            stoploss: If provided, places a bracket order with SL
            target: If provided, places a bracket order with target
            validity: "DAY" or "IOC"
            tag: Order tag for tracking

        Returns:
            Dict with order_id and status
        """
        self._ensure_auth()

        # Clean symbol
        symbol = symbol.strip().upper().replace(".NS", "").replace(".BO", "")

        # Determine variety
        if stoploss and target:
            variety = self.kite.VARIETY_BO
        elif stoploss:
            variety = self.kite.VARIETY_REGULAR  # Will place SL order separately
        else:
            variety = self.kite.VARIETY_REGULAR

        # Map order type
        order_type_map = {
            "MARKET": self.kite.ORDER_TYPE_MARKET,
            "LIMIT": self.kite.ORDER_TYPE_LIMIT,
            "SL": self.kite.ORDER_TYPE_SL,
            "SL-M": self.kite.ORDER_TYPE_SLM,
        }
        kite_order_type = order_type_map.get(order_type.upper(), self.kite.ORDER_TYPE_MARKET)

        # Map transaction type
        kite_txn = (
            self.kite.TRANSACTION_TYPE_BUY
            if transaction_type.upper() == "BUY"
            else self.kite.TRANSACTION_TYPE_SELL
        )

        # Map product
        product_map = {
            "CNC": self.kite.PRODUCT_CNC,
            "MIS": self.kite.PRODUCT_MIS,
            "NRML": self.kite.PRODUCT_NRML,
        }
        kite_product = product_map.get(product.upper(), self.kite.PRODUCT_CNC)

        # Map exchange
        kite_exchange = (
            self.kite.EXCHANGE_NSE if exchange.upper() == "NSE" else self.kite.EXCHANGE_BSE
        )

        # Build order params
        order_params = {
            "variety": variety,
            "exchange": kite_exchange,
            "tradingsymbol": symbol,
            "transaction_type": kite_txn,
            "quantity": quantity,
            "product": kite_product,
            "order_type": kite_order_type,
            "validity": validity,
            "tag": tag,
        }

        if price and order_type.upper() in ("LIMIT", "SL"):
            order_params["price"] = price

        if trigger_price and order_type.upper() in ("SL", "SL-M"):
            order_params["trigger_price"] = trigger_price

        # Bracket order params
        if variety == self.kite.VARIETY_BO:
            order_params["squareoff"] = abs(target - price) if target and price else 0
            order_params["stoploss"] = abs(price - stoploss) if stoploss and price else 0

        try:
            logger.info(
                f"[ZERODHA] Placing order: {transaction_type} {quantity}x {symbol} "
                f"@ {order_type} {price or 'market'} | Product={product}"
            )
            order_id = self.kite.place_order(**order_params)
            logger.info(f"[ZERODHA] Order placed successfully. ID: {order_id}")
            return {
                "status": "success",
                "order_id": order_id,
                "symbol": symbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "price": price,
                "order_type": order_type,
            }
        except Exception as e:
            logger.error(f"[ZERODHA] Order failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "symbol": symbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
            }

    def place_bracket_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        price: float,
        stoploss: float,
        target: float,
        exchange: str = "NSE",
    ) -> Dict[str, Any]:
        """
        Place a bracket order (entry + SL + target).
        Automatically calculates SL and target offsets from entry price.
        """
        self._ensure_auth()

        symbol = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
        kite_exchange = (
            self.kite.EXCHANGE_NSE
            if exchange.upper() == "NSE"
            else self.kite.EXCHANGE_BSE
        )
        kite_txn = (
            self.kite.TRANSACTION_TYPE_BUY
            if transaction_type.upper() == "BUY"
            else self.kite.TRANSACTION_TYPE_SELL
        )

        sl_offset = round(abs(price - stoploss), 1)
        target_offset = round(abs(target - price), 1)

        try:
            logger.info(
                f"[ZERODHA] Bracket order: {transaction_type} {quantity}x {symbol} "
                f"@ ₹{price} | SL=₹{stoploss} (offset={sl_offset}) | "
                f"Target=₹{target} (offset={target_offset})"
            )
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_BO,
                exchange=kite_exchange,
                tradingsymbol=symbol,
                transaction_type=kite_txn,
                quantity=quantity,
                price=price,
                order_type=self.kite.ORDER_TYPE_LIMIT,
                product=self.kite.PRODUCT_MIS,
                stoploss=sl_offset,
                squareoff=target_offset,
                validity="DAY",
                tag="agentic_bracket",
            )
            logger.info(f"[ZERODHA] Bracket order placed. ID: {order_id}")
            return {"status": "success", "order_id": order_id, "type": "bracket"}
        except Exception as e:
            logger.error(f"[ZERODHA] Bracket order failed: {e}")
            return {"status": "error", "error": str(e)}

    def modify_order(self, order_id: str, **kwargs) -> Dict[str, Any]:
        """Modify an existing order."""
        self._ensure_auth()
        try:
            variety = kwargs.pop("variety", self.kite.VARIETY_REGULAR)
            self.kite.modify_order(variety=variety, order_id=order_id, **kwargs)
            logger.info(f"[ZERODHA] Order {order_id} modified")
            return {"status": "success", "order_id": order_id}
        except Exception as e:
            logger.error(f"[ZERODHA] Modify failed: {e}")
            return {"status": "error", "error": str(e)}

    def cancel_order(self, order_id: str, variety: str = "regular") -> Dict[str, Any]:
        """Cancel an open order."""
        self._ensure_auth()
        variety_map = {
            "regular": self.kite.VARIETY_REGULAR,
            "bo": self.kite.VARIETY_BO,
            "co": self.kite.VARIETY_CO,
            "amo": self.kite.VARIETY_AMO,
        }
        try:
            self.kite.cancel_order(
                variety=variety_map.get(variety, self.kite.VARIETY_REGULAR),
                order_id=order_id,
            )
            logger.info(f"[ZERODHA] Order {order_id} cancelled")
            return {"status": "success", "order_id": order_id}
        except Exception as e:
            logger.error(f"[ZERODHA] Cancel failed: {e}")
            return {"status": "error", "error": str(e)}

    # ─── Market Data ─────────────────────────────────────────────────────────

    def get_ltp(self, symbols: List[str]) -> Dict[str, float]:
        """Get last traded price for symbols."""
        self._ensure_auth()
        instruments = [f"NSE:{s.upper().replace('.NS', '')}" for s in symbols]
        data = self.kite.ltp(instruments)
        return {
            k.replace("NSE:", ""): v["last_price"]
            for k, v in data.items()
        }

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get full quote for a symbol."""
        self._ensure_auth()
        symbol = symbol.strip().upper().replace(".NS", "")
        data = self.kite.quote(f"NSE:{symbol}")
        return data.get(f"NSE:{symbol}", {})

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _ensure_auth(self):
        """Raise if not authenticated."""
        if not self._is_authenticated:
            raise RuntimeError(
                "Not authenticated. Call login() and authenticate(request_token) first, "
                "or set access token via set_access_token()."
            )

    def calculate_quantity(
        self, symbol: str, amount: float, price: Optional[float] = None
    ) -> int:
        """
        Calculate how many shares to buy given a rupee amount.
        If price not provided, fetches LTP.
        """
        if not price:
            ltp = self.get_ltp([symbol])
            price = ltp.get(symbol, 0)
        if price <= 0:
            return 0
        return int(amount // price)

    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific order."""
        self._ensure_auth()
        orders = self.kite.orders()
        for order in orders:
            if order.get("order_id") == order_id:
                return order
        return None
