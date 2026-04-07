"""Repository root and Python package root (directory containing this file)."""

from pathlib import Path

# This file: <repo>/src/repo_paths.py
PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[1]

__all__ = ["REPO_ROOT", "PACKAGE_ROOT"]
