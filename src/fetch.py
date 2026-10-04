"""Fetch India/USA/Canada ETF prices via yfinance and upsert into SQLite.

Pulls the combined ticker list from every file in CONFIG_FILES, tagging each
with its market.

Usage:
    python src/fetch.py                 # incremental update for all configured ETFs
    python src/fetch.py --full          # re-download full history for all ETFs
"""

import argparse
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

from db import get_connection

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
# filename -> market. India's two files share the "India" market.
CONFIG_FILES = {
    "etfs.yaml": "India",
    "social_trending_etfs.yaml": "India",
    "etfs_usa.yaml": "USA",
    "social_trending_etfs_usa.yaml": "USA",
    "etfs_canada.yaml": "Canada",
    "social_trending_etfs_canada.yaml": "Canada",
    "etfs_usa_ai.yaml": "USA-AI",
    "social_trending_etfs_usa_ai.yaml": "USA-AI",
}


def load_etf_config(market: str | None = None) -> list[dict]:
    """All configured ETFs, or just one market's if `market` is given."""
    etfs: dict[str, dict] = {}
    for filename, file_market in CONFIG_FILES.items():
        if market is not None and file_market != market:
            continue
        with open(CONFIG_DIR / filename, "r", encoding="utf-8") as f:
            for etf in yaml.safe_load(f):
                etf["market"] = file_market
                etfs[etf["ticker"]] = etf  # de-dupe tickers shared across files
    return list(etfs.values())


def upsert_etfs(conn, etfs: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO etfs (ticker, name, sector, market) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(ticker) DO UPDATE SET name=excluded.name, sector=excluded.sector, "
        "market=excluded.market",
        [(e["ticker"], e["name"], e["sector"], e["market"]) for e in etfs],
    )
    conn.commit()


def last_date_for(conn, ticker: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(date) FROM prices WHERE ticker = ?", (ticker,)
    ).fetchone()
    return row[0] if row and row[0] else None


def fetch_ticker(ticker: str, start: str | None) -> "list[tuple]":
    hist = yf.Ticker(ticker).history(start=start, period=None if start else "max")
    rows = []
    for date, row in hist.iterrows():
        if pd.isna(row["Close"]):
            continue  # incomplete bar for a day still in progress
        rows.append(
            (
                ticker,
                date.strftime("%Y-%m-%d"),
                float(row["Open"]),
                float(row["High"]),
                float(row["Low"]),
                float(row["Close"]),
                int(row["Volume"]),
            )
        )
    return rows


def upsert_prices(conn, rows: "list[tuple]") -> None:
    if not rows:
        return
    conn.executemany(
        "INSERT INTO prices (ticker, date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(ticker, date) DO UPDATE SET "
        "open=excluded.open, high=excluded.high, low=excluded.low, "
        "close=excluded.close, volume=excluded.volume",
        rows,
    )
    conn.commit()


def export_prices_csv(conn) -> Path:
    """Write the committed price-history snapshot (data/prices.csv) that the
    Streamlit dashboard and the Render API read. Ticker metadata (name,
    sector, market) lives in config/*.yaml and is joined at read time (see
    db.read_prices_csv), so the CSV carries only ticker,date,close."""
    import pandas as pd

    df = pd.read_sql_query(
        "SELECT ticker, date, close FROM prices ORDER BY ticker, date", conn
    )
    out = Path(__file__).resolve().parent.parent / "data" / "prices.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Exported {len(df)} rows to {out}")
    return out



def fetch_market(market: str, full: bool = False) -> None:
    """Incrementally fetch just one market's tickers. Called by the dashboard
    itself (common.py) on each cache miss, so data self-refreshes on
    platforms with no external scheduler (e.g. Streamlit Community Cloud) --
    and self-heals with a full history pull if the database is empty/fresh
    (ephemeral cloud storage can reset between container restarts)."""
    etfs = load_etf_config(market)
    conn = get_connection()
    upsert_etfs(conn, etfs)
    for etf in etfs:
        ticker = etf["ticker"]
        start = None if full else last_date_for(conn, ticker)
        rows = fetch_ticker(ticker, start)
        upsert_prices(conn, rows)
    export_prices_csv(conn)
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full", action="store_true", help="re-download full history for all ETFs"
    )
    args = parser.parse_args()

    etfs = load_etf_config()
    conn = get_connection()
    upsert_etfs(conn, etfs)

    for etf in etfs:
        ticker = etf["ticker"]
        start = None if args.full else last_date_for(conn, ticker)
        rows = fetch_ticker(ticker, start)
        upsert_prices(conn, rows)
        print(f"{ticker}: {len(rows)} rows fetched (start={start or 'max history'})")

    export_prices_csv(conn)
    conn.close()


if __name__ == "__main__":
    main()
