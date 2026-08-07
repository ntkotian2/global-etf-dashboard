"""Fetch India sector ETF prices via yfinance and upsert into SQLite.

Usage:
    python src/fetch.py                 # update all ETFs in config/etfs.yaml
    python src/fetch.py --full          # re-download full history for all ETFs
"""

import argparse
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

from db import get_connection

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "etfs.yaml"


def load_etf_config() -> list[dict]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def upsert_etfs(conn, etfs: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO etfs (ticker, name, sector) VALUES (?, ?, ?) "
        "ON CONFLICT(ticker) DO UPDATE SET name=excluded.name, sector=excluded.sector",
        [(e["ticker"], e["name"], e["sector"]) for e in etfs],
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

    conn.close()


if __name__ == "__main__":
    main()
