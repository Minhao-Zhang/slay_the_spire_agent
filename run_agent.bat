@echo off
cd /d "%~dp0"
echo Starting Slay the Spire Agent via uv...
uv run python -m src.main
