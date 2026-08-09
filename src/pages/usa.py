"""USA sector ETF tracker page."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    load_data,
    render_returns_comparison_table,
    render_sector_performance_chart,
    render_sector_rotation_table,
    render_taxonomy_chart,
    render_trending_table,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

st.title("USA Sector ETF Tracker")

df = load_data("USA")

if df.empty:
    st.warning("No data yet. Run `python src/fetch.py` first to populate the database.")
    st.stop()

sectors = sorted(df["sector"].unique())

render_taxonomy_chart(
    CONFIG_DIR / "etf_taxonomy_usa.yaml",
    df,
    chart_key="taxonomy_chart_usa",
    sector_filter_key="sector_filter_usa",
    subheader="USA ETF universe — top-down classification",
    missing_note="add one to config/etfs_usa.yaml to start tracking it.",
)

selected_sectors = st.multiselect("Sectors", sectors, default=sectors, key="sector_filter_usa")

render_sector_performance_chart(df, selected_sectors, period_key="period_usa")
render_returns_comparison_table(df, selected_sectors)
render_sector_rotation_table(df)
render_trending_table(CONFIG_DIR / "social_trending_etfs_usa.yaml", df)

st.caption(f"Data through {df['date'].max().date()}")
