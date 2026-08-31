"""News — ported from dashboard/app.py's News section, with source/processed
filters."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import _shared as shared  # noqa: E402

st.set_page_config(page_title="News — AI-Native Fund", layout="wide")

conn = shared.get_conn()

st.title("News")

sources_df = shared.df_from_query(conn, "SELECT DISTINCT source FROM news_items WHERE source IS NOT NULL ORDER BY source")
source_options = ["(all)"] + (sources_df["source"].tolist() if not sources_df.empty else [])

col1, col2 = st.columns(2)
source_filter = col1.selectbox("Source", source_options)
processed_filter = col2.selectbox("Processed", ["(all)", "Yes", "No"])

query = (
    "SELECT event_scope, tag, impact, description, raw_title, event_date, source, url, processed "
    "FROM news_items WHERE 1=1"
)
params: list = []
if source_filter != "(all)":
    query += " AND source = ?"
    params.append(source_filter)
if processed_filter == "Yes":
    query += " AND processed = 1"
elif processed_filter == "No":
    query += " AND processed = 0"
query += " ORDER BY event_date DESC, id DESC LIMIT 50"

news_df = shared.df_from_query(conn, query, tuple(params))

if news_df.empty:
    st.info("No news items match the current filters.")
else:
    news_df["description"] = news_df["description"].fillna(news_df["raw_title"])
    display_df = news_df[["event_scope", "tag", "impact", "description", "event_date", "source", "url"]].rename(
        columns={"url": "link"}
    )
    st.dataframe(display_df, use_container_width=True)
