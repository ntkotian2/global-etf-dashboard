@echo off
cd /d "C:\Users\ntkot\Documents\GitHub\global-etf-database"
python src\fetch.py >> logs\fetch.log 2>&1
