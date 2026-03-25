#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Control API on http://127.0.0.1:8000  (use with: npm run dev:web)"
exec uv run uvicorn src.control_api.app:app --host 127.0.0.1 --port 8000 --reload
