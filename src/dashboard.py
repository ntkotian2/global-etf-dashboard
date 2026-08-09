"""Streamlit dashboard for comparing India sector ETF performance.

Usage:
    streamlit run src/dashboard.py
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from db import get_connection

st.set_page_config(page_title="India Sector ETF Tracker", layout="wide")

SOCIAL_TRENDING_CONFIG = (
    Path(__file__).resolve().parent.parent / "config" / "social_trending_etfs.yaml"
)
TAXONOMY_CONFIG = Path(__file__).resolve().parent.parent / "config" / "etf_taxonomy.yaml"

# Sunburst ring colors: neutral for asset-class/category rings, status colors
# (green/gray) on the leaf ring to flag what's actionable in this tracker.
TAXONOMY_L1_COLOR = "#f0efec"
TAXONOMY_L2_COLOR = "#dedcd3"
TAXONOMY_TRACKED_COLOR = "#0ca30c"
TAXONOMY_UNTRACKED_COLOR = "#a9a79c"

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


def load_taxonomy() -> list[dict]:
    with open(TAXONOMY_CONFIG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_taxonomy_sunburst(taxonomy: list[dict], tracked_sectors: set[str]) -> go.Figure:
    """Asset Class -> Category -> Sector/Theme sunburst. Node ids are
    '/'-joined paths (e.g. 'Equity/Sectoral/Banking'), carried in customdata
    so clicks can be resolved unambiguously even where labels repeat."""
    ids, labels, parents, values, colors, status = [], [], [], [], [], []
    seen = set()

    for row in taxonomy:
        l1, l2, leaf = row["level1"], row["level2"], row["leaf"]
        l1_id, l2_id, leaf_id = l1, f"{l1}/{l2}", f"{l1}/{l2}/{leaf}"

        if l1_id not in seen:
            seen.add(l1_id)
            ids.append(l1_id)
            labels.append(l1)
            parents.append("")
            values.append(0)
            colors.append(TAXONOMY_L1_COLOR)
            status.append("")
        if l2_id not in seen:
            seen.add(l2_id)
            ids.append(l2_id)
            labels.append(l2)
            parents.append(l1_id)
            values.append(0)
            colors.append(TAXONOMY_L2_COLOR)
            status.append("")

        tracked_sector = row.get("tracked_sector")
        is_tracked = bool(tracked_sector) and tracked_sector in tracked_sectors
        ids.append(leaf_id)
        labels.append(leaf)
        parents.append(l2_id)
        values.append(1)
        colors.append(TAXONOMY_TRACKED_COLOR if is_tracked else TAXONOMY_UNTRACKED_COLOR)
        status.append("Tracked — click to filter tables below" if is_tracked else "Not tracked yet")

    fig = go.Figure(
        go.Sunburst(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="remainder",
            marker=dict(colors=colors, line=dict(color="#fcfcfb", width=2)),
            customdata=list(zip(ids, status)),
            hovertemplate="<b>%{label}</b><br>%{customdata[1]}<extra></extra>",
            maxdepth=3,
        )
    )
    fig.update_layout(margin=dict(t=10, l=10, r=10, b=10), height=650)
    return fig


def taxonomy_sector_lookup(
    taxonomy: list[dict],
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
    """Maps every node id (leaf, category, or asset-class) to the list of
    tracked sectors under it, so a click at any level can filter the tables."""
    leaf_map: dict[str, list[str]] = {}
    l2_map: dict[str, list[str]] = {}
    l1_map: dict[str, list[str]] = {}
    for row in taxonomy:
        l1, l2, leaf = row["level1"], row["level2"], row["leaf"]
        ts = row.get("tracked_sector")
        leaf_map[f"{l1}/{l2}/{leaf}"] = [ts] if ts else []
        l2_map.setdefault(f"{l1}/{l2}", [])
        l1_map.setdefault(l1, [])
        if ts:
            l2_map[f"{l1}/{l2}"].append(ts)
            l1_map[l1].append(ts)
    return leaf_map, l2_map, l1_map


st.title("India Sector ETF Tracker")

df = load_data()

if df.empty:
    st.warning("No data yet. Run `python src/fetch.py` first to populate the database.")
    st.stop()

sectors = sorted(df["sector"].unique())

st.subheader("NSE India ETF universe — top-down classification")
st.caption(
    "🟢 Tracked in this dashboard (click to filter the tables below) · "
    "⚪ Not tracked yet. Click any ring — asset class, category, or "
    "sector — to drill down."
)

taxonomy = load_taxonomy()
taxonomy_fig = build_taxonomy_sunburst(taxonomy, set(sectors))
taxonomy_event = st.plotly_chart(
    taxonomy_fig, width='stretch', on_select="rerun", key="taxonomy_chart"
)

leaf_sectors, l2_sectors, l1_sectors = taxonomy_sector_lookup(taxonomy)
clicked_points = taxonomy_event["selection"]["points"] if taxonomy_event else []
if clicked_points:
    clicked_id, clicked_label = clicked_points[0]["customdata"][0], clicked_points[0]["label"]
    if clicked_id != st.session_state.get("_last_taxonomy_click"):
        st.session_state["_last_taxonomy_click"] = clicked_id
        matched = leaf_sectors.get(clicked_id) or l2_sectors.get(clicked_id) or l1_sectors.get(clicked_id) or []
        if matched:
            st.session_state["sector_filter"] = matched
        else:
            st.info(
                f'No ETFs tracked yet under "{clicked_label}" — add one to '
                f"config/etfs.yaml or config/social_trending_etfs.yaml to start tracking it."
            )

selected_sectors = st.multiselect("Sectors", sectors, default=sectors, key="sector_filter")

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
st.dataframe(comparison_df, width='stretch', hide_index=True)

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
st.dataframe(trending_df, width='stretch', hide_index=True)

st.caption(f"Data through {df['date'].max().date()}")
