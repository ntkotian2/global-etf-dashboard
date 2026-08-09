"""Canada sector ETF tracker page."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import load_data, render_returns_comparison_table, render_sector_performance_chart

st.title("Canada Sector ETF Tracker")

df = load_data("Canada")

if df.empty:
    st.warning("No data yet. Run `python src/fetch.py` first to populate the database.")
    st.stop()

sectors = sorted(df["sector"].unique())
selected_sectors = st.multiselect("Sectors", sectors, default=sectors, key="sector_filter_canada")

render_sector_performance_chart(df, selected_sectors, period_key="period_canada")
render_returns_comparison_table(df, selected_sectors)

st.caption(f"Data through {df['date'].max().date()}")
