from datetime import date

import pandas as pd
import pytest

from backtesting.breakout_ath import daily
from backtesting.breakout_ath.config import AthBreakoutConfig
from backtesting.breakout_ath.engine import PriceBundle
from qtr_results import ledger


def ath_setup(monkeypatch, values, *, start="2026-10-26"):
    closes = pd.DataFrame(
        {"AAA.NS": values}, index=pd.bdate_range(start, periods=len(values))
    )
    monkeypatch.setattr(daily, "load_prices", lambda *a, **k: PriceBundle(closes))
    monkeypatch.setattr(daily, "industry_map", lambda: {})
    monkeypatch.setattr(daily, "_entry_actions", lambda *a: [])
    state = daily.empty_state(1000)
    state.update(cash=0, last_session="2026-10-23")
    state["positions"] = [{
        "symbol": "AAA.NS", "industry": "Test", "entry_date": "2026-10-23",
        "entry_price": 100, "quantity": 10, "anchor": 100,
    }]
    return state


def test_ath_replays_a_missed_stop_even_if_price_recovers(monkeypatch):
    state = ath_setup(monkeypatch, [100, 80, 105])
    result = daily.run_daily(
        portfolio_state=state, as_of=date(2026, 10, 28), download=False, persist=False
    )
    assert result["exits"][0]["exit_date"] == "2026-10-27"
    assert result["state"]["closed"][0]["exit_price"] == 80
    assert result["cash"] == pytest.approx(800 * (1 - AthBreakoutConfig().cost_rate))
    assert len(result["sessions_replayed"]) == 3
    again = daily.run_daily(
        portfolio_state=result["state"], as_of=date(2026, 10, 28),
        download=False, persist=False,
    )
    assert again["sessions_replayed"] == []
    assert again["cash"] == result["cash"]
    assert len(again["state"]["closed"]) == 1


def test_ath_keeps_missed_high_and_does_not_backdate_confirmed_buys(monkeypatch):
    state = ath_setup(monkeypatch, [150, 70, 120])
    state["positions"][0]["entry_date"] = "2026-10-28"
    result = daily.run_daily(
        portfolio_state=state, as_of=date(2026, 10, 28), download=False, persist=False
    )
    assert not result["exits"]
    assert result["state"]["positions"][0]["anchor"] == 120


def test_ath_ratchets_off_intermediate_peak(monkeypatch):
    state = ath_setup(monkeypatch, [150, 140, 135])
    result = daily.run_daily(
        portfolio_state=state, as_of=date(2026, 10, 28), download=False, persist=False
    )
    assert result["state"]["positions"][0]["anchor"] == 150


def test_ath_quarterly_reset_restores_cash_spent_on_later_confirmed_buys(monkeypatch):
    state = ath_setup(monkeypatch, [100, 100, 110], start="2026-10-01")
    state.update(cash=5000, last_session="2026-09-30")
    state["positions"][0]["entry_date"] = "2026-10-05"
    cfg = AthBreakoutConfig()
    result = daily.run_daily(
        portfolio_state=state, as_of=date(2026, 10, 5), download=False, persist=False,
    )
    historical_cash = 5000 + 1000 * (1 + cfg.cost_rate)
    assert result["budget_per_slot"] == pytest.approx(historical_cash / cfg.max_positions)
    assert result["cash"] == 5000


def test_ath_refuses_to_overwrite_a_confirmation_during_download(monkeypatch, tmp_path):
    state = ath_setup(monkeypatch, [100])
    path = tmp_path / "ath.json"
    daily.save_state(path, state)
    original = daily.load_prices

    def changed(*args, **kwargs):
        path.write_text('{"cash":123}', encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(daily, "load_prices", changed)
    with pytest.raises(RuntimeError, match="changed during"):
        daily.run_daily(state_path=path, as_of=date(2026, 10, 26), download=False)
    assert path.read_text() == '{"cash":123}'


def pick():
    return {
        "symbol": "AAA", "entry_price": 100, "entry_date": "2026-10-23",
        "target_price": 200, "trailing_stop_pct": 16, "highest_price": 100,
        "stop_distance_abs": 16, "stop_price": 84, "status": "open",
        "max_holding_days": 90, "last_history_session": "2026-10-23",
    }


def test_quarterly_replays_stops_chronologically_once():
    holding = pick()
    history = pd.DataFrame(
        {"Close": [120, 100, 140]}, index=pd.bdate_range("2026-10-26", periods=3)
    )
    days = [s.date() for s in history.index]
    result = ledger.replay_open_positions(
        [holding], {"AAA": history}, days, since=date(2026, 10, 23)
    )
    assert holding["exit_date"] == "2026-10-27"
    assert holding["exit_price"] == 100
    assert len(result["closed"]) == 1
    assert not ledger.replay_open_positions(
        [holding], {"AAA": history}, days, since=date(2026, 10, 23)
    )["closed"]


def test_quarterly_missing_quote_blocks_cursor_and_does_not_use_future_close():
    holding = pick()
    history = pd.DataFrame({"Close": [150]}, index=pd.to_datetime(["2026-10-27"]))
    result = ledger.replay_open_positions(
        [holding], {"AAA": history}, [date(2026, 10, 26), date(2026, 10, 27)],
        since=date(2026, 10, 23),
    )
    assert result["gaps"] == [{"symbol": "AAA", "date": "2026-10-26"}]
    assert holding["last_history_session"] == "2026-10-23"
    assert holding["highest_price"] == 100


def test_quarterly_history_cannot_close_a_pick_before_its_entry():
    holding = pick()
    holding["entry_date"] = "2026-10-28"
    history = pd.DataFrame(
        {"Close": [70, 75, 110]}, index=pd.bdate_range("2026-10-26", periods=3)
    )
    result = ledger.replay_open_positions(
        [holding], {"AAA": history}, [s.date() for s in history.index],
        since=date(2026, 10, 23),
    )
    assert not result["closed"]
    assert holding["highest_price"] == 110


def test_quarterly_reports_ai_failure_instead_of_completed(monkeypatch):
    from qtr_results import engine
    from strategies.qtr_results import QuarterlyResultsStrategy

    monkeypatch.setattr(engine, "run", lambda p: {
        "report": "partial", "data": {"execution_errors": ["Unsupported model"]},
    })
    result = QuarterlyResultsStrategy().run({})
    assert not result.ok
    assert result.error == "Unsupported model"


def test_related_documents_commit_atomically(monkeypatch, tmp_path):
    import sqlite3
    from core import storage

    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "atomic.sqlite3"))
    storage.set_documents([("test", "ledger", [1]), ("test", "cash", 10)])
    with pytest.raises(sqlite3.IntegrityError):
        storage.set_documents([("test", "ledger", [2]), (None, "cash", 20)])
    assert storage.get_document("test", "ledger") == [1]
    assert storage.get_document("test", "cash") == 10


def test_book_save_refuses_a_concurrent_change(monkeypatch, tmp_path):
    from core import storage

    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "guard.sqlite3"))
    storage.set_document("test", "cash", 10)
    with pytest.raises(RuntimeError, match="changed during"):
        storage.set_documents([("test", "cash", 20)], expected={("test", "cash"): 5})
    assert storage.get_document("test", "cash") == 10


def test_s18_management_only_executes_known_orders_but_creates_no_new_decisions():
    from backtesting.s18.book import Book
    from backtesting.s18.config import S18Config
    from test_s18_book import market

    panel = market(rows=4, stocks=40)
    book = Book.from_cash(S18Config("P15", "none"), "A", 10000)
    book.step(panel, 0, review=False, order=[], initial=True, decisions=False)
    book.queued_buys = [{"gid": 0, "sleeve": "S1", "weight": 1}]
    book.step(panel, 1, review=True, order=panel.buy_order[1], decisions=False)
    assert len(book.positions) == 1
    assert book.positions[0].gid == 0
    assert not book.queued_buys
    book.step(panel, 2, review=False, order=panel.buy_order[2], decisions=True)
    assert book.queued_buys


def test_quarterly_recovery_uses_raw_nse_quotes_and_exchange_sessions(monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace
    from backtesting.s18 import nse_sources
    from qtr_results import engine

    monkeypatch.setattr(engine, "datetime", SimpleNamespace(
        now=lambda tz: datetime(2026, 10, 28, 19, tzinfo=tz)
    ))
    days = ["2026-10-26", "2026-10-27", "2026-10-28"]
    source = SimpleNamespace(
        calendar=lambda *a: SimpleNamespace(records=[
            {"date": day, "is_session": True} for day in days
        ]),
        bhavcopy=lambda d: SimpleNamespace(records=[{
            "symbol": "AAA", "close": {"2026-10-26": 120, "2026-10-27": 100,
                                      "2026-10-28": 140}[str(d)],
        }]),
    )
    monkeypatch.setattr(nse_sources, "NseSources", lambda: source)
    holding = pick()
    result = engine._recover_holdings([holding], date(2026, 10, 23), date(2026, 10, 28))
    assert not result["gaps"]
    assert holding["exit_date"] == "2026-10-27"
    assert holding["exit_price"] == 100


@pytest.mark.parametrize("failed", [False, True])
def test_quarterly_stages_unprocessed_declarers_and_keeps_failed_scan_cursor(
    monkeypatch, tmp_path, failed,
):
    from datetime import timedelta
    from core import storage
    from qtr_results import engine
    from scraper import nse_events

    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "inbox.sqlite3"))
    previous = (date.today() - timedelta(days=9)).isoformat()
    storage.set_document("qtr_results", "recovery", {"last_discovery_date": previous})
    monkeypatch.setattr(engine.ledger_mod, "load_ledger", lambda: [])
    monkeypatch.setattr(engine.memory_mod, "load_memory", lambda: {})
    monkeypatch.setattr(
        engine.portfolio_mod, "load_portfolio",
        lambda capital: engine.portfolio_mod.Portfolio(1000, 1000),
    )
    declarer = {
        "symbol": "AAA", "result_date": previous, "company": "Test",
        "sources": ["nse_filings"], "seen_keys": ["calendar:AAA"],
    }

    def discover(**kwargs):
        if failed:
            kwargs["errors"].append("Discovery LLM failed")
        return [declarer]

    def interrupt(symbol):
        raise RuntimeError("interrupted before analysis")

    monkeypatch.setattr(engine, "discover_result_declarers", discover)
    monkeypatch.setattr(engine, "_prioritize_declarers", lambda rows: rows)
    monkeypatch.setattr(engine, "analyze_symbol", interrupt)
    monkeypatch.setattr(nse_events, "_load_seen", lambda path: {})
    with pytest.raises(RuntimeError, match="interrupted before analysis"):
        engine.run({"upcoming_days": 0}, price_fn=lambda symbol: 100)
    assert storage.get_document("qtr_results", "pending_declarers") == [declarer]
    assert "calendar:AAA" in storage.get_document(
        "nse_events_seen", engine.config.NSE_SEEN_PATH.stem,
    )["keys"]
    recovery = storage.get_document("qtr_results", "recovery")
    assert recovery["last_discovery_date"] == (previous if failed else date.today().isoformat())


def test_nse_discovery_failure_is_explicit_but_does_not_lose_other_feed(monkeypatch):
    from qtr_results import discovery

    def failed_calendar(**kwargs):
        raise RuntimeError("NSE unavailable")

    monkeypatch.setattr(discovery, "new_declared_from_calendar", failed_calendar)
    monkeypatch.setattr(discovery, "new_declared_results", lambda **kwargs: [{
        "symbol": "AAA", "result_date": date.today().isoformat(), "seen_key": "filing:AAA",
    }])
    errors = []
    sources = {}
    rows = discovery.discover_result_declarers(
        use_llm=False, commit_seen=False, errors=errors, source_status=sources,
    )
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["seen_keys"] == ["filing:AAA"]
    assert errors == ["NSE event-calendar discovery failed: NSE unavailable"]
    assert sources == {"nse_calendar": False, "nse_filings": True}


def test_quarterly_does_not_overwrite_cash_changed_while_loading_the_book(monkeypatch, tmp_path):
    from core import storage
    from qtr_results import engine

    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "load-race.sqlite3"))
    original = engine.portfolio_mod.Portfolio(1000, 1000)
    changed = engine.portfolio_mod.Portfolio(1000, 500)
    storage.set_documents([
        ("qtr_results", "ledger", []),
        ("qtr_results", "memory", {"updated_at": date.today().isoformat()}),
        ("qtr_results", "portfolio", original.to_dict()),
    ])
    monkeypatch.setattr(engine.ledger_mod, "load_ledger", lambda: [])
    monkeypatch.setattr(
        engine.memory_mod, "load_memory", lambda: {"updated_at": date.today().isoformat()},
    )

    def load_and_edit(capital):
        storage.set_document("qtr_results", "portfolio", changed.to_dict())
        return original

    monkeypatch.setattr(engine.portfolio_mod, "load_portfolio", load_and_edit)
    with pytest.raises(RuntimeError, match="changed during"):
        engine.run(price_fn=lambda symbol: 100)
    assert storage.get_document("qtr_results", "portfolio") == changed.to_dict()


@pytest.fixture
def quarterly_book(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from core import storage
    from qtr_results import engine

    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "quarterly.sqlite3"))
    storage.set_documents([
        ("qtr_results", "ledger", []),
        ("qtr_results", "portfolio", engine.portfolio_mod.Portfolio(10000, 10000).to_dict()),
        ("qtr_results", "memory", engine.memory_mod._empty_memory()),
    ])
    monkeypatch.setattr(engine, "_recover_holdings", lambda *a: {
        "closed": [], "sessions_replayed": [], "gaps": [],
    })
    monkeypatch.setattr(engine, "_prioritize_declarers", lambda rows: rows)
    monkeypatch.setattr(engine, "_default_price_fn", lambda symbol: 100)
    monkeypatch.setattr(engine, "_entry_filter_reason", lambda *a, **k: "")
    monkeypatch.setattr(
        engine.technicals_mod, "get_technicals", lambda symbol: SimpleNamespace(atr=2),
    )
    monkeypatch.setattr(engine, "_render_report", lambda **kwargs: "Portfolio report")
    return engine


def test_optional_ai_discovery_failure_completes_with_visible_warnings(quarterly_book, monkeypatch):
    from core import storage
    from strategies.qtr_results import QuarterlyResultsStrategy

    engine = quarterly_book
    previous = "2026-10-23"
    storage.set_document("qtr_results", "recovery", {"last_discovery_date": previous})

    def discover(**kwargs):
        kwargs["errors"].append("Discovery LLM failed: HTTP 503")
        kwargs["source_status"].update(nse_calendar=True, web_search=False)
        return []

    monkeypatch.setattr(engine, "discover_result_declarers", discover)
    result = QuarterlyResultsStrategy().run({"upcoming_days": 0})
    assert result.ok
    assert result.status == "completed_with_warnings"
    assert result.data["execution_warnings"] == ["Discovery LLM failed: HTTP 503"]
    assert not result.data["execution_errors"]
    assert "Completed with warnings" in result.report
    assert storage.get_document("qtr_results", "recovery")["last_discovery_date"] == previous


def test_all_discovery_sources_down_without_pending_work_is_a_failure(quarterly_book, monkeypatch):
    from strategies.qtr_results import QuarterlyResultsStrategy

    def discover(**kwargs):
        kwargs["errors"].append("All discovery sources unavailable")
        kwargs["source_status"].update(nse_calendar=False, nse_filings=False, web_search=False)
        return []

    monkeypatch.setattr(quarterly_book, "discover_result_declarers", discover)
    result = QuarterlyResultsStrategy().run({"upcoming_days": 0})
    assert result.status == "failed"
    assert result.error == "All discovery sources unavailable"


def test_failed_conviction_defers_candidate_but_saves_holdings_management(quarterly_book, monkeypatch):
    from core import storage
    from qtr_results.analysis import AnalysisResult
    from qtr_results.conviction import ConvictionVerdict
    from strategies.qtr_results import QuarterlyResultsStrategy

    engine = quarterly_book
    holding = pick()
    holding.update(
        symbol="HELD", entry_date=date.today().isoformat(),
        quantity=10, invested=1000, target_pct=100,
    )
    storage.set_document("qtr_results", "ledger", [holding])
    pf = engine.portfolio_mod.Portfolio(10000, 9000)
    storage.set_document("qtr_results", "portfolio", pf.to_dict())
    declarer = {"symbol": "TEST", "result_date": date.today().isoformat()}
    monkeypatch.setattr(engine, "discover_result_declarers", lambda **kwargs: [declarer])
    monkeypatch.setattr(engine, "_default_price_fn", lambda symbol: 70)
    monkeypatch.setattr(engine, "analyze_symbol", lambda symbol: AnalysisResult(
        symbol=symbol, current_price=100, is_strong=True, strength_score=90,
    ))
    monkeypatch.setattr(
        engine, "evaluate_conviction", lambda *a, **k: ConvictionVerdict(error="network down"),
    )
    result = QuarterlyResultsStrategy().run({"upcoming_days": 0})
    assert result.status == "completed_with_warnings"
    assert result.data["num_new_picks"] == 0
    assert result.data["num_closed"] == 1
    assert result.data["num_conviction_deferred"] == 1
    assert result.data["analysed"][0]["status"] == "llm_error"
    assert storage.get_document("qtr_results", "pending_declarers") == [declarer]
    saved = storage.get_document("qtr_results", "ledger")
    assert len(saved) == 1 and saved[0]["status"] == "exited"
    engine.portfolio_mod.apply_close(pf, 70, 10)
    assert storage.get_document("qtr_results", "portfolio")["cash"] == pf.cash


def test_candidates_beyond_conviction_limit_cannot_buy(quarterly_book, monkeypatch):
    from core import storage
    from qtr_results.analysis import AnalysisResult
    from qtr_results.conviction import ConvictionVerdict
    from strategies.qtr_results import QuarterlyResultsStrategy

    engine = quarterly_book
    declarers = [
        {"symbol": symbol, "result_date": date.today().isoformat()}
        for symbol in ("AAA", "BBB")
    ]
    monkeypatch.setattr(engine.config, "MAX_CONVICTION_EVALS", 1)
    monkeypatch.setattr(engine, "discover_result_declarers", lambda **kwargs: declarers)
    monkeypatch.setattr(engine, "analyze_symbol", lambda symbol: AnalysisResult(
        symbol=symbol, current_price=100, is_strong=True, strength_score=90,
    ))
    checked = []

    def conviction(candidate, *args, **kwargs):
        checked.append(candidate["symbol"])
        return ConvictionVerdict(conviction=0.9, verdict="buy")

    monkeypatch.setattr(engine, "evaluate_conviction", conviction)
    result = QuarterlyResultsStrategy().run({"upcoming_days": 0})
    assert result.status == "completed_with_warnings"
    assert checked == ["AAA"]
    assert result.data["num_new_picks"] == 1
    assert result.data["new_picks"][0]["symbol"] == "AAA"
    assert result.data["analysed"][1]["status"] == "deferred_llm"
    assert storage.get_document("qtr_results", "pending_declarers") == [declarers[1]]


def test_historical_gap_remains_a_failure_even_if_ai_is_healthy(quarterly_book, monkeypatch):
    from strategies.qtr_results import QuarterlyResultsStrategy

    engine = quarterly_book
    monkeypatch.setattr(engine, "_recover_holdings", lambda *a: {
        "closed": [], "sessions_replayed": [],
        "gaps": [{"symbol": "HELD", "date": "2026-10-26"}],
    })
    monkeypatch.setattr(engine, "discover_result_declarers", lambda **kwargs: [])
    result = QuarterlyResultsStrategy().run({"upcoming_days": 0})
    assert result.status == "failed"
    assert "Missing historical close" in result.error
