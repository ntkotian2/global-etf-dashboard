"""Pure data-computation helpers shared between the Streamlit dashboard
(common.py) and the standalone read-only API service (../api-server). No
Streamlit/plotly dependency here on purpose -- the API service imports this
module directly without needing the dashboard's UI stack installed."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml


def market_slug(market: str) -> str:
    return market.lower().replace(" ", "-")


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


def sector_momentum(df: pd.DataFrame, days: int) -> dict[str, float]:
    """Average N-day return per sector, across every tracked ETF in it."""
    pivot = df.pivot_table(index="date", columns="name", values="close")
    name_to_sector = df.drop_duplicates("name").set_index("name")["sector"].to_dict()
    by_sector: dict[str, list[float]] = {}
    for name, series in pivot.items():
        ret = period_return(series, days)
        if ret is not None:
            by_sector.setdefault(name_to_sector[name], []).append(ret)
    return {sector: sum(vals) / len(vals) for sector, vals in by_sector.items()}


def sector_1y_returns(df: pd.DataFrame) -> dict[str, float]:
    """Average 1-year return per sector -- used by the dashboard's taxonomy
    chart, which always reflects true current performance regardless of the
    sector filter."""
    return sector_momentum(df, 365)


def _round_or_none(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def build_market_api_payload(
    market: str, df: pd.DataFrame, trending_config_path: Path
) -> dict:
    """Everything the dashboard shows for one market, as JSON-safe plain
    data: latest prices/returns per ETF, per-sector average returns, the
    sector rotation signal, and the curated trending list."""
    latest = df.sort_values("date").groupby("ticker").tail(1).set_index("ticker")
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
