"""MCP server exposing the Multi-Market ETF Tracker's read-only JSON API as
tools, so Claude (or any other MCP client) can query live ETF data.

Talks to the standalone api-server service over plain HTTP (see
../api-server) -- NOT the Streamlit dashboard's static file route, which
doesn't work on Streamlit Community Cloud (see README.md's API section).
Set ETF_API_BASE_URL to wherever you deployed api-server; defaults to
localhost for local development.

Run directly for local testing:
    python server.py
Normally launched by an MCP client (Claude Desktop, Claude Code) via stdio.
"""

import os

import httpx
from mcp.server.mcpserver import MCPServer

BASE_URL = os.environ.get("ETF_API_BASE_URL", "http://localhost:8000").rstrip("/")
MARKETS = ["India", "USA", "USA-AI", "Canada"]

mcp = MCPServer("etf-tracker")


def _slug(market: str) -> str:
    return market.lower().replace(" ", "-")


def _fetch(path: str) -> dict:
    resp = httpx.get(f"{BASE_URL}/{path}", timeout=15)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def list_markets() -> list[str]:
    """List the markets tracked by the ETF dashboard."""
    return MARKETS


@mcp.tool()
def get_market_snapshot(market: str) -> dict:
    """Full snapshot for one market: etfs (latest price + 3M/6M/1Y returns
    per ticker), sectors (average returns per sector), sector_rotation
    (momentum-shift signal), trending (curated social-trending list).
    market must be one of: India, USA, USA-AI, Canada."""
    return _fetch(_slug(market))


@mcp.tool()
def get_etf(market: str, ticker: str) -> dict:
    """Look up one ETF's latest price and returns by ticker within a market
    (e.g. market='USA-AI', ticker='BOTZ')."""
    data = _fetch(_slug(market))
    for etf in data["etfs"]:
        if etf["ticker"].upper() == ticker.upper():
            return etf
    return {"error": f"{ticker} not found in {market}"}


@mcp.tool()
def get_sector_performance(market: str) -> list[dict]:
    """Average 1M/3M/1Y returns per sector for one market."""
    return _fetch(_slug(market))["sectors"]


@mcp.tool()
def get_sector_rotation(market: str) -> list[dict]:
    """Momentum-based sector rotation signal (decelerating vs. accelerating
    sectors) for one market. A computed proxy, not real fund-flow data."""
    return _fetch(_slug(market))["sector_rotation"]


@mcp.tool()
def get_trending(market: str) -> list[dict]:
    """Curated list of ETFs trending on social media/finance communities for
    one market, with returns and a note on why each is trending."""
    return _fetch(_slug(market))["trending"]


@mcp.tool()
def get_all_markets() -> dict:
    """Every market's full snapshot in one call."""
    return _fetch("all")


if __name__ == "__main__":
    mcp.run()
