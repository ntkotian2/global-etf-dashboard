# India Sector ETF Tracker

Tracks daily prices for India's NSE-listed sector ETFs (Bank, IT, Pharma, PSU Bank,
Consumption, Infra, etc.), stores history in a local SQLite database, and provides a
dashboard for comparing sector performance over time.

## Setup

```
pip install -r requirements.txt
```

## Fetch data

```
python src/fetch.py          # incremental update (only new dates since last fetch)
python src/fetch.py --full   # re-download full history for every ETF
```

This populates `data/etfs.db` (SQLite). Re-run periodically (e.g. daily after market
close) to keep the database current.

## View the dashboard

```
streamlit run src/dashboard.py
```

Lets you pick sectors and a time window, and shows normalized performance lines plus
a sortable returns table.

## Auto-start on login

`scripts/startup_all.vbs` runs `fetch.py` then launches the dashboard, both hidden
(no console windows). A copy is installed in your Windows Startup folder so this runs
automatically every time you log in, and the dashboard stays reachable at
`http://localhost:8501` — bookmark it.

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

Edit [config/etfs.yaml](config/etfs.yaml) — add a ticker (must be a valid yfinance
symbol, NSE tickers use the `.NS` suffix), name, and sector, then re-run `fetch.py`.

## Data source

Prices come from Yahoo Finance via the `yfinance` library. Data is typically delayed
and best-effort — not suitable for trading decisions, only for tracking trends.
