"""Streamlit dashboard for comparing India sector ETF performance.

Usage:
    streamlit run src/dashboard.py
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from db import get_connection

st.set_page_config(page_title="India Sector ETF Tracker", layout="wide")

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

st.subheader("Returns over selected period")
returns = []
for name, series in pivot.items():
    series = series.dropna()
    if len(series) < 2:
        continue
    ret_pct = (series.iloc[-1] / series.iloc[0] - 1) * 100
    sector = df.loc[df["name"] == name, "sector"].iloc[0]
    returns.append({"ETF": name, "Sector": sector, "Return %": round(ret_pct, 2)})

returns_df = pd.DataFrame(returns).sort_values("Return %", ascending=False)
st.dataframe(returns_df, use_container_width=True, hide_index=True)

st.caption(f"Data through {df['date'].max().date()}")
