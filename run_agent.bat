@echo off
cd /d "%~dp0"
echo Starting Slay the Spire Agent...
.venv\Scripts\python.exe -m src.main
