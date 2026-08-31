"""AI-Native Fund — Home (entry point of the multipage Streamlit app).

Status board ALWAYS visible with zero generation runs: last run per job/
agent role (rolling 5-day window), staleness chips, and a "Refresh data"
button that shells out to `--job daily_data` (pure Python pipelines only —
no LLM ever fires from here). Run:

    .venv\\Scripts\\python -m streamlit run dashboard/Home.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parent
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402

st.set_page_config(page_title="AI-Native Fund — Home", layout="wide")

conn = shared.get_conn()
settings = shared.get_settings()

st.title("AI-Native Fund")
st.caption("Paper portfolio · manual-first · every capital decision halts at a human checkpoint.")


# ---------------------------------------------------------------------------
# Staleness chips + status board, fragment-scoped so the refresh button's
# rerun only re-executes this section (not the whole page).
# ---------------------------------------------------------------------------

@st.fragment
def _status_panels() -> None:
    chips = shared.staleness_check(conn)
    level_symbol = {"green": "🟢", "amber": "🟠", "red": "🔴", "unknown": "⚪"}

    st.subheader("Data freshness")
    chip_cols = st.columns(len(chips))
    for col, chip in zip(chip_cols, chips):
        symbol = level_symbol.get(chip["level"], "⚪")
        if chip["latest_date"] is None:
            detail = "no data yet"
        else:
            detail = f"{chip['latest_date']} ({chip['age_days']}d ago)"
        col.metric(f"{symbol} {chip['label']}", detail)

    red_chips = [c for c in chips if c["level"] == "red"]
    if red_chips:
        names = ", ".join(c["label"] for c in red_chips)
        st.warning(f"Data may be stale — refresh before generating ideas ({names}).")

    st.divider()

    # -----------------------------------------------------------------------
    # Refresh data / make system ready
    # -----------------------------------------------------------------------

    st.subheader("Refresh data")
    st.caption(
        "Runs `--job daily_data` (universe, prices, AMFI NAVs, index P/E, India VIX, "
        "FII/DII, news RSS, NAV mark-to-market) — pure Python, no LLM involved."
    )

    if st.button("Refresh data / make system ready", type="primary"):
        log_lines: list[str] = []
        with st.status("Running daily_data job...", expanded=True) as status:
            log_box = st.empty()

            def _sink(line: str) -> None:
                log_lines.append(line)
                log_box.code("\n".join(log_lines[-200:]), language="text")

            exit_code = shared.run_job_streaming("daily_data", line_sink=_sink)
            if exit_code == 0:
                status.update(label="daily_data job finished", state="complete")
            else:
                status.update(label=f"daily_data job exited with code {exit_code}", state="error")

        # Chips/status board must re-read the DB after the job — a plain
        # st.rerun() here would only rerun this fragment, which is exactly
        # what we want (chips + status board both live in this fragment).
        st.rerun()

    st.divider()

    # -----------------------------------------------------------------------
    # Status board: job_runs + agent_runs, rolling 5-day window
    # -----------------------------------------------------------------------

    st.subheader(f"Status board (last {shared.ROLLING_WINDOW_DAYS} days)")

    col_jobs, col_agents = st.columns(2)

    with col_jobs:
        st.markdown("**Jobs** (`job_runs`)")
        jobs = shared.job_runs_rolling(conn)
        if not jobs["recent"]:
            st.info("No job runs in the rolling window yet.")
        else:
            for j in jobs["recent"]:
                badge = "✅" if j["status"] == "SUCCESS" else ("❌" if j["status"] == "FAILED" else "•")
                st.write(f"{badge} **{j['job_name']}** — {j['status']} — last: {j['started_at']}")
        if jobs["older_count"]:
            st.caption(f"{jobs['older_count']} older run(s) not shown.")

    with col_agents:
        st.markdown("**Agent roles** (`agent_runs`)")
        agents = shared.agent_runs_rolling(conn)
        if not agents["recent"]:
            st.info("No agent runs in the rolling window yet.")
        else:
            for a in agents["recent"]:
                badge = "✅" if a["status"] == "COMPLETED" else ("🕓" if a["status"] == "PREPARED" else ("❌" if a["status"] == "FAILED" else "•"))
                st.write(f"{badge} **{a['role']}** — {a['status']} — last: {a['started_at']}")
        if agents["older_count"]:
            st.caption(f"{agents['older_count']} older run(s) not shown.")


_status_panels()

st.divider()
st.caption(
    "Use the sidebar to navigate: Positions, Risk, Macro/Micro KPI screens, Cycle Wheel, "
    "Ideas (click-gated generation), ER Reports, Buy-Side, News, Ops, Decisions & Theses."
)
