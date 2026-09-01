"""Rules for the ATH breakout sleeve.

Each test pins a rule that was verified numerically against the reference
dossier, so a regression here means the sleeve has drifted from the strategy
that was validated.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backtesting.breakout_ath import signals
from backtesting.breakout_ath.config import AthBreakoutConfig
from backtesting.breakout_ath.daily import (
    _exit_actions,
    _refresh_budget,
    apply_entries,
    confirm_fills,
    empty_state,
    ledger_snapshot,
    normalize_state,
    save_state,
)
from backtesting.breakout_ath.engine import AthBreakoutEngine, PriceBundle, _reset_key
from backtesting.breakout_ath.portfolio import Portfolio


def _closes(values, symbol="AAA", start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(values))
    return pd.DataFrame({symbol: values}, index=idx)


class TestEntryRule:
    def test_breakout_needs_a_new_lookback_high(self):
        # Flat, then one step up on the final bar.
        frame = _closes([100.0] * 10 + [101.0])
        out = signals.breakout_matrix(frame, lookback=5)
        assert not out.iloc[-2]["AAA"]
        assert out.iloc[-1]["AAA"]

    def test_equalling_the_prior_high_is_not_a_breakout(self):
        frame = _closes([100.0] * 10)
        assert not signals.breakout_matrix(frame, lookback=5).iloc[-1]["AAA"]

    def test_lifetime_ratio_is_close_over_running_peak(self):
        frame = _closes([50.0, 200.0, 100.0])
        ratio = signals.lifetime_ratio(frame)
        assert ratio.iloc[-1]["AAA"] == pytest.approx(0.5)

    def test_entry_needs_both_breakout_and_proximity_to_lifetime_high(self):
        # Peaks at 200, collapses, then makes a 5-session high at 120 — a
        # breakout, but only 60% of the lifetime high, so it must not qualify.
        values = [100.0, 200.0] + [80.0] * 8 + [120.0]
        frame = _closes(values)
        assert signals.breakout_matrix(frame, lookback=5).iloc[-1]["AAA"]
        assert not signals.entry_matrix(frame, lookback=5, floor=0.85).iloc[-1]["AAA"]

    def test_entry_qualifies_when_close_is_inside_the_band(self):
        values = [100.0] * 10 + [101.0]
        frame = _closes(values)
        assert signals.entry_matrix(frame, lookback=5, floor=0.85).iloc[-1]["AAA"]


class TestTrailingStop:
    """anchor = running max close since entry; stop = anchor * (1 - sl_pct)."""

    def _state(self, anchor, entry=100.0):
        state = empty_state(1_000_000.0)
        state["positions"] = [
            {
                "symbol": "AAA",
                "industry": "Test",
                "entry_date": "2020-01-01",
                "entry_price": entry,
                "quantity": 10.0,
                "anchor": anchor,
            }
        ]
        return state

    def test_stop_sits_sixteen_percent_below_the_anchor(self):
        cfg = AthBreakoutConfig()
        assert cfg.stop_multiple == pytest.approx(0.84)

    def test_no_exit_while_the_close_holds_above_the_stop(self):
        cfg = AthBreakoutConfig()
        state = self._state(anchor=100.0)
        live = pd.Series({"AAA": 84.5})
        assert (
            _exit_actions(cfg, state, live, date(2020, 2, 1), lambda s, f="?": f) == []
        )

    def test_exit_once_the_close_breaks_the_stop(self):
        cfg = AthBreakoutConfig()
        state = self._state(anchor=100.0)
        live = pd.Series({"AAA": 83.9})
        out = _exit_actions(cfg, state, live, date(2020, 2, 1), lambda s, f="?": f)
        assert [e["symbol"] for e in out] == ["AAA"]
        assert out[0]["reason"] == "TRAIL_SL"
        assert out[0]["stop_level"] == pytest.approx(84.0)

    def test_the_anchor_ratchets_up_and_never_down(self):
        cfg = AthBreakoutConfig()
        state = self._state(anchor=100.0)
        _exit_actions(
            cfg, state, pd.Series({"AAA": 150.0}), date(2020, 2, 1), lambda s, f="?": f
        )
        assert state["positions"][0]["anchor"] == pytest.approx(150.0)
        _exit_actions(
            cfg, state, pd.Series({"AAA": 130.0}), date(2020, 2, 2), lambda s, f="?": f
        )
        assert state["positions"][0]["anchor"] == pytest.approx(150.0)

    def test_a_gap_fills_at_the_close_not_the_stop(self):
        """The reference book took a 20.6% loss through a gap, so fills are
        at the breaking close rather than the stop level."""
        cfg = AthBreakoutConfig()
        state = self._state(anchor=100.0)
        out = _exit_actions(
            cfg, state, pd.Series({"AAA": 70.0}), date(2020, 2, 1), lambda s, f="?": f
        )
        assert out[0]["price"] == pytest.approx(70.0)
        assert out[0]["return_pct"] == pytest.approx(-0.30)


class TestSizing:
    """Commission comes out of the slot budget, and cash falls by the whole
    budget — the reference book's day one reproduces to the rupee."""

    def test_day_one_budget_cost_and_cash(self):
        cfg = AthBreakoutConfig()
        pf = Portfolio(cash=cfg.start_capital, cost_rate=cfg.cost_rate)
        budget = cfg.start_capital / cfg.max_positions
        assert budget == pytest.approx(357_142.857142, rel=1e-9)

        pf.open_position(
            symbol="AAA",
            industry="Test",
            day=date(2012, 10, 19),
            price=41.740585,
            budget=budget,
        )
        fill = pf.fills[-1]
        assert fill.cost == pytest.approx(892.857143, rel=1e-6)
        assert fill.value == pytest.approx(356_250.0, rel=1e-9)
        assert pf.cash == pytest.approx(9_642_857.142857, rel=1e-9)

    def test_quantity_is_fractional(self):
        cfg = AthBreakoutConfig()
        pf = Portfolio(cash=cfg.start_capital, cost_rate=cfg.cost_rate)
        pf.open_position(
            symbol="AAA",
            industry="Test",
            day=date(2012, 10, 19),
            price=41.740585,
            budget=cfg.start_capital / cfg.max_positions,
        )
        assert pf.positions["AAA"].quantity == pytest.approx(8534.858752, rel=1e-6)


class TestBudgetCadence:
    def test_budget_is_restruck_each_quarter(self):
        cfg = AthBreakoutConfig()
        state = empty_state(10_000_000.0)

        _refresh_budget(cfg, state, date(2020, 1, 15), 10_000_000.0)
        first = state["budget"]
        assert first == pytest.approx(10_000_000.0 / 28)

        # Same quarter: the budget must not move even though equity grew.
        _refresh_budget(cfg, state, date(2020, 2, 20), 20_000_000.0)
        assert state["budget"] == pytest.approx(first)

        # New quarter: it re-strikes off current equity.
        _refresh_budget(cfg, state, date(2020, 4, 2), 20_000_000.0)
        assert state["budget"] == pytest.approx(20_000_000.0 / 28)

    def test_reset_key_groups_by_quarter(self):
        assert _reset_key(date(2020, 1, 5), "Q") == _reset_key(date(2020, 3, 31), "Q")
        assert _reset_key(date(2020, 3, 31), "Q") != _reset_key(date(2020, 4, 1), "Q")

    def test_never_resetting_keeps_one_key(self):
        assert _reset_key(date(2020, 1, 5), "N") == _reset_key(date(2024, 9, 9), "N")


class TestConfig:
    def test_defaults_match_the_reference_dossier(self):
        cfg = AthBreakoutConfig()
        assert (cfg.max_positions, cfg.sl_pct, cfg.ath_band) == (28, 0.16, 0.15)
        assert cfg.selection_rule == "mom_3m"
        assert cfg.lookback == 252
        assert cfg.slot_reset_freq == "Q"
        assert cfg.cost_bps == 25.0
        assert cfg.ath_floor == pytest.approx(0.85)
        assert cfg.cost_rate == pytest.approx(0.0025)

    @pytest.mark.parametrize(
        "field, value",
        [
            ("max_positions", 0),
            ("sl_pct", 0.0),
            ("sl_pct", 1.0),
            ("ath_band", 1.0),
            ("lookback", 1),
            ("cost_bps", -1.0),
            ("start_capital", 0.0),
            ("slot_reset_freq", "W"),
            ("selection_rule", "nope"),
        ],
    )
    def test_validate_rejects_nonsense(self, field, value):
        cfg = AthBreakoutConfig(**{field: value})
        with pytest.raises(ValueError):
            cfg.validate()


class TestState:
    def test_unknown_payload_falls_back_to_an_empty_book(self):
        assert normalize_state("not a book", 500.0) == empty_state(500.0)

    def test_positions_are_normalised(self):
        state = normalize_state(
            {"cash": 100.0, "positions": [{"symbol": "aaa.ns", "entry_price": 10.0}]},
            1_000.0,
        )
        pos = state["positions"][0]
        assert pos["symbol"] == "AAA"
        # The anchor defaults to the entry price for a brand new position.
        assert pos["anchor"] == pytest.approx(10.0)

    def test_a_v1_book_is_readable(self):
        """Books written before marks and pending entries existed must still load."""
        state = normalize_state(
            {"version": 1, "cash": 900.0, "positions": [], "closed": []}, 1_000.0
        )
        assert state["cash"] == pytest.approx(900.0)
        assert state["pending_entries"] == []
        assert state["marks"] == {}


class TestConfirmFills:
    """Suggestions are not holdings until the orders actually fill."""

    @staticmethod
    def _book(tmp_path):
        state = empty_state(500_000.0)
        state["pending_entries"] = [
            {"symbol": "AAA", "industry": "Tech", "budget": 125_000.0, "price": 100.0},
            {"symbol": "BBB", "industry": "Bank", "budget": 125_000.0, "price": 200.0},
        ]
        state["pending_session"] = "2026-09-01"
        state["last_session"] = "2026-09-01"
        path = tmp_path / "book.json"
        save_state(path, state)
        return path

    def test_only_confirmed_names_reach_the_book(self, tmp_path):
        path = self._book(tmp_path)
        state = confirm_fills(
            [{"symbol": "AAA", "industry": "Tech", "budget": 125_000.0}],
            day=date(2026, 9, 2),
            state_path=path,
            capital=500_000.0,
        )
        assert [p["symbol"] for p in state["positions"]] == ["AAA"]
        # The skipped suggestion must not linger and look like a holding.
        assert state["pending_entries"] == []

    def test_a_worse_fill_buys_fewer_shares_rather_than_spending_more(self, tmp_path):
        path = self._book(tmp_path)
        state = confirm_fills(
            [{"symbol": "AAA", "budget": 125_000.0, "fill_price": 125.0}],
            day=date(2026, 9, 2),
            state_path=path,
            capital=500_000.0,
            cost_rate=0.0025,
        )
        pos = state["positions"][0]
        assert pos["entry_price"] == pytest.approx(125.0)
        assert pos["quantity"] == pytest.approx((125_000.0 * 0.9975) / 125.0)
        # Cash falls by the budget, never by more.
        assert state["cash"] == pytest.approx(375_000.0)

    def test_a_fill_can_never_overdraw_the_book(self):
        state = empty_state(1_000.0)
        apply_entries(
            state,
            [{"symbol": "AAA", "budget": 5_000.0, "price": 10.0}],
            date(2026, 9, 2),
        )
        assert state["cash"] == pytest.approx(0.0)


class TestLedgerSnapshot:
    def test_a_missing_book_reports_that_it_does_not_exist(self, tmp_path):
        snap = ledger_snapshot(state_path=tmp_path / "absent.json")
        assert snap["exists"] is False
        assert snap["as_of"] is None

    def test_the_snapshot_marks_positions_at_the_last_saved_close(self, tmp_path):
        cfg = AthBreakoutConfig(start_capital=100_000.0, max_positions=4, sl_pct=0.16)
        state = empty_state(100_000.0)
        state["cash"] = 90_000.0
        state["positions"] = [
            {
                "symbol": "AAA",
                "industry": "Tech",
                "entry_date": "2026-08-01",
                "entry_price": 100.0,
                "quantity": 100.0,
                "anchor": 120.0,
            }
        ]
        state["marks"] = {"AAA": 110.0}
        state["last_session"] = "2026-09-01"
        path = tmp_path / "book.json"
        save_state(path, state)

        snap = ledger_snapshot(cfg, state_path=path, today=date(2026, 9, 2))
        book = snap["book"]
        assert book["deployed"] == pytest.approx(11_000.0)
        assert book["equity"] == pytest.approx(101_000.0)
        assert book["free_slots"] == 3

        holding = snap["holdings"][0]
        # The stop trails the anchor, not the entry or the last close.
        assert holding["stop_level"] == pytest.approx(120.0 * 0.84)
        assert holding["return_pct"] == pytest.approx(10.0)

    def test_a_book_days_behind_is_flagged_stale(self, tmp_path):
        state = empty_state(100_000.0)
        state["last_session"] = "2026-09-01"
        path = tmp_path / "book.json"
        save_state(path, state)

        fresh = ledger_snapshot(state_path=path, today=date(2026, 9, 2))
        assert fresh["freshness"]["stale"] is False

        stale = ledger_snapshot(state_path=path, today=date(2026, 9, 15))
        assert stale["freshness"]["stale"] is True
        # Weekends do not count against the book.
        assert stale["freshness"]["weekdays_behind"] == 10


class TestPitMembership:
    """Point-in-time membership must gate entries but never force an exit."""

    @staticmethod
    def _bundle(membership):
        # Two names, one long uptrend so both break out every session.
        days = pd.bdate_range("2020-01-01", periods=400)
        rising = pd.Series(range(1, len(days) + 1), index=days, dtype=float)
        closes = pd.DataFrame({"AAA.NS": rising, "BBB.NS": rising * 2})
        return PriceBundle(closes=closes, membership=membership)

    def _run(self, membership):
        cfg = AthBreakoutConfig(
            max_positions=2, lookback=20, ath_band=0.99, start_capital=100_000.0
        )
        return AthBreakoutEngine(cfg, self._bundle(membership)).run()

    def test_non_members_are_never_bought(self):
        bundle = self._bundle(None)
        member = pd.DataFrame(
            True, index=bundle.closes.index, columns=["AAA.NS", "BBB.NS"]
        )
        member["BBB.NS"] = False

        bought = {fill.symbol for fill in self._run(member).pf.fills}
        assert bought == {"AAA.NS"}

    def test_absent_membership_leaves_the_universe_open(self):
        bought = {fill.symbol for fill in self._run(None).pf.fills}
        assert bought == {"AAA.NS", "BBB.NS"}

    def test_leaving_the_index_does_not_close_a_position(self):
        bundle = self._bundle(None)
        member = pd.DataFrame(
            True, index=bundle.closes.index, columns=["AAA.NS", "BBB.NS"]
        )
        # Everything drops out of the index halfway through.
        member.iloc[200:] = False

        engine = self._run(member)
        # Prices only rise, so the trailing stop never fires and both names
        # must still be held at the end despite having left the index.
        assert set(engine.pf.positions) == {"AAA.NS", "BBB.NS"}
