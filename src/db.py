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
