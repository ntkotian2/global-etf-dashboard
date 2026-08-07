"""Streamlit dashboard for comparing India sector ETF performance.

Usage:
    streamlit run src/dashboard.py
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from db import get_connection

st.set_page_config(page_title="India Sector ETF Tracker", layout="wide")

SOCIAL_TRENDING_CONFIG = (
    Path(__file__).resolve().parent.parent / "config" / "social_trending_etfs.yaml"
)

PERIODS = {
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 182,
    "1Y": 365,
    "3Y": 365 * 3,
}


@st.cache_data(ttl=3600)
def load_data() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT p.ticker, e.name, e.sector, p.date, p.close
        FROM prices p JOIN etfs e ON e.ticker = p.ticker
        ORDER BY p.date
        """,
        conn,
        parse_dates=["date"],
    )
    conn.close()
    return df


st.title("India Sector ETF Tracker")

df = load_data()

if df.empty:
    st.warning("No data yet. Run `python src/fetch.py` first to populate the database.")
    st.stop()

sectors = sorted(df["sector"].unique())
selected_sectors = st.multiselect("Sectors", sectors, default=sectors)

period_label = st.radio("Period", list(PERIODS.keys()), index=2, horizontal=True)
cutoff = pd.Timestamp(date.today() - timedelta(days=PERIODS[period_label]))

filtered = df[df["sector"].isin(selected_sectors) & (df["date"] >= cutoff)]

st.subheader("Sector performance (normalized to 100 at period start)")
pivot = filtered.pivot_table(index="date", columns="name", values="close")
normalized = pivot / pivot.bfill().iloc[0] * 100
st.line_chart(normalized)

st.subheader("Returns comparison")
COMPARISON_PERIODS = {"3M Return %": 90, "6M Return %": 182, "1Y Return %": 365}

full_pivot = df[df["sector"].isin(selected_sectors)].pivot_table(
    index="date", columns="name", values="close"
)


def period_return(series: pd.Series, days: int) -> float | None:
    series = series.dropna()
    if series.empty:
        return None
    cutoff_date = pd.Timestamp(date.today() - timedelta(days=days))
    eligible = series[series.index >= cutoff_date]
    if eligible.empty:
        return None
    start_price = eligible.iloc[0]
    if start_price == 0:
        return None
    return (series.iloc[-1] / start_price - 1) * 100


comparison = []
for name, series in full_pivot.items():
    sector = df.loc[df["name"] == name, "sector"].iloc[0]
    row = {"ETF": name, "Sector": sector}
    for label, days in COMPARISON_PERIODS.items():
        ret = period_return(series, days)
        row[label] = round(ret, 2) if ret is not None else None
    comparison.append(row)

comparison_df = pd.DataFrame(comparison).sort_values("1Y Return %", ascending=False)
st.dataframe(comparison_df, use_container_width=True, hide_index=True)

st.subheader("Top 10 trending on social media")
st.caption(
    "Curated snapshot of ETFs frequently discussed on YouTube/X/Facebook finance "
    "content, manually refreshed (see config/social_trending_etfs.yaml) — not a "
    "live social-media feed."
)

with open(SOCIAL_TRENDING_CONFIG, "r", encoding="utf-8") as f:
    trending_etfs = yaml.safe_load(f)

trending_names = [e["name"] for e in trending_etfs]
trending_pivot = df[df["name"].isin(trending_names)].pivot_table(
    index="date", columns="name", values="close"
)

trending_rows = []
for rank, etf in enumerate(trending_etfs, start=1):
    series = trending_pivot.get(etf["name"], pd.Series(dtype=float))
    row = {"Rank": rank, "ETF": etf["name"], "Sector": etf["sector"]}
    for label, days in COMPARISON_PERIODS.items():
        ret = period_return(series, days)
        row[label] = round(ret, 2) if ret is not None else None
    row["Why it's trending"] = etf["note"]
    trending_rows.append(row)

trending_df = pd.DataFrame(trending_rows)
st.dataframe(trending_df, use_container_width=True, hide_index=True)

st.caption(f"Data through {df['date'].max().date()}")
