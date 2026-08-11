from datetime import date
from pathlib import Path
from types import SimpleNamespace

from backtesting.swing_trading.config import BacktestConfig
from backtesting.swing_trading.portfolio import ClosedTrade
from backtesting.swing_trading.watchlist import UniverseStock
from backtesting.swing_trading import service
from core.storage import get_artifact


class FakeData:
    def __init__(self, _cache_dir):
        self.frames = {}

    def load_or_download(self, **_kwargs):
        self.frames = {"TCS": object()}


class FakeEngine:
    def __init__(self, _cfg, _data, universe):
        assert [item.symbol for item in universe] == ["TCS"]
        trade = ClosedTrade(
            symbol="TCS",
            quantity=2,
            entry_price=100,
            exit_price=110,
            entry_date=date(2026, 1, 2),
            exit_date=date(2026, 1, 12),
            pnl=20,
            pnl_pct=10,
            exit_reason="target",
            holding_days=10,
            setup="Momentum",
        )
        self.pf = SimpleNamespace(closed=[trade], positions={})
        self.daily_log = [
            {
                "date": "2026-01-02",
                "equity": 1000,
                "cash": 800,
                "deployed": 200,
                "open_positions": 1,
                "watchlist_size": 1,
            },
            {
                "date": "2026-01-12",
                "equity": 1020,
                "cash": 1020,
                "deployed": 0,
                "open_positions": 0,
                "watchlist_size": 1,
            },
        ]
        self.watchlist_log = [{"date": "2026-01-02", "symbols": ["TCS"]}]

    def run(self, _start, _end):
        return None


class ExitingEngine(FakeEngine):
    def run(self, _start, _end):
        raise SystemExit("No trading days in range")


def test_backtest_service_returns_structured_artifacts(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "portfolio.sqlite3"))
    monkeypatch.setattr(service, "PointInTimeData", FakeData)
    monkeypatch.setattr(service, "BacktestEngine", FakeEngine)
    monkeypatch.setattr(
        service, "load_universe", lambda _cfg: [UniverseStock(symbol="IGNORED")]
    )
    cfg = BacktestConfig(
        starting_capital=1000,
        goal_return_pct=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    result = service.run_backtest(cfg, symbols=["tcs.ns"], tag="test")

    assert result["metrics"]["total_return_pct"] == 2.0
    assert result["metrics"]["goal_reached"] is True
    assert result["trades"][0]["entry_date"] == "2026-01-02"
    trades_ref = result["artifacts"]["trades.csv"]
    group_id = trades_ref.split("/")[3]
    assert get_artifact(group_id, "trades.csv").text.startswith("symbol,setup")
    assert get_artifact(group_id, "equity_curve.csv") is not None


def test_backtest_service_translates_engine_exit(monkeypatch):
    monkeypatch.setattr(service, "PointInTimeData", FakeData)
    monkeypatch.setattr(service, "BacktestEngine", ExitingEngine)
    cfg = BacktestConfig(
        start_date=date(2026, 1, 3),
        end_date=date(2026, 1, 4),
    )

    try:
        service.run_backtest(cfg, symbols=["TCS"], write_outputs=False)
    except RuntimeError as exc:
        assert "No trading days" in str(exc)
    else:
        raise AssertionError("SystemExit should be translated to RuntimeError")


def test_default_artifact_directories_are_unique(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "portfolio.sqlite3"))
    monkeypatch.setattr(service, "PointInTimeData", FakeData)
    monkeypatch.setattr(service, "BacktestEngine", FakeEngine)
    cfg = BacktestConfig(
        starting_capital=1000,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    first = service.run_backtest(cfg, symbols=["TCS"])
    second = service.run_backtest(cfg, symbols=["TCS"])

    assert first["artifacts"]["summary.txt"] != second["artifacts"]["summary.txt"]
