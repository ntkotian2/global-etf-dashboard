"""Shared helpers used by every market page (India, USA, Canada)."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from db import get_connection

PERIODS = {
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 182,
    "1Y": 365,
    "3Y": 365 * 3,
}

COMPARISON_PERIODS = {"3M Return %": 90, "6M Return %": 182, "1Y Return %": 365}


@st.cache_data(ttl=3600)
def load_data(market: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT p.ticker, e.name, e.sector, p.date, p.close
        FROM prices p JOIN etfs e ON e.ticker = p.ticker
        WHERE e.market = ?
        ORDER BY p.date
        """,
        conn,
        params=(market,),
        parse_dates=["date"],
    )
    conn.close()
    return df


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


def render_sector_performance_chart(df: pd.DataFrame, selected_sectors: list[str], period_key: str) -> None:
    period_label = st.radio("Period", list(PERIODS.keys()), index=2, horizontal=True, key=period_key)
    cutoff = pd.Timestamp(date.today() - timedelta(days=PERIODS[period_label]))
    filtered = df[df["sector"].isin(selected_sectors) & (df["date"] >= cutoff)]

    st.subheader("Sector performance (normalized to 100 at period start)")
    pivot = filtered.pivot_table(index="date", columns="name", values="close")
    normalized = pivot / pivot.bfill().iloc[0] * 100
    st.line_chart(normalized)


def render_returns_comparison_table(df: pd.DataFrame, selected_sectors: list[str]) -> None:
    st.subheader("Returns comparison")
    full_pivot = df[df["sector"].isin(selected_sectors)].pivot_table(
        index="date", columns="name", values="close"
    )

    comparison = []
    for name, series in full_pivot.items():
        sector = df.loc[df["name"] == name, "sector"].iloc[0]
        row = {"ETF": name, "Sector": sector}
        for label, days in COMPARISON_PERIODS.items():
            ret = period_return(series, days)
            row[label] = round(ret, 2) if ret is not None else None
        comparison.append(row)

    comparison_df = pd.DataFrame(comparison).sort_values("1Y Return %", ascending=False)
    st.dataframe(comparison_df, width="stretch", hide_index=True)
