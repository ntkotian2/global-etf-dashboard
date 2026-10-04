"""SQLite schema and connection helper for the ETF database."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "etfs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS etfs (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'India'
);

CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT NOT NULL REFERENCES etfs(ticker),
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    PRIMARY KEY (ticker, date)
);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    # migration: `market` was added after the table already existed for some users
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(etfs)")}
    if "market" not in existing_cols:
        conn.execute("ALTER TABLE etfs ADD COLUMN market TEXT NOT NULL DEFAULT 'India'")
        conn.commit()
    return conn


PRICES_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "prices.csv"


def read_prices_csv(market: str | None = None) -> "pd.DataFrame":
    """Read the committed price-history snapshot (data/prices.csv, refreshed
    once daily by the GitHub Actions workflow) and join ETF metadata from
    config/*.yaml. Returns columns: ticker, name, sector, market,
    date (datetime), close -- the same shape the old SQLite queries
    produced. Returns an empty DataFrame with these columns when the
    snapshot is missing."""
    import pandas as pd

    from fetch import load_etf_config  # deferred: fetch imports db at module level

    cols = ["ticker", "name", "sector", "market", "date", "close"]
    if not PRICES_CSV_PATH.exists():
        return pd.DataFrame({c: [] for c in cols})
    prices = pd.read_csv(PRICES_CSV_PATH, parse_dates=["date"])
    meta = pd.DataFrame(load_etf_config(market))[["ticker", "name", "sector", "market"]]
    df = prices.merge(meta, on="ticker", how="inner")
    if market is not None:
        df = df[df["market"] == market]
    return df[cols].sort_values("date").reset_index(drop=True)
