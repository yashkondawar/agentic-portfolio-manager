"""ER Reports — equity/sector research_reports list, most recent first, with
the underlying ingested agent output (final note / handoff) rendered inline.

final_note_path/handoff_path are currently always NULL in research_reports
(the note lives in the ingested outputs JSON, not a separate file) — this
page reports that honestly rather than presenting a broken link.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402

st.set_page_config(page_title="ER Reports — AI-Native Fund", layout="wide")

conn = shared.get_conn()

st.title("ER Reports")
st.caption("Equity + sector research_reports, most recent first.")

reports_df = shared.df_from_query(
    conn,
    "SELECT id, ticker, report_type, rating, as_of_date, status, final_note_path, handoff_path, created_at "
    "FROM research_reports WHERE report_type IN ('EQUITY','SECTOR') ORDER BY as_of_date DESC, id DESC LIMIT 100",
)

if reports_df.empty:
    st.info(
        "No EQUITY/SECTOR research_reports yet. Run "
        "`.venv\\Scripts\\python -m afund.orchestrator.run --job equity_research_kickoff` or "
        "`--job sector_research`, then ingest the agent output with `--ingest-output`."
    )
    st.stop()

st.dataframe(reports_df, use_container_width=True)

st.divider()
st.subheader("Report detail")

label_map = {
    row.id: f"#{row.id} · {row.report_type} · {row.ticker} · {row.as_of_date}"
    for row in reports_df.itertuples()
}
selected_id = st.selectbox("Select a report", list(label_map), format_func=lambda i: label_map[i])
selected_row = reports_df[reports_df["id"] == selected_id].iloc[0]

st.markdown(f"**{selected_row['ticker']}** — {selected_row['report_type']} — as of {selected_row['as_of_date']}")
col1, col2, col3 = st.columns(3)
col1.metric("Rating", selected_row["rating"] or "-")
col2.metric("Status", selected_row["status"] or "-")
col3.metric("Created", selected_row["created_at"] or "-")

if selected_row["final_note_path"]:
    st.markdown(f"[Final note]({selected_row['final_note_path']})")
else:
    st.caption("(no final_note_path recorded — see the ingested output below instead)")

if selected_row["handoff_path"]:
    st.markdown(f"[Handoff]({selected_row['handoff_path']})")
else:
    st.caption("(no handoff_path recorded)")

st.divider()

role = "sector_researcher" if selected_row["report_type"] == "SECTOR" else "research_head"
output = shared.latest_agent_output(conn, role)

if output is None:
    st.info(f"No ingested '{role}' output found in data/packets/ for this report.")
else:
    if selected_row["report_type"] == "SECTOR":
        st.markdown("**Competitive landscape**")
        st.write(output.get("competitive_landscape", "-"))
        st.markdown("**Value chain note**")
        st.write(output.get("value_chain_note", "-"))
        if output.get("comparison_table"):
            st.markdown("**Comparison table**")
            st.dataframe(output["comparison_table"], use_container_width=True)
        col_a, col_b = st.columns(2)
        col_a.markdown("**Top picks**")
        col_a.write(", ".join(output.get("top_picks", [])) or "-")
        col_b.markdown("**Avoid list**")
        col_b.write(", ".join(output.get("avoid_list", [])) or "-")
        if output.get("key_risks"):
            st.markdown("**Key risks**")
            for risk_item in output["key_risks"]:
                st.write(f"- {risk_item}")
    else:
        st.markdown("**Thesis**")
        st.write(output.get("thesis", "-"))
        if output.get("key_drivers"):
            st.markdown("**Key drivers**")
            for d in output["key_drivers"]:
                st.write(f"- {d}")
        if output.get("risks"):
            st.markdown("**Risks**")
            for r in output["risks"]:
                st.write(f"- {r}")
        if output.get("invalidation_condition"):
            st.caption(f"Invalidation: {output['invalidation_condition']}")

    if output.get("sources"):
        st.caption("Sources: " + "; ".join(output["sources"]))
