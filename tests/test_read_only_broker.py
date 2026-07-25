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
