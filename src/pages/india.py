"""India sector ETF tracker page: taxonomy chart, sector performance,
returns comparison, and social-media-trending ETFs."""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    COMPARISON_PERIODS,
    load_data,
    period_return,
    render_returns_comparison_table,
    render_sector_performance_chart,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
SOCIAL_TRENDING_CONFIG = CONFIG_DIR / "social_trending_etfs.yaml"
TAXONOMY_CONFIG = CONFIG_DIR / "etf_taxonomy.yaml"

# Sunburst ring colors: neutral for asset-class/category rings; the leaf ring
# is a traffic light on 1-year return (green/orange/red), gray where no
# return data exists for that sector yet.
TAXONOMY_L1_COLOR = "#f0efec"
TAXONOMY_L2_COLOR = "#dedcd3"
TAXONOMY_GREEN = "#0ca30c"
TAXONOMY_ORANGE = "#fab219"
TAXONOMY_RED = "#d03b3b"
TAXONOMY_NO_DATA_COLOR = "#c3c2b7"
TAXONOMY_GREEN_THRESHOLD = 10.0
TAXONOMY_RED_THRESHOLD = -10.0


def load_taxonomy() -> list[dict]:
    with open(TAXONOMY_CONFIG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sector_1y_returns(df: pd.DataFrame) -> dict[str, float]:
    """Average 1-year return per sector, across every tracked ETF in it
    (unfiltered by the sector multiselect -- the sunburst always reflects
    true current performance)."""
    pivot = df.pivot_table(index="date", columns="name", values="close")
    name_to_sector = df.drop_duplicates("name").set_index("name")["sector"].to_dict()
    by_sector: dict[str, list[float]] = {}
    for name, series in pivot.items():
        ret = period_return(series, 365)
        if ret is not None:
            by_sector.setdefault(name_to_sector[name], []).append(ret)
    return {sector: sum(vals) / len(vals) for sector, vals in by_sector.items()}


def build_taxonomy_sunburst(taxonomy: list[dict], sector_returns: dict[str, float]) -> go.Figure:
    """Asset Class -> Category -> Sector/Theme sunburst, colored as a traffic
    light on 1-year return. Node ids are '/'-joined paths (e.g.
    'Equity/Sectoral/Banking')."""
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
        ret = sector_returns.get(tracked_sector) if tracked_sector else None
        if ret is None:
            color, status_text = TAXONOMY_NO_DATA_COLOR, "No return data yet"
        elif ret > TAXONOMY_GREEN_THRESHOLD:
            color, status_text = TAXONOMY_GREEN, f"Outperforming: {ret:+.1f}% (1Y)"
        elif ret < TAXONOMY_RED_THRESHOLD:
            color, status_text = TAXONOMY_RED, f"Underperforming: {ret:+.1f}% (1Y)"
        else:
            color, status_text = TAXONOMY_ORANGE, f"Sideways: {ret:+.1f}% (1Y)"

        ids.append(leaf_id)
        labels.append(leaf)
        parents.append(l2_id)
        values.append(1)
        colors.append(color)
        status.append(status_text)

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

df = load_data("India")

if df.empty:
    st.warning("No data yet. Run `python src/fetch.py` first to populate the database.")
    st.stop()

sectors = sorted(df["sector"].unique())

st.subheader("NSE India ETF universe — top-down classification")
st.caption(
    f"🟢 1Y return > {TAXONOMY_GREEN_THRESHOLD:.0f}% · 🟠 "
    f"{TAXONOMY_RED_THRESHOLD:.0f}% to {TAXONOMY_GREEN_THRESHOLD:.0f}% · 🔴 1Y return < "
    f"{TAXONOMY_RED_THRESHOLD:.0f}% · ⚪ no return data yet. Click any ring — "
    "asset class, category, or sector — to filter the tables below."
)

taxonomy = load_taxonomy()
taxonomy_fig = build_taxonomy_sunburst(taxonomy, sector_1y_returns(df))
taxonomy_event = st.plotly_chart(
    taxonomy_fig, width="stretch", on_select="rerun", key="taxonomy_chart"
)

leaf_sectors, l2_sectors, l1_sectors = taxonomy_sector_lookup(taxonomy)
clicked_points = taxonomy_event["selection"]["points"] if taxonomy_event else []
if clicked_points:
    point = clicked_points[0]
    clicked_label = point.get("label", "")
    # Sunburst point selections don't carry `customdata` through Streamlit's
    # event mapping (unlike scatter/bar) -- `id` is the native Plotly field
    # for id-based traces like this one, so use that; fall back to label for
    # the handful of nodes whose label repeats across levels (e.g. "ESG").
    clicked_id = point.get("id") or clicked_label
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

render_sector_performance_chart(df, selected_sectors, period_key="period_india")
render_returns_comparison_table(df, selected_sectors)

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
st.dataframe(trending_df, width="stretch", hide_index=True)

st.caption(f"Data through {df['date'].max().date()}")
