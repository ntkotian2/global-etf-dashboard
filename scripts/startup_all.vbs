Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\ntkot\Documents\GitHub\global-etf-database"
WshShell.Run "cmd /c ""C:\Users\ntkot\Documents\GitHub\global-etf-database\scripts\run_fetch.bat""", 0, True
WshShell.Run "cmd /c python -m streamlit run src\app.py --server.headless true --server.port 8501 >> logs\dashboard.log 2>&1", 0, False
