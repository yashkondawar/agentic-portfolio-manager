from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core import storage
from core.run_history import save_run
from core.strategy import StrategyResult
from backtesting.s18 import portfolio, service
from test_s18_service import daily_setup  # noqa: F401


def _saved_run(book_id, output, **params):
    return save_run(
        StrategyResult("s18_daily", "completed", data=output),
        {"book_id": book_id, "combo": "P5", "metal_mode": "none", **params},
        duration_ms=1,
    )


@pytest.mark.parametrize("path_setting", ["PORTFOLIO_DB_PATH", "TRADER_WORKBENCH_DB"])
def test_workbench_reuses_existing_storage_without_changing_saved_data(
    daily_setup, tmp_path, monkeypatch, path_setting
):
    from backtesting.breakout_ath import config as ath_config
    from backtesting.breakout_ath.daily import empty_state, save_state
    from core.bars import write_bars
    from core.schedules import Schedule, save_schedule
    from gfs.state import Book, save_book
    from ui.overview_data import load_books

    database = storage.database_path()
    monkeypatch.delenv("PORTFOLIO_DB_PATH")
    monkeypatch.setenv(path_setting, str(database))
    monkeypatch.setattr("core.scheduler.ensure_running", lambda: False)
    ath_path = tmp_path / "existing_ath.json"
    monkeypatch.setattr(ath_config, "STATE_PATH", ath_path)
    ath = empty_state(20000)
    ath.update(cash=19000, last_session="2025-01-02", opened_on="2025-01-01")
    save_state(ath_path, ath)
    ath_before = ath_path.read_bytes()

    book = Book()
    book.open_with(1000, date(2025, 1, 1))
    book.cash = 945.23
    book.last_session = date(2025, 1, 2)
    save_book(book)
    storage.set_document(
        "qtr_results",
        "portfolio",
        {"starting_capital": 2000, "cash": 2123.45, "realized_pnl": 123.45},
    )
    storage.set_document("qtr_results", "ledger", [])
    output = service.run_daily(
        as_of=str(daily_setup.dates[1]),
        book_id="existing",
        combo="P5",
        metal_mode="none",
    )
    _saved_run("existing", output)
    defaults = {
        "book_id": "existing",
        "combo": "P5",
        "metal_mode": "none",
        "capital": 100000,
    }
    storage.set_document("strategy_defaults", "s18_daily", defaults)
    storage.set_document("watchlists", "default", ["TCS", "INFY"])
    save_schedule(
        Schedule(
            id="existing-schedule",
            name="Existing daily update",
            strategy_id="s18_daily",
            run_at="18:00",
            params=defaults,
        )
    )
    today = date.today()
    write_bars(
        "^NSEI",
        pd.DataFrame(
            {
                "Open": [100],
                "High": [102],
                "Low": [99],
                "Close": [101],
                "Volume": [1000],
            },
            index=pd.to_datetime([today]),
        ),
        today,
        today,
    )

    def saved_data():
        with storage.connection_scope() as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT IN ('application_logs', 'sqlite_sequence')"
                )
            ]
            return {
                table: sorted(
                    (
                        tuple(row)
                        for row in connection.execute(f'SELECT * FROM "{table}"')
                    ),
                    key=repr,
                )
                for table in tables
            }

    before = saved_data()
    with (
        patch("core.registry.run_strategy") as execute,
        patch("yfinance.download", side_effect=AssertionError("Unexpected network")),
        patch("dotenv.load_dotenv", return_value=False),
    ):
        books = load_books()
        assert all(book.exists and not book.error for book in books)
        assert [book.value for book in books[:3]] == [945.23, 19000, 2123.45]
        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py")
        ).run(timeout=30)
        assert not app.exception
        app.radio(key="_section_tab").set_value("Invest").run(timeout=30)
        assert not app.exception
        app.button(key="open_book_book:existing:P5:none").click().run(timeout=30)
        assert not app.exception
        assert app.number_input(key="discover_s18_capital").value == 100000
        app.radio(key="_section_tab").set_value("Manage").run(timeout=30)
        assert not app.exception
        app.sidebar.radio(key="_page_tab").set_value("history").run(timeout=30)
        assert not app.exception
        execute.assert_not_called()
    assert storage.database_path() == database
    assert saved_data() == before
    assert ath_path.read_bytes() == ath_before


def test_snapshot_uses_saved_portfolio_not_preview_or_network(daily_setup):
    m = daily_setup
    first = service.run_daily(as_of=str(m.dates[0]), combo="P5", metal_mode="none")
    service.run_daily(as_of=str(m.dates[1]), combo="P5", metal_mode="none")
    m.close[2] *= 1.2
    preview = service.run_daily(
        as_of=str(m.dates[2]),
        combo="P5",
        metal_mode="none",
        persist=False,
    )
    _saved_run("default", preview)
    with (
        patch(
            "backtesting.s18.data.load_market",
            side_effect=AssertionError("Price reload"),
        ),
        patch(
            "backtesting.s18.live_data.collect_market",
            side_effect=AssertionError("Network"),
        ),
    ):
        snap = portfolio.ledger_snapshot(combo="P5", metal_mode="none")
    assert snap["as_of"] == str(m.dates[1])
    assert snap["book"]["equity"] == pytest.approx(99980)
    assert snap["book"]["open_positions"] == 10
    assert snap["book"]["total_pnl"] == pytest.approx(-20)
    assert snap["book"]["unrealized_pnl"] == pytest.approx(-20)
    assert snap["book"]["realized_pnl"] == 0
    assert snap["book"]["tax_paid"] == 0
    assert snap["opened_on"] == first["as_of"]
    assert preview["metrics"]["final_value"] > snap["book"]["equity"]
    assert all(h["average_cost"] > 100 for h in snap["holdings"])


def test_latest_run_is_scoped_to_selected_portfolio(daily_setup):
    first = service.run_daily(
        as_of="2025-01-01",
        book_id="first",
        combo="P5",
        metal_mode="none",
    )
    second = service.run_daily(
        as_of="2025-01-01",
        book_id="second",
        combo="P5",
        metal_mode="none",
        capital=200000,
    )
    first_id = _saved_run("first", first)
    _saved_run("second", second)
    assert (
        portfolio.latest_portfolio_run(book_id="first", combo="P5", metal_mode="none")[
            "id"
        ]
        == first_id
    )
    failure_id = save_run(
        StrategyResult("s18_daily", "failed", error="Input unavailable"),
        {"book_id": "first", "combo": "P5", "metal_mode": "none"},
        duration_ms=1,
    )
    assert (
        portfolio.latest_portfolio_run(book_id="first", combo="P5", metal_mode="none")[
            "id"
        ]
        == failure_id
    )
    assert (
        portfolio.ledger_snapshot(book_id="first", combo="P5", metal_mode="none")[
            "book"
        ]["equity"]
        == 100000
    )
    assert portfolio.latest_portfolio_run(book_id="unused") is None


def test_missing_committed_artifact_is_explicit(daily_setup):
    output = service.run_daily(as_of="2025-01-01", combo="P5", metal_mode="none")
    with storage.connection_scope() as connection:
        connection.execute(
            "DELETE FROM artifacts WHERE group_id=? AND name='holdings.csv'",
            (output["artifact_group_id"],),
        )
    with pytest.raises(ValueError, match="missing holdings"):
        portfolio.ledger_snapshot(combo="P5", metal_mode="none")


def test_page_updates_saved_snapshot_above_latest_run_on_same_submission(daily_setup):
    m = daily_setup
    defaults = {
        "book_id": "layout",
        "combo": "P5",
        "metal_mode": "none",
        "capital": 100000.0,
        "persist": True,
        "as_of": str(m.dates[0]),
    }
    storage.set_document("strategy_defaults", "s18_daily", defaults)
    service.run_daily(**defaults)
    app = AppTest.from_string(
        "from ui.state import initialize_state\n"
        "from ui.pages import _s18_portfolio_desk\n"
        "initialize_state()\n"
        "_s18_portfolio_desk()\n"
    ).run(timeout=120)
    assert not app.exception
    assert next(v for v in app.metric if v.label == "Portfolio value").value.endswith(
        "100,000"
    )
    assert [v.value for v in app.subheader] == ["Run S18 Daily", "Latest run"]
    assert any(v.value == "### S18 portfolio" for v in app.markdown)
    assert any(
        v.value == "### S18 portfolio" for v in app.main.children[0].get("markdown")
    )
    app.date_input(key="discover_s18_as_of").set_value(pd.Timestamp(m.dates[1]).date())
    next(b for b in app.button if b.label == "Run S18 Daily").click().run(timeout=120)
    assert not app.exception
    assert next(v for v in app.metric if v.label == "Portfolio value").value.endswith(
        "99,980"
    )
    assert next(v for v in app.metric if v.label == "Positions (A + B)").value == "10"
    assert any("Portfolio updated" in s.value for s in app.success)
    assert any(
        "2025-01-02" in c.value and "Saved through" in c.value for c in app.caption
    )
    assert not any(v.value == "#### Daily data ingestion" for v in app.markdown)
    assert not any(v.value == "#### Golden validation evidence" for v in app.markdown)

    m.close[2] *= 1.2
    app.date_input(key="discover_s18_as_of").set_value(date(2025, 1, 3))
    app.checkbox(key="discover_s18_persist").uncheck()
    next(b for b in app.button if b.label == "Run S18 Daily").click().run(timeout=120)
    assert not app.exception
    assert next(v for v in app.metric if v.label == "Portfolio value").value.endswith(
        "99,980"
    )
    assert any("Preview only" in s.value for s in app.info)
    assert (
        portfolio.ledger_snapshot(book_id="layout", combo="P5", metal_mode="none")[
            "as_of"
        ]
        == "2025-01-02"
    )
    app.date_input(key="discover_s18_as_of").set_value(date(2025, 1, 1))
    app.checkbox(key="discover_s18_persist").check()
    next(b for b in app.button if b.label == "Run S18 Daily").click().run(timeout=120)
    assert not app.exception
    assert any("backwards" in e.value for e in app.error)
    assert next(v for v in app.metric if v.label == "Portfolio value").value.endswith(
        "99,980"
    )


def test_empty_portfolio_does_not_replay_old_run_into_saved_state(daily_setup):
    preview = service.run_daily(
        as_of="2025-01-01",
        combo="P5",
        metal_mode="none",
        persist=False,
    )
    _saved_run("default", preview)
    assert not portfolio.ledger_snapshot(combo="P5", metal_mode="none")["exists"]
    assert portfolio.latest_portfolio_run(combo="P5", metal_mode="none") is not None


def test_saved_refresh_picks_up_scheduled_run_without_running_strategy(daily_setup):
    m = daily_setup
    defaults = {
        "book_id": "scheduled",
        "combo": "P5",
        "metal_mode": "none",
        "capital": 100000.0,
        "persist": True,
        "as_of": str(m.dates[0]),
    }
    storage.set_document("strategy_defaults", "s18_daily", defaults)
    first = service.run_daily(**defaults)
    _saved_run("scheduled", first)
    app = AppTest.from_string(
        "from ui.state import initialize_state\n"
        "from ui.pages import _s18_portfolio_desk\n"
        "initialize_state()\n"
        "_s18_portfolio_desk()\n"
    ).run(timeout=120)
    assert not app.exception
    assert any(
        "2025-01-01" in c.value and "Saved through" in c.value for c in app.caption
    )
    assert any("every 30 seconds" in c.value for c in app.caption)
    app.session_state["latest_results"] = {
        "s18_daily": StrategyResult("s18_daily", "completed", data=first).to_dict()
    }
    updated = service.run_daily(**{**defaults, "as_of": str(m.dates[1])})
    latest_id = _saved_run("scheduled", updated)
    original = storage.get_document("s18", "book:scheduled:P5:none")
    with (
        patch("ui.pages.run_strategy", side_effect=AssertionError("Ran strategy")),
        patch(
            "backtesting.s18.live_data.collect_market",
            side_effect=AssertionError("Fetched prices"),
        ),
    ):
        app.button(key="discover_s18_refresh").click().run(timeout=120)
        assert not app.exception
        assert any(
            "2025-01-02" in c.value and "Saved through" in c.value for c in app.caption
        )
        assert any("2025-01-02" in s.value for s in app.success)
        app.run(timeout=120)
        assert not app.exception
    assert storage.get_document("s18", "book:scheduled:P5:none") == original
    assert (
        portfolio.latest_portfolio_run(
            book_id="scheduled", combo="P5", metal_mode="none"
        )["id"]
        == latest_id
    )
    assert (
        app.date_input(key="discover_s18_as_of").value
        == pd.Timestamp(m.dates[0]).date()
    )


def test_risk_off_report_is_visible_without_opening_an_expander(daily_setup):
    m = daily_setup
    m.risk_off[:] = True
    output = service.run_daily(
        as_of=str(m.dates[0]), combo="P5", metal_mode="none", persist=False
    )
    run_id = save_run(
        StrategyResult("s18_daily", "completed", report=output["report"], data=output),
        {"book_id": "default", "combo": "P5", "metal_mode": "none"},
        duration_ms=1,
    )
    app = AppTest.from_string(
        "from core.run_history import get_run\n"
        "from ui.components import render_result, result_from_record\n"
        f"render_result(result_from_record(get_run('{run_id}')))\n"
    ).run(timeout=120)
    assert not app.exception
    assert any("SMA100 overlay: **risk-off**" in v.value for v in app.markdown)
    assert not any(v.label == "Full report" for v in app.expander)
    assert any("not a buy-the-dip strategy" in c.value for c in app.caption)
    assert any("five-session startup" in c.value for c in app.caption)


def test_workbench_links_preserve_capital_when_switching_s18_books(daily_setup):
    for book_id, capital in (("small", 250000.0), ("large", 500000.0)):
        service.run_daily(
            as_of="2025-01-01",
            book_id=book_id,
            combo="P5",
            metal_mode="none",
            capital=capital,
        )
    with patch("core.scheduler.ensure_running"):
        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py")
        ).run(timeout=30)
        app.radio(key="_section_tab").set_value("Invest").run(timeout=30)
        for book_id, capital in (("small", 250000.0), ("large", 500000.0)):
            app.button(key=f"open_book_book:{book_id}:P5:none").click().run(timeout=30)
            assert not app.exception
            assert app.text_input(key="discover_s18_book_id").value == book_id
            assert app.selectbox(key="discover_s18_combo").value == "P5"
            assert app.selectbox(key="discover_s18_metal_mode").value == "none"
            assert app.number_input(key="discover_s18_capital").value == capital
            app.radio(key="_page_tab").set_value("invest").run(timeout=30)
