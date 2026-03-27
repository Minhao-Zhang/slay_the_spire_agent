@echo off
cd /d "%~dp0"
echo Control API on http://127.0.0.1:8000  (use with: npm run dev:web)
uv run uvicorn src.ui.dashboard:app --host 127.0.0.1 --port 8000 --reload
