"""Standalone read-only JSON API for the Multi-Market ETF Tracker.

Exists because Streamlit Community Cloud's gateway doesn't proxy custom
static file routes through to the dashboard app (see README.md's API
section for how that was discovered) -- this is a small, separately hosted
FastAPI service that computes the exact same payloads independently, using
its own SQLite database (self-refreshing via yfinance, same pattern as the
dashboard).

Data comes from data/prices.csv, committed to the repo once daily by the
GitHub Actions workflow (see README "Data pipeline"). Nothing fetches from
Yahoo at request time: datacenter IPs get rate-limited, which used to
return 500s on every endpoint.

Run locally:
    uvicorn main:app --reload --port 8000
"""

import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from api_data import build_market_api_payload, market_slug  # noqa: E402
from db import read_prices_csv  # noqa: E402

CONFIG_DIR = REPO_ROOT / "config"

MARKETS: dict[str, Path] = {
    "India": CONFIG_DIR / "social_trending_etfs.yaml",
    "USA": CONFIG_DIR / "social_trending_etfs_usa.yaml",
    "USA-AI": CONFIG_DIR / "social_trending_etfs_usa_ai.yaml",
    "Canada": CONFIG_DIR / "social_trending_etfs_canada.yaml",
}

CACHE_TTL_SECONDS = 3600
_cache: dict[str, tuple[float, dict]] = {}

app = FastAPI(
    title="Multi-Market ETF Tracker API",
    description="Read-only, unauthenticated JSON snapshot of "
    "https://global-etf-database.streamlit.app/ -- free to use, no API key required.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _load_market_df(market: str):
    # $0 pipeline: read the daily-committed snapshot -- no yfinance here.
    return read_prices_csv(market)


def _get_market_payload(market: str) -> dict:
    now = time.time()
    cached = _cache.get(market)
    if cached is not None and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    df = _load_market_df(market)
    if df.empty:
        raise HTTPException(status_code=503, detail=f"No data yet for {market}, try again shortly")

    payload = build_market_api_payload(market, df, MARKETS[market])
    _cache[market] = (now, payload)
    return payload


@app.get("/")
def index() -> dict:
    """Discovery doc: schema + endpoint list."""
    return {
        "name": "Multi-Market ETF Tracker API",
        "description": "Read-only, unauthenticated JSON snapshot of the data shown on "
        "https://global-etf-database.streamlit.app/",
        "markets": list(MARKETS.keys()),
        "endpoints": {
            "/{market-slug}": "One market's full snapshot (etfs, sectors, sector_rotation, trending). "
            "market-slug is the market name lowercased with spaces replaced by hyphens, "
            "e.g. /india, /usa, /usa-ai, /canada.",
            "/all": "All markets combined, under a top-level \"markets\" object keyed by market name.",
        },
        "caveats": [
            "Prices come from Yahoo Finance via yfinance -- free and unofficial, delayed, not for trading decisions.",
            "sector_rotation is a computed price-momentum proxy, not real fund-flow or social-media data.",
            "trending is a manually curated, periodically-refreshed list, not a live social-media feed.",
            "Price history refreshes once daily via a GitHub Actions workflow (free tier).",
            "Snapshots are cached for up to 1 hour per market.",
        ],
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/all")
def all_markets() -> dict:
    return {market: _get_market_payload(market) for market in MARKETS}


@app.get("/{slug}")
def one_market(slug: str) -> dict:
    for market in MARKETS:
        if market_slug(market) == slug.lower():
            return _get_market_payload(market)
    raise HTTPException(
        status_code=404,
        detail=f"Unknown market '{slug}'. Valid: {[market_slug(m) for m in MARKETS]}",
    )
