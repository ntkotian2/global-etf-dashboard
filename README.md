# Multi-Market ETF Tracker

Tracks daily sector ETF prices across **India** (NSE), **USA**, and **Canada**
(TSX), stores history in a local SQLite database, and provides a multi-page
dashboard for comparing sector performance within each market.

- **India**: full-featured — top-down sector/theme classification chart,
  sector performance, returns comparison, social-media-trending ETFs.
- **USA / Canada**: sector performance + returns comparison (India's extra
  sections haven't been built out for these yet).

**Live dashboard**: https://global-etf-database.streamlit.app/

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
`src/fetch.py`'s `CONFIG_FILES` map (India, USA, Canada). Re-run periodically
(e.g. daily after market close) to keep the database current.

## View the dashboard

```
streamlit run src/app.py
```

Opens on a Home page with links to India / USA / Canada. Each market page
lets you pick sectors and a time window, and shows normalized performance
lines plus a sortable returns table.

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
- [config/etfs_canada.yaml](config/etfs_canada.yaml) — Canada sector ETFs
- [config/social_trending_etfs.yaml](config/social_trending_etfs.yaml) — India social-trending list
- [config/etf_taxonomy.yaml](config/etf_taxonomy.yaml) — India's classification chart structure

`ticker` must be a valid yfinance symbol: NSE tickers use `.NS`, TSX tickers
use `.TO`, US tickers need no suffix.

## Project structure

```
src/
  app.py          # entry point (streamlit run src/app.py) — defines page navigation
  common.py       # shared helpers used by every market page
  db.py           # SQLite schema + connection
  fetch.py        # pulls prices via yfinance, upserts into SQLite
  pages/
    home.py       # landing page with links to each market
    india.py      # full-featured India page
    usa.py        # USA page
    canada.py     # Canada page
```

## Data source

Prices come from Yahoo Finance via the `yfinance` library — free, no
subscription or account needed, but unofficial (not a licensed API) and
delayed. Fine for a daily trend tracker like this one, not for trading
decisions.
