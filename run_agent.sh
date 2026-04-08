#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"
echo "Starting Slay the Spire Agent..."
exec .venv/bin/python -m src.main
