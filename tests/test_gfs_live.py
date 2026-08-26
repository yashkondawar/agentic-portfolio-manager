"""Tests for the live GFS runner.

The central claim this strategy makes is that it *is* the backtest - not a
faithful re-implementation of it, but the same engine resumed against a saved
book. The load-bearing test here is
:func:`test_resuming_in_chunks_matches_one_shot`: if serialising the book
between sessions changed anything at all - a dropped pending order, a lost stop
ratchet, a reset high-water mark - the chunked run and the one-shot run would
diverge, and the live numbers would stop meaning what the research measured.

Everything else in this file guards the boundary around that claim: that the
pinned config really is pinned, and that the persisted book survives a
round-trip.
"""

from datetime import date, timedelta

import pytest

from backtesting.gfs.config import GFSConfig
from backtesting.gfs.engine import GFSBacktestEngine
from backtesting.gfs.panels import (
    build_panels,
    build_qualify_matrix,
    build_regime_panel,
    build_sector_panel,
    master_calendar,
)
from backtesting.gfs.portfolio import Position
from backtesting.gfs.strategy import ExitOp

from gfs import config as live_config
from gfs import state as live_state

from test_gfs_engine import build_market


# ── shared fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def market():
    return build_market()


def _cfg(**kw) -> GFSConfig:
    """A config that trades often enough on a random walk to be worth comparing."""
    base = dict(
        start_date=date(2019, 1, 1),
        end_date=date(2021, 12, 31),
        min_daily_bars=250,
        min_weekly_bars=52,
        min_monthly_bars=24,
        min_turnover_cr=0.0,
        min_price=0.0,
        max_atr_pct=100.0,
        use_regime_filter=False,
        use_sector_filter=False,
        starting_capital=1_000_000.0,
        max_positions=5,
    )
    base.update(kw)
    return GFSConfig(**base)


def _pipeline(data, universe, cfg):
    panels = build_panels(data, universe, cfg)
    calendar = master_calendar(data.benchmark, panels)
    return (
        panels,
        calendar,
        build_sector_panel(panels, calendar, cfg),
        build_regime_panel(data.benchmark, panels, calendar, cfg),
        build_qualify_matrix(panels, calendar, cfg),
    )


def _fresh_engine(data, universe, cfg) -> GFSBacktestEngine:
    panels, calendar, sector, regime, qualify = _pipeline(data, universe, cfg)
    return GFSBacktestEngine(cfg, panels, sector, regime, qualify, calendar)


def _fingerprint(engine: GFSBacktestEngine) -> dict:
    """Everything about a book that must not depend on how it was reached."""
    return {
        "cash": round(engine.pf.cash, 6),
        "positions": sorted(
            (
                p.symbol,
                round(p.quantity, 6),
                round(p.entry_price, 6),
                p.entry_date.isoformat(),
                round(p.stop_loss, 6),
                round(p.initial_stop, 6),
                round(p.highest_close, 6),
                round(p.highest_high, 6),
                round(p.lowest_low, 6),
            )
            for p in engine.pf.positions.values()
        ),
        "trades": [
            (
                t.symbol,
                t.entry_date.isoformat(),
                t.exit_date.isoformat(),
                round(t.entry_price, 6),
                round(t.exit_price, 6),
                round(t.quantity, 6),
                t.exit_reason,
            )
            for t in engine.pf.closed
        ],
        "equity": [
            (s["date"], round(s["equity"], 4), round(s["cash"], 4))
            for s in engine.pf.equity_curve
        ],
    }


# ── the fidelity guarantee ───────────────────────────────────────────────────


def test_resuming_in_chunks_matches_one_shot(market):
    """Saving and reloading the book between sessions must change nothing.

    This is the whole premise of the live strategy. The chunk boundaries are
    deliberately awkward (mid-week, uneven lengths) so that a pending entry or a
    queued exit is *guaranteed* to straddle a save/load boundary - which is the
    exact state a naive implementation loses.
    """
    data, universe = market
    cfg = _cfg()

    one_shot = _fresh_engine(data, universe, cfg)
    one_shot.run(cfg.start_date, cfg.end_date)
    expected = _fingerprint(one_shot)

    boundaries = [
        date(2019, 1, 1),
        date(2019, 4, 17),
        date(2019, 11, 6),
        date(2020, 3, 25),
        date(2020, 3, 26),  # a single-session chunk
        date(2021, 2, 9),
        date(2021, 12, 31),
    ]

    book = live_state.Book()
    book.open_with(cfg.starting_capital, boundaries[0])
    for start, end in zip(boundaries, boundaries[1:]):
        chunk_start = start if start == boundaries[0] else start + timedelta(days=1)
        engine = _fresh_engine(data, universe, cfg)
        book.restore_into(engine)
        engine.run(chunk_start, end)
        book.capture_from(engine)
        book.last_session = end
        # Force the state through the exact serialisation the DB uses, so a
        # field that only survives in memory cannot pass this test.
        book = live_state.Book.from_document(book.to_document())

    replayed = _fresh_engine(data, universe, cfg)
    book.restore_into(replayed)

    assert _fingerprint(replayed) == expected


def test_a_pending_order_survives_the_save_load_boundary(market):
    """A queued entry must still be queued after a round-trip.

    Without this, a signal generated on the last session of a run would be
    silently dropped instead of filling at the next open - the live strategy
    would quietly trade a different rule than the one that was measured.
    """
    data, universe = market
    cfg = _cfg()

    engine = _fresh_engine(data, universe, cfg)
    # Walk forward until a scan actually leaves something queued.
    end = cfg.start_date
    for _ in range(400):
        end += timedelta(days=1)
        engine = _fresh_engine(data, universe, cfg)
        engine.run(cfg.start_date, end)
        if engine.pending_entries:
            break
    assert engine.pending_entries, "no session in range produced a queued entry"

    book = live_state.Book()
    book.open_with(cfg.starting_capital, cfg.start_date)
    book.capture_from(engine)
    restored = live_state.Book.from_document(book.to_document())

    assert [s.symbol for s in restored.pending_entries] == [
        s.symbol for s in engine.pending_entries
    ]
    assert restored.pending_entries[0].signal_date == engine.pending_entries[0].signal_date
    assert restored.pending_entries[0].stop_hint == pytest.approx(
        engine.pending_entries[0].stop_hint
    )


def test_book_round_trips_through_a_document():
    book = live_state.Book()
    book.open_with(250_000.0, date(2024, 1, 2))
    book.last_session = date(2024, 3, 15)
    book.pending_exits = [("ACME", ExitOp(price=101.5, reason="rsi_target", fill="next_open"))]
    book.equity_curve = [{"date": "2024-03-15", "equity": 250_000.0, "cash": 250_000.0}]

    restored = live_state.Book.from_document(book.to_document())

    assert restored.starting_capital == 250_000.0
    assert restored.opened_on == date(2024, 1, 2)
    assert restored.last_session == date(2024, 3, 15)
    assert restored.equity_curve == book.equity_curve
    symbol, op = restored.pending_exits[0]
    assert (symbol, op.reason, op.fill) == ("ACME", "rsi_target", "next_open")


def test_a_newer_book_is_refused_rather_than_misread():
    with pytest.raises(RuntimeError, match="version"):
        live_state.Book.from_document({"version": live_state.BOOK_VERSION + 1})


def test_an_empty_document_opens_as_an_empty_book():
    book = live_state.Book.from_document(None)
    assert book.is_empty
    assert book.positions == {} and book.closed == []


# ── the configuration really is the researched one ───────────────────────────


def test_live_defaults_are_the_adopted_configuration():
    cfg = live_config.build_config(
        {}, start=date(2024, 1, 1), end=date(2024, 6, 30)
    )
    assert cfg.s_rsi_entry == 43.0
    assert cfg.exit_rsi == 70.0
    assert cfg.atr_stop_mult == 3.5
    assert cfg.min_headroom_pct == 10.0
    assert cfg.regime_mode == "breadth"
    assert cfg.min_breadth_pct == 40.0
    assert cfg.max_positions == 4
    assert cfg.max_position_pct == 30.0


def test_the_time_stop_is_off_and_cannot_be_turned_on():
    """The user's instruction was explicit: exits come from RSI and price only."""
    cfg = live_config.build_config(
        {"max_holding_days": 45}, start=date(2024, 1, 1), end=date(2024, 6, 30)
    )
    assert cfg.max_holding_days == 0


def test_leak_free_higher_timeframes_are_pinned():
    """`live` HTF mode roughly halved returns in testing; it is not selectable."""
    cfg = live_config.build_config(
        {"htf_mode": "live"}, start=date(2024, 1, 1), end=date(2024, 6, 30)
    )
    assert cfg.htf_mode == "closed"


def test_user_parameters_still_reach_the_config():
    cfg = live_config.build_config(
        {"s_rsi_entry": 38.0, "exit_rsi": 60.0, "max_positions": 6},
        start=date(2024, 1, 1),
        end=date(2024, 6, 30),
    )
    assert (cfg.s_rsi_entry, cfg.exit_rsi, cfg.max_positions) == (38.0, 60.0, 6)


def test_shadow_threshold_is_dropped_when_it_matches_the_live_rule():
    assert live_config.shadow_exit_rsi({"exit_rsi": 70.0}) == 60.0
    assert live_config.shadow_exit_rsi({"exit_rsi": 60.0, "shadow_exit_rsi": 60.0}) is None
    assert live_config.shadow_exit_rsi({"shadow_exit_rsi": 0}) is None


# ── the registered strategy ──────────────────────────────────────────────────


def test_strategy_is_registered_with_usable_specs():
    from core.registry import get_strategy

    strategy = get_strategy("gfs_live")
    specs = {s.name: s for s in strategy.param_specs()}
    assert specs["exit_rsi"].default == 70.0
    assert specs["s_rsi_entry"].default == 43.0
    assert specs["regime_mode"].choices == list(live_config.REGIME_MODES)
    # Every spec must carry a group, or the form renders an unlabelled pile.
    assert all(s.group for s in strategy.param_specs())


def test_snapshot_of_an_empty_book_is_renderable():
    from gfs import engine as live_engine

    snap = live_engine.ledger_snapshot()
    assert snap["holdings"] == []
    assert snap["book"]["open_positions"] == 0
    # A book with no history must not claim an annualised return.
    assert "cagr_pct" not in snap["metrics"]


def _seeded_book() -> live_state.Book:
    """A saved book with one open position and a display mark, as a real run leaves it."""
    book = live_state.Book()
    book.open_with(500_000.0, date(2024, 1, 2))
    book.last_session = date(2024, 3, 15)
    book.positions = {
        "ACME": Position(
            symbol="ACME",
            sector="IT",
            quantity=100,
            entry_price=100.0,
            entry_date=date(2024, 2, 1),
            stop_loss=90.0,
            initial_stop=90.0,
            target_price=130.0,
            atr_at_entry=3.0,
            entry_rsi_d=38.0,
            entry_rsi_w=64.0,
            entry_rsi_m=67.0,
        )
    }
    book.marks = {"ACME": {"price": 120.0, "rsi_d": 65.0, "rsi_w": 66.0, "rsi_m": 68.0}}
    return book


def test_offline_snapshot_marks_positions_at_the_last_run_price():
    """The always-on panel must not report every open position at 0.0%."""
    from gfs import engine as live_engine

    live_state.save_book(_seeded_book())
    try:
        row = live_engine.ledger_snapshot()["holdings"][0]
    finally:
        live_state.reset_book()

    assert row["last_price"] == 120.0
    assert row["unrealized_pct"] == pytest.approx(20.0)
    assert row["rsi_d"] == 65.0
    assert row["days_held"] == 43


def test_the_up_to_date_report_renders_and_still_flags_the_shadow_rule():
    """Regression: the no-new-sessions path once emitted a different holdings
    shape than the replay path (KeyError on render) and never flagged a shadow
    exit. Both are display-only, but a report that crashes is a broken run."""
    from gfs import engine as live_engine

    live_state.save_book(_seeded_book())
    try:
        result = live_engine.run(
            {"as_of": date(2024, 3, 15), "dry_run": True, "shadow_exit_rsi": 60.0}
        )
    finally:
        live_state.reset_book()

    assert result["data"]["up_to_date"] is True
    # RSI 65 is past the shadow threshold of 60, so it must be named.
    assert result["data"]["shadow"]["would_exit"] == ["ACME"]
    assert "ACME" in result["report"]


def test_replay_and_snapshot_holdings_agree_on_shape():
    """Both paths feed the same renderer and the same UI table."""
    from gfs import engine as live_engine

    live_state.save_book(_seeded_book())
    try:
        snapshot_row = live_engine.ledger_snapshot()["holdings"][0]
    finally:
        live_state.reset_book()

    required = {
        "symbol", "sector", "quantity", "entry_date", "entry_price", "last_price",
        "value", "unrealized_pct", "stop_price", "stop_distance_pct", "target_price",
        "days_held", "entry_rsi_d", "entry_rsi_w", "entry_rsi_m",
        "rsi_d", "rsi_w", "rsi_m", "shadow_exit",
    }
    assert required <= set(snapshot_row)


# ── Data freshness ────────────────────────────────────────────────────────────
# A benchmark parse bug once froze the master calendar four sessions in the
# past. The run reported its stale as-of date and produced no signals, with no
# error anywhere. These pin the guard that makes that loud.


def test_a_weekend_gap_is_not_stale():
    """Friday close read on Sunday is normal, not a fault."""
    from gfs.engine import _freshness

    fresh = _freshness(date(2024, 3, 15), date(2024, 3, 17))  # Fri -> Sun

    assert fresh["weekdays_behind"] == 0
    assert fresh["stale"] is False


def test_tonights_close_not_published_yet_is_tolerated():
    """One weekday behind is the provider running late, which self-heals."""
    from gfs.engine import _freshness

    fresh = _freshness(date(2024, 3, 14), date(2024, 3, 15))  # Thu -> Fri

    assert fresh["weekdays_behind"] == 1
    assert fresh["stale"] is False


def test_the_benchmark_freeze_that_started_all_this_is_stale():
    """The real incident: data to Friday, run on the following Tuesday."""
    from gfs.engine import _freshness

    fresh = _freshness(date(2024, 3, 15), date(2024, 3, 19))  # Fri -> Tue

    assert fresh["weekdays_behind"] == 2
    assert fresh["stale"] is True


def test_a_stale_run_shouts_before_it_lists_any_order():
    """The warning has to outrank the orders, or it will be scrolled past."""
    from gfs.engine import render_report

    report = render_report(
        {
            "as_of": "2024-03-15",
            "sessions_replayed": ["2024-03-15"],
            "book": {},
            "orders": [],
            "holdings": [],
            "tradebook": [],
            "freshness": {
                "last_session": "2024-03-15",
                "today": "2024-03-19",
                "weekdays_behind": 2,
                "stale": True,
            },
        }
    )

    assert "STALE PRICE DATA" in report
    assert report.index("STALE PRICE DATA") < report.index("ORDERS FOR THE NEXT OPEN")


def test_a_fresh_run_says_nothing_about_staleness():
    from gfs.engine import render_report

    report = render_report(
        {
            "as_of": "2024-03-15",
            "sessions_replayed": ["2024-03-15"],
            "book": {},
            "orders": [],
            "holdings": [],
            "tradebook": [],
            "freshness": {
                "last_session": "2024-03-15",
                "today": "2024-03-15",
                "weekdays_behind": 0,
                "stale": False,
            },
        }
    )

    assert "STALE" not in report


def test_the_stale_branch_in_run_is_actually_executable(monkeypatch):
    """The warning sits in a branch that never fires in a healthy run, so a typo
    in it survives every other test and only shows up on the day it matters."""
    from gfs import engine as live_engine

    monkeypatch.setattr(
        live_engine,
        "_freshness",
        lambda last, today: {
            "last_session": "2024-03-11",
            "today": "2024-03-15",
            "weekdays_behind": 4,
            "stale": True,
        },
    )
    live_state.save_book(_seeded_book())
    try:
        result = live_engine.run({"as_of": date(2024, 3, 15), "dry_run": True})
    finally:
        live_state.reset_book()

    assert result["data"]["freshness"]["stale"] is True
    assert "STALE PRICE DATA" in result["report"]


def test_a_queued_order_is_visible_in_the_saved_book_not_just_counted():
    """The window between the run that queues an order and the run that fills it
    is exactly when the user has to place it. Reporting only a count there makes
    the order unactionable - they cannot buy a number."""
    from gfs import engine as live_engine
    from backtesting.gfs.strategy import EntrySignal

    book = _seeded_book()
    book.pending_entries = [
        EntrySignal(
            symbol="GABRIEL",
            sector="Automobile and Auto Components",
            signal_date=date(2024, 3, 15),
            close=1346.0,
            atr=56.96,
            stop_hint=1146.63,
            rsi_d=41.6,
            rsi_w=67.3,
            rsi_m=72.9,
            sector_rank=3.0,
            resistance=1596.7,
            score=0.51,
        )
    ]
    live_state.save_book(book)
    try:
        snap = live_engine.ledger_snapshot()
    finally:
        live_state.reset_book()

    assert snap["pending"] == 1
    orders = snap["orders"]
    assert [o["symbol"] for o in orders] == ["GABRIEL"]
    order = orders[0]
    assert order["action"] == "BUY"
    assert order["stop_price"] == 1146.63
    # An indicative size, so the capital it will absorb is visible.
    assert isinstance(order["quantity"], int) and order["quantity"] > 0
