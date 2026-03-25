#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"
echo "Starting Slay the Spire Agent via uv..."
exec uv run python -m src.main
