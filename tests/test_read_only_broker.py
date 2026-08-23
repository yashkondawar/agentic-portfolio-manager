from zerodha import read_only


class FakeClient:
    def __init__(self, api_key=None, api_secret=None, **_kwargs):
        self.api_key = api_key or "api-key"
        self.api_secret = api_secret or "api-secret"
        self.is_authenticated = True
        self.login_url = "https://example.test/login"

    def get_holdings(self):
        return [
            {
                "tradingsymbol": "TCS",
                "quantity": 2,
                "average_price": 100,
                "last_price": 110,
            }
        ]

    def get_positions(self):
        return {
            "net": [
                {
                    "tradingsymbol": "INFY",
                    "quantity": 3,
                    "average_price": 200,
                    "last_price": 210,
                }
            ]
        }


def test_read_only_facade_has_no_order_api(monkeypatch):
    monkeypatch.setattr(read_only, "ZerodhaClient", FakeClient)
    broker = read_only.ReadOnlyZerodha()

    assert not hasattr(broker, "place_order")
    assert broker.holdings_for_strategy() == [
        {"symbol": "TCS", "quantity": 2, "buy_price": 100, "last_price": 110}
    ]
    assert broker.positions_for_strategy()[0]["symbol"] == "INFY"


def test_browser_auth_stays_behind_read_only_facade(monkeypatch):
    monkeypatch.setattr(read_only, "ZerodhaClient", FakeClient)
    broker = read_only.ReadOnlyZerodha()
    authenticated_client = FakeClient()
    calls = {}

    def fake_auth_flow(**kwargs):
        calls.update(kwargs)
        return authenticated_client

    import zerodha.auth_server

    monkeypatch.setattr(zerodha.auth_server, "run_auth_flow", fake_auth_flow)

    assert broker.authenticate_in_browser(timeout=30) is True
    assert calls["timeout"] == 30
    assert not hasattr(broker, "place_order")


class DeliveryOnlyClient(FakeClient):
    """A cash-segment account: stock is settled, so Kite reports no positions."""

    def get_holdings(self):
        return [
            {
                "tradingsymbol": "TCS",
                "quantity": 2,
                "t1_quantity": 0,
                "average_price": 100,
                "last_price": 110,
            },
            # Bought in the previous session: not settled yet, so the whole
            # quantity sits in t1_quantity.
            {
                "tradingsymbol": "WIPRO",
                "quantity": 0,
                "t1_quantity": 5,
                "average_price": 400,
                "last_price": 420,
            },
        ]

    def get_positions(self):
        return {"net": [], "day": []}


def test_swing_positions_use_the_delivery_book(monkeypatch):
    """Regression: the Swing Desk showed nothing for a delivery-only account.

    It read Kite's intraday ``positions`` book, which is empty once stock has
    settled, while the Portfolio page read ``holdings`` and worked. Swing trades
    are delivery trades, so they must come from the holdings book.
    """
    monkeypatch.setattr(read_only, "ZerodhaClient", DeliveryOnlyClient)
    broker = read_only.ReadOnlyZerodha()

    assert broker.positions_for_strategy() == []  # the old, empty source
    rows = {row["symbol"]: row for row in broker.swing_positions()}
    assert set(rows) == {"TCS", "WIPRO"}
    assert rows["TCS"]["quantity"] == 2
    assert rows["TCS"]["buy_price"] == 100
    # T+1 stock is still an open position and must not be dropped.
    assert rows["WIPRO"]["quantity"] == 5


def test_holdings_for_strategy_counts_unsettled_stock(monkeypatch):
    monkeypatch.setattr(read_only, "ZerodhaClient", DeliveryOnlyClient)
    broker = read_only.ReadOnlyZerodha()

    rows = {row["symbol"]: row["quantity"] for row in broker.holdings_for_strategy()}
    assert rows == {"TCS": 2, "WIPRO": 5}


class MixedBookClient(FakeClient):
    """Settled stock, a same-day CNC top-up, plus intraday and F&O noise."""

    def get_holdings(self):
        return [
            {
                "tradingsymbol": "TCS",
                "quantity": 10,
                "average_price": 100,
                "last_price": 130,
            }
        ]

    def get_positions(self):
        return {
            "net": [
                # Today's delivery top-up on a symbol already held.
                {
                    "tradingsymbol": "TCS",
                    "quantity": 10,
                    "average_price": 120,
                    "last_price": 130,
                    "exchange": "NSE",
                    "product": "CNC",
                },
                # Intraday scalp - not a swing trade.
                {
                    "tradingsymbol": "SBIN",
                    "quantity": 50,
                    "average_price": 600,
                    "last_price": 605,
                    "exchange": "NSE",
                    "product": "MIS",
                },
                # Derivatives leg - not a swing equity trade.
                {
                    "tradingsymbol": "NIFTY24JUNFUT",
                    "quantity": 1,
                    "average_price": 23000,
                    "last_price": 23100,
                    "exchange": "NFO",
                    "product": "NRML",
                },
                # A short is not an open long swing position.
                {
                    "tradingsymbol": "ITC",
                    "quantity": -20,
                    "average_price": 450,
                    "last_price": 445,
                    "exchange": "NSE",
                    "product": "CNC",
                },
            ]
        }


def test_swing_positions_merge_same_day_buys_and_exclude_non_swing_legs(monkeypatch):
    monkeypatch.setattr(read_only, "ZerodhaClient", MixedBookClient)
    broker = read_only.ReadOnlyZerodha()

    rows = {row["symbol"]: row for row in broker.swing_positions()}
    assert set(rows) == {"TCS"}, "MIS, F&O and short legs are not swing positions"
    # 10 @ 100 (settled) + 10 @ 120 (today) -> 20 @ cost-weighted 110.
    assert rows["TCS"]["quantity"] == 20
    assert rows["TCS"]["buy_price"] == 110
