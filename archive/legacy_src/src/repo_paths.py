"""Repository root and legacy package paths when code lives under archive/legacy_src/src."""

from pathlib import Path

# This file: <repo>/archive/legacy_src/src/repo_paths.py
LEGACY_SRC_ROOT = Path(__file__).resolve().parent
# src -> legacy_src -> archive -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

__all__ = ["REPO_ROOT", "LEGACY_SRC_ROOT"]
