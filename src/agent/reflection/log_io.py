"""Read run log artifacts without importing the FastAPI dashboard."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_AI_JSON = re.compile(r"^(\d+)\.ai\.json$")
_FRAME_JSON = re.compile(r"^(\d+)\.json$")


def iter_frame_json_paths(run_dir: Path) -> list[Path]:
    """Sorted ``NNNN.json`` state log envelopes (excludes ``*.ai.json``)."""
    if not run_dir.is_dir():
        return []
    paths: list[tuple[int, Path]] = []
    for p in run_dir.iterdir():
        if not p.is_file():
            continue
        m = _FRAME_JSON.match(p.name)
        if m:
            paths.append((int(m.group(1)), p))
    paths.sort(key=lambda x: x[0])
    return [p for _, p in paths]


def iter_ai_json_paths(run_dir: Path) -> list[Path]:
    if not run_dir.is_dir():
        return []
    paths: list[tuple[int, Path]] = []
    for p in run_dir.iterdir():
        if not p.is_file():
            continue
        m = _AI_JSON.match(p.name)
        if m:
            paths.append((int(m.group(1)), p))
    paths.sort(key=lambda x: x[0])
    return [p for _, p in paths]


def read_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def load_run_metrics_lines(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "run_metrics.ndjson"
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def load_run_end_snapshot(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "run_end_snapshot.json"
    data = read_json_dict(path)
    if not data:
        return None
    return data
