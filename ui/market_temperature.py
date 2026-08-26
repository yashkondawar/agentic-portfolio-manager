"""Market Temperature dashboard page.

The page is organised around the question a person actually has when they open
it: *I have money. What should I do with it right now, and why should I believe
you?* So the order is verdict, then action, then reasoning, then evidence, then
the honest limitations — not the other way round.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from research.market_temperature import (
    DEFAULT_MARKET,
    MARKETS,
    MarketDataUnavailable,
    MarketTemperature,
    compute_market_temperature,
    deployment_schedule,
)
from research.market_temperature.config import TEMPERATURE_BANDS
from ui.components import page_header

_BAND_ORDER = ["Cold", "Cool", "Neutral", "Warm", "Hot"]


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def _load(market_key: str, refresh: bool) -> MarketTemperature:
    return compute_market_temperature(MARKETS[market_key], refresh=refresh)


def market_temperature_page() -> None:
    page_header(
        "Market Temperature",
        "A long-horizon read on whether the market is unusually cheap or "
        "expensive — built to guide how fast you deploy new money, not to trade.",
    )

    controls = st.columns([3, 2, 2])
    market_key = controls[0].selectbox(
        "Index",
        list(MARKETS),
        index=list(MARKETS).index(DEFAULT_MARKET),
        format_func=lambda k: MARKETS[k].label,
    )
    horizon = controls[1].selectbox(
        "Evidence horizon", [12, 36, 60], format_func=lambda m: f"Next {m // 12} year(s)"
    )
    refresh = controls[2].button("Refresh data", use_container_width=True)

    try:
        with st.spinner(f"Loading {MARKETS[market_key].label}..."):
            temp = _load(market_key, refresh)
    except MarketDataUnavailable as exc:
        st.error(f"Cannot show a reading for {MARKETS[market_key].label}.\n\n{exc}")
        st.caption(
            "This page deliberately has no fallback. It will not substitute "
            "simulated data to keep the charts looking full."
        )
        return

    if MARKETS[market_key].note:
        st.caption(MARKETS[market_key].note)

    _render_verdict(temp)
    st.divider()

    action_tab, why_tab, evidence_tab, history_tab, trust_tab = st.tabs(
        [
            "What to do",
            "Why it says that",
            "What happened next",
            "History",
            "How much to trust this",
        ]
    )
    with action_tab:
        _render_action(temp)
    with why_tab:
        _render_rules(temp)
    with evidence_tab:
        _render_evidence(temp, horizon)
    with history_tab:
        _render_history(temp)
    with trust_tab:
        _render_trust(temp)


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #


def _render_verdict(temp: MarketTemperature) -> None:
    st.markdown(
        f"""
        <div style="
            border-left: .5rem solid {temp.band.colour};
            background: {temp.band.colour}14;
            border-radius: .6rem;
            padding: 1.1rem 1.4rem;
            margin-bottom: .75rem;">
          <div style="font-size:.8rem;letter-spacing:.09em;text-transform:uppercase;opacity:.7;">
            {temp.market.label} &middot; as of {temp.asof.strftime('%d %b %Y')}
          </div>
          <div style="font-size:2.3rem;font-weight:700;color:{temp.band.colour};line-height:1.15;">
            {temp.band.label}
          </div>
          <div style="font-size:1.05rem;opacity:.85;">{temp.band.headline}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(f"**{temp.band.guidance}**")

    cols = st.columns(4)
    cols[0].metric(
        "Rules firing now",
        f"{len(temp.active_rules)} of {len(temp.readings)}",
        help="How many of the underlying checks are actually saying something.",
    )
    cols[1].metric(
        "Below all-time high",
        f"{temp.drawdown_from_alltime:.1f}%",
        help="Distance from the highest total-return level ever recorded.",
    )
    cols[2].metric(
        "Time spent neutral",
        f"{temp.neutral_share:.0%}",
        help="Share of months in history where no rule fired. A quiet signal is normal.",
    )
    cols[3].metric(
        "History available",
        f"{temp.years_of_history:.0f} yrs",
        help=f"{temp.data_start.strftime('%b %Y')} to {temp.data_end.strftime('%b %Y')}.",
    )


# --------------------------------------------------------------------------- #
# Action
# --------------------------------------------------------------------------- #


def _render_action(temp: MarketTemperature) -> None:
    plan = temp.deployment
    st.subheader("Deploying new money")
    st.caption(
        "This signal is far too weak to justify buying and selling an existing "
        "portfolio — the trading costs and capital-gains tax exceed the measured "
        "edge. It is only used here to set the *pace* at which new cash goes in, "
        "a decision you have to make anyway and which costs nothing extra."
    )

    if temp.is_neutral:
        st.info(
            "No rule is firing, so there is no reason to deviate from your normal "
            "plan. The most valuable thing this page can tell you is that there is "
            "nothing to do — which is the case most of the time."
        )

    left, right = st.columns([2, 3])
    with left:
        amount = st.number_input(
            "Lump sum available",
            min_value=0.0,
            value=100_000.0,
            step=10_000.0,
            format="%.0f",
        )
        st.metric(
            "Suggested SIP pace",
            f"{plan.sip_multiplier:.1f}x your normal",
            help="Multiplier on your regular monthly contribution while this band holds.",
        )
        st.caption(plan.tranche_note)

    with right:
        if amount > 0:
            schedule = pd.DataFrame(deployment_schedule(amount, temp))
            schedule["Amount"] = schedule["Amount"].map(
                lambda v: f"{temp.market.currency} {v:,.0f}"
            )
            st.dataframe(schedule, use_container_width=True, hide_index=True)
            st.caption(
                "A schedule, not an instruction. Spreading purchases reduces the "
                "damage from being wrong about timing, which is the realistic "
                "assumption here."
            )

    st.divider()
    st.markdown("**What this page will never tell you to do**")
    st.markdown(
        "- Sell something you already own. The evidence does not support it.\n"
        "- Stop your SIPs. Pausing contributions in cheap markets is the single "
        "most expensive mistake this framework's own history warns against.\n"
        "- Move a large share of your portfolio on one reading. The measured edge "
        "is under half a percent a year, and only in Indian indices."
    )


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #


def _render_rules(temp: MarketTemperature) -> None:
    st.subheader("The underlying checks")
    st.caption(
        "Each check looks at one horizon and votes. The votes are weighted and "
        "averaged into a single score, shown at the bottom."
    )

    icons = {"Bullish": "🟢", "Bearish": "🔴", "Quiet": "⚪", "Not enough history": "⚫"}
    rows = []
    for reading in temp.readings:
        rows.append(
            {
                "": icons.get(reading.verdict, "⚪"),
                "Check": reading.label,
                "Reading": (
                    "n/a"
                    if reading.observed is None
                    else f"{reading.observed:+.1f}%"
                ),
                "Measures": reading.observed_label,
                "Vote": "—" if reading.score is None else f"{reading.score:+.1f}",
                "Weight": f"{reading.weight:.1f}",
                "What it means": reading.detail,
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.metric(
        "Composite score",
        f"{temp.score:+.3f}",
        help=(
            "Weighted average vote on a -2 to +2 scale. Positive means cheap. "
            "In practice it rarely leaves the -0.3 to +0.6 range, because most "
            "checks are silent most of the time."
        ),
    )
    if temp.active_rules:
        st.success(
            "Currently speaking: "
            + ", ".join(f"**{r.label}** ({r.verdict.lower()})" for r in temp.active_rules)
        )


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #


def _render_evidence(temp: MarketTemperature, horizon: int) -> None:
    st.subheader(f"When it looked like this before, what happened over the next {horizon // 12} year(s)?")
    st.caption(
        "Annualised total return from every month that fell in each band. This is "
        "the part of the page worth reading — the label at the top is only a "
        "summary of it."
    )

    rows = []
    for record in temp.evidence:
        stats = record.forward.get(horizon)
        if not stats:
            continue
        rows.append(
            {
                "Band": record.band_label,
                "Months seen": record.months_observed,
                "Independent windows": f"{record.independent_windows:.1f}",
                "Median return": stats["median"],
                "Average return": stats["mean"],
                "Worst": stats["worst"],
                "Best": stats["best"],
                "% positive": stats["pct_positive"],
                "% beat cash": stats["pct_beat_cash"],
            }
        )
    if not rows:
        st.info("Not enough forward history at this horizon yet.")
        return

    frame = pd.DataFrame(rows)
    frame["_order"] = frame["Band"].map({b: i for i, b in enumerate(_BAND_ORDER)})
    frame = frame.sort_values("_order").drop(columns="_order")

    def _highlight(row: pd.Series):
        active = row["Band"] == temp.band.label
        return [
            "background-color: rgba(120,120,120,.18); font-weight:600" if active else ""
        ] * len(row)

    st.dataframe(
        frame.style.apply(_highlight, axis=1).format(
            {
                "Median return": "{:+.1f}%",
                "Average return": "{:+.1f}%",
                "Worst": "{:+.1f}%",
                "Best": "{:+.1f}%",
                "% positive": "{:.0f}%",
                "% beat cash": "{:.0f}%",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        f"Your current band, **{temp.band.label}**, is highlighted. "
        "'Independent windows' matters more than 'months seen': overlapping "
        "windows share the same underlying market moves, so 52 months of history "
        "at a 5-year horizon is really about one independent observation."
    )

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=frame["Band"],
            y=frame["Median return"],
            marker_color=[
                TEMPERATURE_BANDS[k].colour
                for k in frame["Band"].str.lower()
                if k in TEMPERATURE_BANDS
            ],
            text=[f"{v:+.1f}%" for v in frame["Median return"]],
            textposition="outside",
            hovertemplate="%{x}<br>median %{y:+.1f}%/yr<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color="rgba(128,128,128,.5)")
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=30, b=10),
        yaxis_title=f"Median annualised return over next {horizon // 12}y (%)",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    worst = frame.loc[frame["Band"] == temp.band.label, "Worst"]
    if not worst.empty:
        st.warning(
            f"The worst outcome ever recorded from a **{temp.band.label}** reading "
            f"was **{worst.iloc[0]:+.1f}% a year** over the following "
            f"{horizon // 12} year(s). Size any decision so that outcome is survivable."
        )


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #


def _render_history(temp: MarketTemperature) -> None:
    st.subheader("The signal against the market")
    st.caption(
        "Shaded bands show what the signal said at the time, using only the data "
        "available at that point — no hindsight."
    )

    frame = temp.history
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.06,
        subplot_titles=("Index (total return, log scale)", "Composite score"),
    )

    spans = _contiguous_bands(frame["band_key"])
    for band_key, start, end in spans:
        if band_key == "neutral":
            continue
        fig.add_vrect(
            x0=start,
            x1=end,
            fillcolor=TEMPERATURE_BANDS[band_key].colour,
            opacity=0.16,
            line_width=0,
            row="all",
        )

    fig.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["total_return"],
            mode="lines",
            name="Total return",
            line=dict(width=1.8, color="#1f77b4"),
            hovertemplate="%{x|%b %Y}<br>%{y:.2f}x<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["score"],
            mode="lines",
            name="Score",
            line=dict(width=1.4, color="#6a1b9a"),
            fill="tozeroy",
            fillcolor="rgba(106,27,154,.18)",
            hovertemplate="%{x|%b %Y}<br>score %{y:+.3f}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.update_yaxes(type="log", row=1, col=1)
    fig.update_layout(
        height=560,
        margin=dict(l=10, r=10, t=48, b=10),
        showlegend=False,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    legend = " ".join(
        f"<span style='background:{TEMPERATURE_BANDS[k].colour}2e;"
        f"border-left:3px solid {TEMPERATURE_BANDS[k].colour};"
        f"padding:.15rem .5rem;margin-right:.4rem;border-radius:.25rem;'>"
        f"{TEMPERATURE_BANDS[k].label}</span>"
        for k in ("cold", "cool", "warm", "hot")
    )
    st.markdown(
        legend + "<span style='opacity:.6;margin-left:.4rem;'>unshaded = neutral</span>",
        unsafe_allow_html=True,
    )

    counts = frame["band_label"].value_counts()
    summary = pd.DataFrame(
        {
            "Band": [b for b in _BAND_ORDER if b in counts.index],
            "Months": [int(counts[b]) for b in _BAND_ORDER if b in counts.index],
        }
    )
    summary["Share of history"] = (
        summary["Months"] / summary["Months"].sum() * 100
    ).map("{:.0f}%".format)
    st.dataframe(summary, use_container_width=True, hide_index=True)


def _contiguous_bands(series: pd.Series) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    """Collapse a per-month band series into contiguous runs for shading."""
    spans: list[tuple[str, pd.Timestamp, pd.Timestamp]] = []
    if series.empty:
        return spans
    current = series.iloc[0]
    start = series.index[0]
    previous = series.index[0]
    for timestamp, value in series.items():
        if value != current:
            spans.append((current, start, previous))
            current, start = value, timestamp
        previous = timestamp
    spans.append((current, start, previous))
    return spans


# --------------------------------------------------------------------------- #
# Trust
# --------------------------------------------------------------------------- #


def _render_trust(temp: MarketTemperature) -> None:
    st.subheader("What this is, and what it is not")
    st.markdown(
        "This module is a rewritten, bug-fixed version of a contrarian allocation "
        "framework. It was tested properly before being put on screen, and it "
        "**failed as a trading strategy**. It is published here as a research "
        "read only. The full write-up is in `research/market_temperature/VALIDATION.md`."
    )

    cols = st.columns(3)
    cols[0].metric("Edge vs a fixed allocation, SENSEX", "+0.44%/yr", "passed, p=0.013")
    cols[1].metric("NIFTY", "-0.22%/yr", "failed, p=0.64", delta_color="inverse")
    cols[2].metric("NASDAQ", "-0.80%/yr", "failed, p=0.20", delta_color="inverse")
    st.caption(
        "Out-of-sample, after costs and an allowance for capital-gains tax, "
        "measured against simply holding a fixed stock/cash mix at the same "
        "average weight. An edge that appears in one market and reverses in "
        "another is not something to trade. Reproduce with "
        "`python -m research.market_temperature.validate`."
    )

    if temp.warnings:
        st.markdown("**Caveats for this specific reading**")
        for warning in temp.warnings:
            st.warning(warning)

    with st.expander("Known limitations, in full"):
        st.markdown(
            "- **Three of the seven checks have never fired.** The 12-year and "
            "8-year stagnation rules and the parabolic-move rule have not "
            "triggered once in the available history. They are kept for "
            "transparency, but the working content is the 5-year, 10-year and "
            "drawdown checks.\n"
            "- **Dividends are assumed, not measured.** Index-level payout history "
            "is not available free, so a constant yield is accrued instead. This "
            "matters most for the long-horizon 'went nowhere' rules.\n"
            "- **Overlapping windows overstate the sample.** Monthly readings at a "
            "five-year horizon share almost all their underlying data. The "
            "'independent windows' column is the honest count.\n"
            "- **Thresholds were not tuned**, deliberately. Fitting them to this "
            "data would produce better-looking history and worse future results.\n"
            "- **The framework's valuation half is missing.** The original also "
            "used index P/E, P/B and bond-yield comparisons. Reliable point-in-time "
            "history for those is not freely available, and NSE changed its P/E "
            "methodology in 2021, breaking comparability across that date.\n"
            "- **It says nothing about individual stocks**, sectors, or your own "
            "portfolio. It describes one index."
        )

    st.info(
        "Rule of thumb: if this page and your financial plan disagree, follow the "
        "plan. The signal is worth a nudge in deployment pace, nothing more."
    )
