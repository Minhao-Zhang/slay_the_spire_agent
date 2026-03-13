#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"
echo "Starting Slay the Spire Agent via venv Python..."
"/Users/minhaozhang/Documents/Code/slay_the_spire_agent/.venv/bin/python" -m src.main