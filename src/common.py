"""Shared helpers used by every market page (India, USA, Canada)."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from db import get_connection

# Streamlit serves ./static/ (relative to the running app file, src/app.py)
# at the public path /app/static/ -- see .streamlit/config.toml
# (enableStaticServing) and README.md's API section.
STATIC_API_DIR = Path(__file__).resolve().parent / "static" / "api"

PERIODS = {
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 182,
    "1Y": 365,
    "3Y": 365 * 3,
}

COMPARISON_PERIODS = {"3M Return %": 90, "6M Return %": 182, "1Y Return %": 365}

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


@st.cache_data(ttl=3600)
def load_data(market: str, trending_config_path: Path | None = None) -> pd.DataFrame:
    """Self-refreshing: fetches this market's latest prices before reading,
    so the app stays current without an external scheduler (e.g. on
    Streamlit Community Cloud, which has no cron/Task Scheduler). Cheap on a
    warm database (incremental fetch), self-heals with a full history pull
    if the database is empty (ephemeral cloud storage can reset between
    container restarts) -- that first load can take up to a minute.

    Also re-exports this market's JSON API snapshot (see export_market_api)
    on the same cache cycle, so /app/static/api/ stays in sync with what the
    dashboard shows without a separate write path."""
    from fetch import fetch_market

    with st.spinner(f"Fetching latest {market} prices…"):
        fetch_market(market)

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

    if trending_config_path is not None:
        export_market_api(market, df, trending_config_path)

    return df


def broker_ticker(ticker: str) -> str:
    """Strip the yfinance exchange suffix (.NS, .TO) so the symbol matches
    what you'd actually type into a broker's search box."""
    return ticker.split(".")[0]


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
        etf_row = df.loc[df["name"] == name].iloc[0]
        row = {"Ticker": broker_ticker(etf_row["ticker"]), "ETF": name, "Sector": etf_row["sector"]}
        for label, days in COMPARISON_PERIODS.items():
            ret = period_return(series, days)
            row[label] = round(ret, 2) if ret is not None else None
        comparison.append(row)

    comparison_df = pd.DataFrame(comparison).sort_values("1Y Return %", ascending=False)
    st.dataframe(comparison_df, width="stretch", hide_index=True)


def render_sector_rotation_table(df: pd.DataFrame) -> None:
    """Top 5 rows of the biggest momentum decelerators paired with the
    biggest accelerators -- a computed price-momentum proxy for sector
    rotation, NOT real institutional fund-flow or social-media data (no free
    source for either exists)."""
    st.subheader("Top 5 sector rotation (momentum proxy)")
    st.caption(
        "Computed signal, not real fund-flow or social-media data — ranks sectors by "
        "how much their 1-month return diverges from their 3-month trend, then pairs "
        "the biggest decelerators with the biggest accelerators to suggest where "
        "capital may be rotating. Treat as a starting point for research, not a signal."
    )

    mom_1m = sector_momentum(df, 30)
    mom_3m = sector_momentum(df, 90)
    shift = {s: mom_1m[s] - mom_3m[s] for s in mom_1m if s in mom_3m}

    n_pairs = min(5, len(shift) // 2)
    if n_pairs < 1:
        st.info("Not enough sectors with data yet to compute rotation.")
        return

    sector_to_ticker = df.drop_duplicates("sector").set_index("sector")["ticker"].to_dict()
    ranked = sorted(shift.items(), key=lambda kv: kv[1])  # ascending: biggest decelerators first
    losers = ranked[:n_pairs]
    gainers = list(reversed(ranked[-n_pairs:]))  # biggest accelerator first

    rows = []
    for i in range(n_pairs):
        from_sector, from_shift = losers[i]
        to_sector, to_shift = gainers[i]
        rows.append(
            {
                "Rank": i + 1,
                "From Sector": from_sector,
                "From Ticker": broker_ticker(sector_to_ticker[from_sector]),
                "From 1M-3M Shift %": round(from_shift, 2),
                "To Sector": to_sector,
                "To Ticker": broker_ticker(sector_to_ticker[to_sector]),
                "To 1M-3M Shift %": round(to_shift, 2),
            }
        )

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# --- Taxonomy chart (Asset Class -> Category -> Sector/Theme) ---


def load_taxonomy(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sector_momentum(df: pd.DataFrame, days: int) -> dict[str, float]:
    """Average N-day return per sector, across every tracked ETF in it
    (unfiltered by the sector multiselect)."""
    pivot = df.pivot_table(index="date", columns="name", values="close")
    name_to_sector = df.drop_duplicates("name").set_index("name")["sector"].to_dict()
    by_sector: dict[str, list[float]] = {}
    for name, series in pivot.items():
        ret = period_return(series, days)
        if ret is not None:
            by_sector.setdefault(name_to_sector[name], []).append(ret)
    return {sector: sum(vals) / len(vals) for sector, vals in by_sector.items()}


def sector_1y_returns(df: pd.DataFrame) -> dict[str, float]:
    """Average 1-year return per sector -- used by the taxonomy chart, which
    always reflects true current performance regardless of the sector filter."""
    return sector_momentum(df, 365)


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


def render_taxonomy_chart(
    taxonomy_path: Path,
    df: pd.DataFrame,
    chart_key: str,
    sector_filter_key: str,
    subheader: str,
    missing_note: str,
) -> None:
    """Renders the sunburst + click-to-filter handling. A click writes the
    matched sectors into st.session_state[sector_filter_key] -- render this
    BEFORE the page's sector multiselect (same key) so the override applies."""
    st.subheader(subheader)
    st.caption(
        f"🟢 1Y return > {TAXONOMY_GREEN_THRESHOLD:.0f}% · 🟠 "
        f"{TAXONOMY_RED_THRESHOLD:.0f}% to {TAXONOMY_GREEN_THRESHOLD:.0f}% · 🔴 1Y return < "
        f"{TAXONOMY_RED_THRESHOLD:.0f}% · ⚪ no return data yet. Click any ring — "
        "asset class, category, or sector — to filter the tables below."
    )

    taxonomy = load_taxonomy(taxonomy_path)
    fig = build_taxonomy_sunburst(taxonomy, sector_1y_returns(df))
    event = st.plotly_chart(fig, width="stretch", on_select="rerun", key=chart_key)

    leaf_sectors, l2_sectors, l1_sectors = taxonomy_sector_lookup(taxonomy)
    clicked_points = event["selection"]["points"] if event else []
    if clicked_points:
        point = clicked_points[0]
        clicked_label = point.get("label", "")
        # Sunburst point selections don't carry `customdata` through Streamlit's
        # event mapping (unlike scatter/bar) -- `id` is the native Plotly field
        # for id-based traces like this one, so use that; fall back to label
        # for the handful of nodes whose label repeats across levels.
        clicked_id = point.get("id") or clicked_label
        last_click_key = f"_last_taxonomy_click_{chart_key}"
        if clicked_id != st.session_state.get(last_click_key):
            st.session_state[last_click_key] = clicked_id
            matched = (
                leaf_sectors.get(clicked_id)
                or l2_sectors.get(clicked_id)
                or l1_sectors.get(clicked_id)
                or []
            )
            if matched:
                st.session_state[sector_filter_key] = matched
            else:
                st.info(f'No ETFs tracked yet under "{clicked_label}" — {missing_note}')


def render_trending_table(trending_config_path: Path, df: pd.DataFrame) -> None:
    st.subheader("Top 10 trending on social media")
    st.caption(
        "Curated snapshot of ETFs frequently discussed on YouTube/X/Facebook finance "
        f"content, manually refreshed (see {trending_config_path.relative_to(trending_config_path.parent.parent)}) "
        "— not a live social-media feed."
    )

    with open(trending_config_path, "r", encoding="utf-8") as f:
        trending_etfs = yaml.safe_load(f)

    trending_names = [e["name"] for e in trending_etfs]
    trending_pivot = df[df["name"].isin(trending_names)].pivot_table(
        index="date", columns="name", values="close"
    )

    rows = []
    for rank, etf in enumerate(trending_etfs, start=1):
        series = trending_pivot.get(etf["name"], pd.Series(dtype=float))
        row = {
            "Rank": rank,
            "Ticker": broker_ticker(etf["ticker"]),
            "ETF": etf["name"],
            "Sector": etf["sector"],
        }
        for label, days in COMPARISON_PERIODS.items():
            ret = period_return(series, days)
            row[label] = round(ret, 2) if ret is not None else None
        row["Why it's trending"] = etf["note"]
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# --- JSON API export (read-only snapshot for external/AI consumers) ---


def market_slug(market: str) -> str:
    return market.lower().replace(" ", "-")


def build_market_api_payload(
    market: str, df: pd.DataFrame, trending_config_path: Path
) -> dict:
    """Everything the dashboard shows for one market, as JSON-safe plain
    data: latest prices/returns per ETF, per-sector average returns, the
    sector rotation signal, and the curated trending list."""
    latest = df.sort_values("date").groupby("ticker").tail(1).set_index("ticker")
    name_to_ticker = df.drop_duplicates("name").set_index("name")["ticker"].to_dict()
    pivot = df.pivot_table(index="date", columns="name", values="close")

    etfs = []
    for ticker, row in latest.iterrows():
        series = pivot[row["name"]] if row["name"] in pivot else pd.Series(dtype=float)
        etfs.append(
            {
                "ticker": ticker,
                "broker_ticker": broker_ticker(ticker),
                "name": row["name"],
                "sector": row["sector"],
                "latest_price": round(float(row["close"]), 4),
                "latest_date": row["date"].strftime("%Y-%m-%d"),
                "return_3m_pct": _round_or_none(period_return(series, 90)),
                "return_6m_pct": _round_or_none(period_return(series, 182)),
                "return_1y_pct": _round_or_none(period_return(series, 365)),
            }
        )
    etfs.sort(key=lambda e: e["ticker"])

    sectors = []
    mom_1m, mom_3m, mom_1y = (
        sector_momentum(df, 30),
        sector_momentum(df, 90),
        sector_momentum(df, 365),
    )
    for sector in sorted(df["sector"].unique()):
        sectors.append(
            {
                "sector": sector,
                "avg_return_1m_pct": _round_or_none(mom_1m.get(sector)),
                "avg_return_3m_pct": _round_or_none(mom_3m.get(sector)),
                "avg_return_1y_pct": _round_or_none(mom_1y.get(sector)),
            }
        )

    sector_rotation = []
    shift = {s: mom_1m[s] - mom_3m[s] for s in mom_1m if s in mom_3m}
    n_pairs = min(5, len(shift) // 2)
    if n_pairs >= 1:
        sector_to_ticker = df.drop_duplicates("sector").set_index("sector")["ticker"].to_dict()
        ranked = sorted(shift.items(), key=lambda kv: kv[1])
        losers, gainers = ranked[:n_pairs], list(reversed(ranked[-n_pairs:]))
        for i in range(n_pairs):
            from_sector, from_shift = losers[i]
            to_sector, to_shift = gainers[i]
            sector_rotation.append(
                {
                    "rank": i + 1,
                    "from_sector": from_sector,
                    "from_ticker": broker_ticker(sector_to_ticker[from_sector]),
                    "from_1m_3m_shift_pct": round(from_shift, 2),
                    "to_sector": to_sector,
                    "to_ticker": broker_ticker(sector_to_ticker[to_sector]),
                    "to_1m_3m_shift_pct": round(to_shift, 2),
                }
            )

    with open(trending_config_path, "r", encoding="utf-8") as f:
        trending_etfs = yaml.safe_load(f)
    trending = []
    for rank, etf in enumerate(trending_etfs, start=1):
        series = pivot.get(etf["name"], pd.Series(dtype=float))
        trending.append(
            {
                "rank": rank,
                "ticker": etf["ticker"],
                "broker_ticker": broker_ticker(etf["ticker"]),
                "name": etf["name"],
                "sector": etf["sector"],
                "return_3m_pct": _round_or_none(period_return(series, 90)),
                "return_6m_pct": _round_or_none(period_return(series, 182)),
                "return_1y_pct": _round_or_none(period_return(series, 365)),
                "note": etf["note"],
            }
        )

    return {
        "market": market,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_through": df["date"].max().strftime("%Y-%m-%d"),
        "etfs": etfs,
        "sectors": sectors,
        "sector_rotation": sector_rotation,
        "trending": trending,
    }


def _round_or_none(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def export_market_api(market: str, df: pd.DataFrame, trending_config_path: Path) -> None:
    """Writes /app/static/api/{market-slug}.json and folds this market's
    slice into the combined /app/static/api/all.json. Best-effort: on
    Streamlit Community Cloud, runtime-written files aren't guaranteed to
    persist across container restarts, but this re-runs on every cache
    refresh (see load_data), so it self-heals the first time each market
    page is visited after a restart -- same pattern as the SQLite database."""
    STATIC_API_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_market_api_payload(market, df, trending_config_path)

    slug = market_slug(market)
    with open(STATIC_API_DIR / f"{slug}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    all_path = STATIC_API_DIR / "all.json"
    combined = {"markets": {}}
    if all_path.exists():
        try:
            with open(all_path, "r", encoding="utf-8") as f:
                combined = json.load(f)
        except (json.JSONDecodeError, OSError):
            combined = {"markets": {}}
    combined.setdefault("markets", {})[market] = payload
    combined["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(all_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)
