# Multi-Market ETF Tracker

Tracks daily sector ETF prices across **India** (NSE), **USA**, and **Canada**
(TSX), stores history in a local SQLite database, and provides a multi-page
dashboard for comparing sector performance within each market.

All four market pages are full-featured: top-down sector/theme classification
chart, sector performance, returns comparison, sector rotation, and
social-media-trending ETFs.

- **India**, **USA**, **Canada**: broad market-wide sector ETFs.
- **USA – AI**: a thematic sub-page tracking pure-play AI/robotics ETFs
  (BOTZ, ROBO, AIQ, ARKQ, etc.), grouped by AI sub-theme instead of GICS
  sector.

**Live dashboard**: https://global-etf-database.streamlit.app/

**JSON API** (open, no key needed): https://global-etf-database-api.onrender.com/
— see [API](#api) below for the endpoints and why it's a separate service.

**MCP server**: lets Claude query this data directly — see [MCP server](#mcp-server) below.

## Setup

```
pip install -r requirements.txt
```

## Fetch data

```
python src/fetch.py          # incremental update (only new dates since last fetch)
python src/fetch.py --full   # re-download full history for every ETF
```

This populates `data/etfs.db` (SQLite) from every config file in
`src/fetch.py`'s `CONFIG_FILES` map (India, USA, USA-AI, Canada). Re-run
periodically (e.g. daily after market close) to keep the database current.

## View the dashboard

```
streamlit run src/app.py
```

Opens on a Home page with links to India / USA / USA-AI / Canada. Each
market page lets you pick sectors and a time window, and shows normalized
performance lines plus a sortable returns table.

Or skip the local setup entirely and use the hosted version:
https://global-etf-database.streamlit.app/

## Auto-start on login

`scripts/startup_all.vbs` runs `fetch.py` then launches the dashboard, both
hidden (no console windows). A copy is installed in your Windows Startup
folder so this runs automatically every time you log in, and the dashboard
stays reachable at `http://localhost:8501` — bookmark it.

Logs go to `logs/fetch.log` and `logs/dashboard.log`.

To remove the auto-start, delete:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\IndiaETF-Startup.vbs
```
and kill the running `python` process (Task Manager, or `taskkill /IM python.exe /F`).

To reinstall/update it after editing `scripts/startup_all.vbs`:
```powershell
Copy-Item scripts\startup_all.vbs "$([Environment]::GetFolderPath('Startup'))\IndiaETF-Startup.vbs" -Force
```

## Adding/removing ETFs

Edit the relevant config file, then re-run `fetch.py`:
- [config/etfs.yaml](config/etfs.yaml) — India sector ETFs
- [config/etfs_usa.yaml](config/etfs_usa.yaml) — USA sector ETFs
- [config/etfs_usa_ai.yaml](config/etfs_usa_ai.yaml) — USA AI/robotics thematic ETFs
- [config/etfs_canada.yaml](config/etfs_canada.yaml) — Canada sector ETFs
- [config/social_trending_etfs.yaml](config/social_trending_etfs.yaml) — India social-trending list
- [config/social_trending_etfs_usa.yaml](config/social_trending_etfs_usa.yaml) — USA social-trending list
- [config/social_trending_etfs_usa_ai.yaml](config/social_trending_etfs_usa_ai.yaml) — USA-AI social-trending list
- [config/social_trending_etfs_canada.yaml](config/social_trending_etfs_canada.yaml) — Canada social-trending list
- [config/etf_taxonomy.yaml](config/etf_taxonomy.yaml) — India's classification chart structure
- [config/etf_taxonomy_usa.yaml](config/etf_taxonomy_usa.yaml) — USA's classification chart structure
- [config/etf_taxonomy_usa_ai.yaml](config/etf_taxonomy_usa_ai.yaml) — USA-AI's classification chart structure
- [config/etf_taxonomy_canada.yaml](config/etf_taxonomy_canada.yaml) — Canada's classification chart structure

Note: a ticker can only belong to one market at a time (the database keys
ETFs by ticker alone) — don't add the same ticker to two different config
files.

`ticker` must be a valid yfinance symbol: NSE tickers use `.NS`, TSX tickers
use `.TO`, US tickers need no suffix.

## Project structure

```
src/
  app.py          # entry point (streamlit run src/app.py) — defines page navigation
  common.py       # Streamlit rendering helpers used by every market page
  api_data.py     # pure data computation, shared by common.py and api-server (no Streamlit dep)
  db.py           # SQLite schema + connection
  fetch.py        # pulls prices via yfinance, upserts into SQLite
  pages/
    home.py       # landing page with links to each market
    india.py      # India page
    usa.py        # USA page
    usa_ai.py     # USA AI/robotics thematic page
    canada.py     # Canada page
  static/api/     # generated JSON snapshots served at /app/static/api/ locally only — see API below
.streamlit/
  config.toml     # enableStaticServing = true (local-only, see API section)
api-server/       # standalone FastAPI service — the real public API, see API below
  main.py
  requirements.txt
mcp-server/       # MCP server wrapping api-server as Claude-usable tools, see MCP server below
  server.py
  requirements.txt
render.yaml       # Render blueprint for deploying api-server
```

## API

A read-only, unauthenticated JSON snapshot of everything the dashboard shows
— `etfs` (latest price + 3M/6M/1Y returns per ticker), `sectors` (average
returns per sector), `sector_rotation` (the momentum-shift signal), and
`trending` (the curated social-trending list) — computed by
[src/api_data.py](src/api_data.py)'s `build_market_api_payload`, shared by
both the dashboard and the API below so the numbers always match.

### Why a separate service

The first attempt used Streamlit's built-in
[static file serving](https://docs.streamlit.io/develop/concepts/configuration/serving-static-files)
(`enableStaticServing`, still in [.streamlit/config.toml](.streamlit/config.toml))
to expose JSON at `/app/static/api/...` directly from the dashboard, with no
extra hosting. It works when running locally
(`http://localhost:8501/app/static/api/india.json`) but **not** on Streamlit
Community Cloud: that platform now runs apps behind a gateway (its own
`/-/build/assets/...`, `/-/auth/...` routes) that only proxies known
Streamlit routes through to the app process — confirmed by testing that even
Streamlit's *own* built-in static assets (`favicon.png`, `manifest.json`) get
served the gateway's app shell instead of their real content on this
platform. So the public API is instead [api-server/](api-server/), a small
standalone FastAPI service with its own SQLite database (same self-refresh
pattern as the dashboard, via yfinance).

### Endpoints

Live at https://global-etf-database-api.onrender.com (deployed on Render's
free tier — the first request after a period of inactivity takes ~30-60s to
wake the service and cold-fetch that market's price history; cached
responses after that are near-instant):

```
GET https://global-etf-database-api.onrender.com/            # discovery doc: schema + endpoint list
GET https://global-etf-database-api.onrender.com/india        # one market
GET https://global-etf-database-api.onrender.com/usa
GET https://global-etf-database-api.onrender.com/usa-ai
GET https://global-etf-database-api.onrender.com/canada
GET https://global-etf-database-api.onrender.com/all          # every market combined
GET https://global-etf-database-api.onrender.com/healthz      # health check
```

### Deploying api-server

Any Python host works; [Render](https://render.com)'s free tier is the path
of least friction and this repo includes [render.yaml](render.yaml) for it:

1. On [render.com](https://render.com), **New** → **Blueprint**, connect
   this GitHub repo. Render reads `render.yaml` and creates the service
   automatically (root dir `api-server`, free plan, health check `/healthz`).
2. Or manually: **New** → **Web Service** → connect the repo → root
   directory `api-server` → build command `pip install -r requirements.txt`
   → start command `uvicorn main:app --host 0.0.0.0 --port $PORT`.
3. Render gives you a URL like `https://global-etf-database-api.onrender.com`.
   Free-tier services sleep after inactivity and take ~30s to wake on the
   next request — same self-heal-on-first-request pattern as the rest of
   this project, just with a cold-start delay.

Locally: `cd api-server && pip install -r requirements.txt && uvicorn main:app --reload --port 8000`.

## MCP server

[mcp-server/](mcp-server/) wraps the API above as an
[MCP](https://modelcontextprotocol.io) server, so Claude (or any other MCP
client) can query live ETF data as tools instead of you pasting URLs into
chat: `list_markets`, `get_market_snapshot`, `get_etf`,
`get_sector_performance`, `get_sector_rotation`, `get_trending`,
`get_all_markets`.

Setup:
```
cd mcp-server
pip install -r requirements.txt
```

`ETF_API_BASE_URL` defaults to `http://localhost:8000` for local dev; set it
to the deployed URL above for the live data.

**Claude Desktop** — add to `claude_desktop_config.json`
(`%APPDATA%\Claude\claude_desktop_config.json` on Windows):
```json
{
  "mcpServers": {
    "etf-tracker": {
      "command": "python",
      "args": ["C:\\Users\\ntkot\\Documents\\GitHub\\global-etf-database\\mcp-server\\server.py"],
      "env": { "ETF_API_BASE_URL": "https://global-etf-database-api.onrender.com" }
    }
  }
}
```
Restart Claude Desktop after editing.

**Claude Code**:
```
claude mcp add etf-tracker --env ETF_API_BASE_URL=https://global-etf-database-api.onrender.com -- python "C:\Users\ntkot\Documents\GitHub\global-etf-database\mcp-server\server.py"
```

**claude.ai (web/mobile Custom Connectors)** needs a *remote* MCP server
(reachable over HTTPS), not this stdio-based one — a further step beyond
what's built here if you want it on that surface too.

## Data source

Prices come from Yahoo Finance via the `yfinance` library — free, no
subscription or account needed, but unofficial (not a licensed API) and
delayed. Fine for a daily trend tracker like this one, not for trading
decisions.
