"""Daily price refresh for the GitHub Actions workflow (also runnable locally).

Incrementally extends data/prices.csv (columns: ticker,date,close) using
yfinance, starting each ticker from the day after its latest date already in
the CSV. First run with no CSV present pulls full history. Ticker metadata
(name, sector, market) is NOT stored here -- it is joined from config/*.yaml
at read time (see src/db.py read_prices_csv).

Designed for CI: per-ticker retries with backoff, and a ticker that still
fails is skipped with a warning instead of killing the whole run.
"""

import sys
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from fetch import fetch_ticker, load_etf_config  # noqa: E402

CSV_PATH = REPO_ROOT / "data" / "prices.csv"
POLITE_DELAY_SECONDS = 1.0
MAX_ATTEMPTS = 3


def fetch_with_retry(ticker: str, start: str | None) -> list[tuple]:
    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fetch_ticker(ticker, start)
        except Exception as err:  # noqa: BLE001 - one bad ticker must not kill the run
            last_err = err
            print(f"  {ticker}: attempt {attempt}/{MAX_ATTEMPTS} failed ({err}), retrying...")
            time.sleep(2**attempt)
    print(f"  WARNING: {ticker}: giving up after {MAX_ATTEMPTS} attempts ({last_err})")
    return []


def main() -> None:
    existing = None
    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, parse_dates=["date"])
        print(f"Loaded {len(existing)} existing rows from {CSV_PATH}")

    last_date: dict[str, pd.Timestamp] = {}
    if existing is not None and not existing.empty:
        last_date = existing.groupby("ticker")["date"].max().to_dict()

    etfs = load_etf_config()
    print(f"{len(etfs)} tickers configured")

    new_rows: list[tuple] = []
    for i, etf in enumerate(etfs, start=1):
        ticker = etf["ticker"]
        start = None
        if ticker in last_date:
            start = (last_date[ticker] + timedelta(days=1)).strftime("%Y-%m-%d")
        rows = fetch_with_retry(ticker, start)
        new_rows.extend((t, d, c) for t, d, _o, _h, _l, c, _v in rows)
        print(f"[{i}/{len(etfs)}] {ticker}: {len(rows)} new rows (start={start or 'full history'})")
        time.sleep(POLITE_DELAY_SECONDS)

    fresh = pd.DataFrame(new_rows, columns=["ticker", "date", "close"])
    if existing is not None and not existing.empty:
        combined = pd.concat(
            [existing[["ticker", "date", "close"]], fresh], ignore_index=True
        )
    else:
        combined = fresh
    combined["date"] = pd.to_datetime(combined["date"]).dt.strftime("%Y-%m-%d")
    combined = combined.drop_duplicates(subset=["ticker", "date"], keep="last")
    combined = combined.sort_values(["ticker", "date"]).reset_index(drop=True)

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(CSV_PATH, index=False)
    print(f"Wrote {len(combined)} rows to {CSV_PATH}")


if __name__ == "__main__":
    main()
