"""
taxes.py
========

What the strategy actually keeps.

A backtest that reports CAGR before taxes and statutory charges is answering a
question nobody can trade. In India the gap is large and it is *structural*, not
a rounding error:

- Every round trip pays STT, stamp duty, exchange transaction charges, SEBI
  turnover fees, brokerage, and GST on top of the brokerage and transaction
  charges. Round trip is roughly 0.25-0.35% of turnover for delivery equity.
- **Short-term capital gains are taxed at 20%** (Finance Act 2024, w.e.f.
  23 July 2024; 15% before that). A strategy holding for ~37 days realises
  essentially all of its gains as STCG.
- Buy-and-hold pays **12.5% LTCG** and only when it finally sells, so the
  benchmark is taxed far more lightly *and* far later. Comparing a
  high-turnover strategy to buy-and-hold on pre-tax CAGR flatters the strategy
  twice over.

This module therefore does two things the rest of the harness does not: it
prices the full statutory charge stack per trade, and it applies annual capital
gains tax to realised P&L with loss set-off carried forward the way the Income
Tax Act actually allows.

Rates are defaults, not gospel - they change with every budget. Everything is a
field on `TaxConfig` so a rate change is a config edit, not a code edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

#: Short-term capital gains on listed equity moved from 15% to 20% for transfers
#: on or after this date. Backtests spanning it must use both rates or they
#: misstate every year on one side of the line.
STCG_RATE_CHANGE = date(2024, 7, 23)


@dataclass
class TaxConfig:
    """Indian delivery-equity charges and capital gains rates."""

    # ── Statutory charges, as a fraction of turnover ──────────────────────────
    stt_buy_pct: float = 0.1  # securities transaction tax, delivery, buy side
    stt_sell_pct: float = 0.1  # and sell side
    stamp_duty_pct: float = 0.015  # buy side only
    exchange_txn_pct: float = 0.00297  # NSE equity delivery
    sebi_turnover_pct: float = 0.0001  # Rs 10 per crore
    brokerage_pct: float = 0.0  # discount brokers charge nothing on delivery
    brokerage_flat: float = 0.0  # ...or a flat fee per executed order
    brokerage_cap: float = 20.0  # per-order ceiling, when a % is charged
    gst_pct: float = 18.0  # on brokerage + exchange txn + SEBI fees

    # ── Capital gains ────────────────────────────────────────────────────────
    stcg_rate_pct: float = 20.0  # on or after 23 Jul 2024
    stcg_rate_pct_legacy: float = 15.0  # before that date
    ltcg_rate_pct: float = 12.5
    ltcg_exempt_per_year: float = 125_000.0  # annual LTCG exemption
    long_term_days: int = 365
    apply_capital_gains: bool = True

    def stcg_rate_for(self, sold_on: date) -> float:
        return (
            self.stcg_rate_pct
            if sold_on >= STCG_RATE_CHANGE
            else self.stcg_rate_pct_legacy
        )


def charges_for_leg(value: float, cfg: TaxConfig, *, is_buy: bool) -> float:
    """Statutory + broker charges on one side of one trade, in rupees.

    Kept separate from the backtest's `commission_pct`/`slippage_bps` because
    those model *execution* (spread, impact) while these are *statutory* and do
    not scale with how skilfully you trade.
    """
    if value <= 0:
        return 0.0
    stt = value * (cfg.stt_buy_pct if is_buy else cfg.stt_sell_pct) / 100.0
    stamp = value * cfg.stamp_duty_pct / 100.0 if is_buy else 0.0
    exchange = value * cfg.exchange_txn_pct / 100.0
    sebi = value * cfg.sebi_turnover_pct / 100.0

    brokerage = cfg.brokerage_flat
    if cfg.brokerage_pct > 0:
        brokerage = min(value * cfg.brokerage_pct / 100.0, cfg.brokerage_cap)

    # GST applies to brokerage and to the exchange/SEBI charges, but never to
    # STT or stamp duty - a tax on a tax is not levied here.
    gst = (brokerage + exchange + sebi) * cfg.gst_pct / 100.0
    return stt + stamp + exchange + sebi + brokerage + gst


def round_trip_charges(entry_value: float, exit_value: float, cfg: TaxConfig) -> float:
    return (
        charges_for_leg(entry_value, cfg, is_buy=True)
        + charges_for_leg(exit_value, cfg, is_buy=False)
    )


# ── Applying the charges and taxes to a closed-trade list ────────────────────


def _as_date(value: Any) -> Optional[date]:
    """Trades arrive either as dataclasses or as the JSON-ready dicts the
    service builds for artifacts, where dates have become ISO strings."""
    if value is None or isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, str):
        try:
            return pd.Timestamp(value).date()
        except ValueError:
            return None
    return None


def _field(trade: Any, name: str, default: Any = None) -> Any:
    if isinstance(trade, dict):
        return trade.get(name, default)
    return getattr(trade, name, default)


def _trade_values(trade: Any) -> Tuple[float, float, Optional[date], Optional[date]]:
    """Entry value, exit value, entry date and exit date from one closed trade."""
    qty = float(_field(trade, "quantity", _field(trade, "shares", 0)) or 0)
    entry = float(_field(trade, "entry_price", 0.0) or 0.0)
    exit_px = float(_field(trade, "exit_price", 0.0) or 0.0)
    return (
        qty * entry,
        qty * exit_px,
        _as_date(_field(trade, "entry_date")),
        _as_date(_field(trade, "exit_date")),
    )


def apply_to_trades(
    trades: Iterable[Any],
    cfg: Optional[TaxConfig] = None,
    *,
    use_recorded_costs: bool = False,
) -> pd.DataFrame:
    """Per-trade table with statutory charges and holding-period classification.

    ``use_recorded_costs`` swaps the modelled statutory charges for the costs the
    portfolio actually booked (``entry_cost + exit_cost``). Use it when the
    output has to reconcile against an equity curve: the curve already had
    execution costs taken out of cash, so charging the statutory model on top
    would tax a P&L that no cash book ever saw. Left off, behaviour is unchanged
    for every existing caller.
    """
    cfg = cfg or TaxConfig()
    rows: List[Dict[str, Any]] = []
    for t in trades:
        entry_value, exit_value, entry_date, exit_date = _trade_values(t)
        if entry_value <= 0 or exit_date is None or entry_date is None:
            continue
        if use_recorded_costs:
            charges = float(_field(t, "entry_cost", 0.0) or 0.0) + float(
                _field(t, "exit_cost", 0.0) or 0.0
            )
        else:
            charges = round_trip_charges(entry_value, exit_value, cfg)
        gross = exit_value - entry_value
        held = (exit_date - entry_date).days
        rows.append({
            "entry_date": entry_date,
            "exit_date": exit_date,
            "fy": financial_year(exit_date),
            "entry_value": entry_value,
            "exit_value": exit_value,
            "gross_pnl": gross,
            "charges": charges,
            "net_pnl": gross - charges,
            "days_held": held,
            "long_term": held > cfg.long_term_days,
        })
    return pd.DataFrame(rows)


def financial_year(day: date) -> str:
    """Indian FY label. April-March, so a March exit and an April exit are
    taxed a full year apart - which matters for loss set-off."""
    year = day.year if day.month >= 4 else day.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def capital_gains_by_year(
    trade_table: pd.DataFrame, cfg: Optional[TaxConfig] = None
) -> pd.DataFrame:
    """Per-financial-year capital gains tax, with losses carried forward.

    Short-term losses may be set off against both short- and long-term gains;
    long-term losses only against long-term gains. Both carry forward eight
    years. Modelling that matters here because the strategy has losing years,
    and a model that taxes gross gains while ignoring loss relief would overstate
    the tax bill and make the strategy look worse than it is.
    """
    cfg = cfg or TaxConfig()
    if trade_table.empty:
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []
    st_carry = 0.0
    lt_carry = 0.0

    for fy, group in trade_table.groupby("fy", sort=True):
        st = float(group.loc[~group["long_term"], "net_pnl"].sum())
        lt = float(group.loc[group["long_term"], "net_pnl"].sum())
        # Gains and losses are reported separately as well as netted: a year that
        # nets to zero on Rs 50 lakh of gains against Rs 50 lakh of losses is a
        # very different year from one that simply had no trades.
        st_leg_all = group.loc[~group["long_term"], "net_pnl"]
        lt_leg_all = group.loc[group["long_term"], "net_pnl"]
        st_gain = float(st_leg_all[st_leg_all > 0].sum())
        st_loss = float(-st_leg_all[st_leg_all < 0].sum())
        lt_gain = float(lt_leg_all[lt_leg_all > 0].sum())
        lt_loss = float(-lt_leg_all[lt_leg_all < 0].sum())
        brought_forward = st_carry + lt_carry

        st_net = st - st_carry
        st_carry = 0.0
        if st_net < 0:
            st_carry = -st_net
            st_net = 0.0

        lt_net = lt - lt_carry
        lt_carry = 0.0
        if lt_net < 0:
            lt_carry = -lt_net
            lt_net = 0.0

        # A remaining short-term loss may still shelter long-term gains.
        if st_carry > 0 and lt_net > 0:
            used = min(st_carry, lt_net)
            lt_net -= used
            st_carry -= used

        # The STCG rate changed mid-FY-2024-25 (23 Jul 2024), so a single rate
        # per year would be wrong for that year. Weight by the short-term gains
        # actually booked on either side of the change.
        st_leg = group.loc[~group["long_term"]]
        gains = st_leg.loc[st_leg["net_pnl"] > 0]
        if gains["net_pnl"].sum() > 0:
            rate = float(
                (
                    gains["exit_date"].map(cfg.stcg_rate_for) * gains["net_pnl"]
                ).sum()
                / gains["net_pnl"].sum()
            )
        else:
            rate = cfg.stcg_rate_for(group["exit_date"].max())
        stcg_tax = st_net * rate / 100.0
        taxable_lt = max(0.0, lt_net - cfg.ltcg_exempt_per_year)
        ltcg_tax = taxable_lt * cfg.ltcg_rate_pct / 100.0

        rows.append({
            "fy": fy,
            "short_term_pnl": st,
            "long_term_pnl": lt,
            "short_term_gain": st_gain,
            "short_term_loss": st_loss,
            "long_term_gain": lt_gain,
            "long_term_loss": lt_loss,
            "loss_brought_forward": brought_forward,
            "taxable_stcg": st_net,
            "taxable_ltcg": taxable_lt,
            "stcg_rate": rate,
            "tax_on_stcg": stcg_tax,
            "tax_on_ltcg": ltcg_tax,
            "tax": stcg_tax + ltcg_tax,
            "loss_carried_forward": st_carry + lt_carry,
            "charges": float(group["charges"].sum()),
        })
    return pd.DataFrame(rows).set_index("fy")


def net_summary(
    trades: Iterable[Any],
    starting_capital: float,
    years: float,
    cfg: Optional[TaxConfig] = None,
) -> Dict[str, Any]:
    """Gross vs net-of-everything outcome for a closed-trade list.

    The CAGR here is deliberately recomputed from cumulative P&L rather than
    taken from the equity curve: taxes are paid annually out of the account, so
    they compound against you, and a post-hoc percentage haircut on the gross
    CAGR would understate that.
    """
    cfg = cfg or TaxConfig()
    table = apply_to_trades(trades, cfg)
    if table.empty:
        return {}

    gross_pnl = float(table["gross_pnl"].sum())
    charges = float(table["charges"].sum())
    by_year = capital_gains_by_year(table, cfg)
    tax = float(by_year["tax"].sum()) if not by_year.empty else 0.0
    if not cfg.apply_capital_gains:
        tax = 0.0

    turnover = float(table["entry_value"].sum() + table["exit_value"].sum())
    net_pnl = gross_pnl - charges - tax

    def cagr(pnl: float) -> float:
        end = starting_capital + pnl
        if end <= 0 or years <= 0:
            return float("nan")
        return ((end / starting_capital) ** (1.0 / years) - 1.0) * 100.0

    return {
        "num_trades": int(len(table)),
        "trades_per_year": len(table) / years if years > 0 else float("nan"),
        "turnover": turnover,
        "gross_pnl": gross_pnl,
        "charges": charges,
        "charges_pct_of_turnover": charges / turnover * 100.0 if turnover else 0.0,
        "tax": tax,
        "net_pnl": net_pnl,
        "gross_cagr": cagr(gross_pnl),
        "cagr_after_charges": cagr(gross_pnl - charges),
        "net_cagr": cagr(net_pnl),
        "tax_drag_pct": cagr(gross_pnl - charges) - cagr(net_pnl),
        "charge_drag_pct": cagr(gross_pnl) - cagr(gross_pnl - charges),
        "by_year": by_year,
        "long_term_share": float(table["long_term"].mean()) * 100.0,
    }


def benchmark_net_cagr(
    gross_cagr_pct: float, years: float, cfg: Optional[TaxConfig] = None
) -> float:
    """Buy-and-hold's post-tax CAGR: one LTCG event at the end, not annually.

    This is the comparison that matters. The index is not merely taxed at a
    lower rate, it is taxed *once, at the end*, so its gains compound untaxed
    throughout. Any turnover-heavy strategy must clear that bar, not the
    pre-tax one.
    """
    cfg = cfg or TaxConfig()
    if years <= 0:
        return float("nan")
    growth = (1.0 + gross_cagr_pct / 100.0) ** years
    gain = growth - 1.0
    net_growth = 1.0 + gain * (1.0 - cfg.ltcg_rate_pct / 100.0)
    return (net_growth ** (1.0 / years) - 1.0) * 100.0


def render_tax_summary(
    summary: Dict[str, Any], benchmark_gross_cagr: Optional[float] = None,
    years: float = 0.0, cfg: Optional[TaxConfig] = None,
) -> str:
    """Human-readable block for the backtest report."""
    if not summary:
        return " No closed trades to tax.\n"
    cfg = cfg or TaxConfig()
    lines = [
        "-" * 68,
        " AFTER COSTS AND TAX - what actually reaches the bank account",
        f" Trades / year        : {summary['trades_per_year']:.1f}",
        f" Turnover             : Rs {summary['turnover']:,.0f}",
        f" Statutory charges    : Rs {summary['charges']:,.0f}"
        f"   ({summary['charges_pct_of_turnover']:.3f}% of turnover)",
        f" Capital gains tax    : Rs {summary['tax']:,.0f}",
        f" Held > 1 year        : {summary['long_term_share']:.1f}% of trades",
        "",
        f" CAGR gross           : {summary['gross_cagr']:+.2f}%",
        f" CAGR after charges   : {summary['cagr_after_charges']:+.2f}%"
        f"   (drag {summary['charge_drag_pct']:.2f}pp)",
        f" CAGR after tax       : {summary['net_cagr']:+.2f}%"
        f"   (drag {summary['tax_drag_pct']:.2f}pp)",
    ]
    if benchmark_gross_cagr is not None and years > 0:
        bench_net = benchmark_net_cagr(benchmark_gross_cagr, years, cfg)
        edge = summary["net_cagr"] - bench_net
        lines += [
            "",
            f" Benchmark, taxed once at exit : {bench_net:+.2f}%",
            f" Post-tax excess               : {edge:+.2f}%"
            + ("" if edge > 0 else "   <-- the taxman takes the edge"),
        ]
    return "\n".join(lines) + "\n"
