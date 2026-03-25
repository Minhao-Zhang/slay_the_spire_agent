"""Repository root for loading packaged data (e.g. ``data/processed``)."""

from __future__ import annotations

from pathlib import Path

# This file: <repo>/src/repo_paths.py → repo root is parent of ``src``.
REPO_ROOT = Path(__file__).resolve().parent.parent

__all__ = ["REPO_ROOT"]
