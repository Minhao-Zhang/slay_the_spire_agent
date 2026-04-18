"""Normalization helpers for comparing file-based vs SQL-backed :class:`RunReport` payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agent.reflection.report_types import RunReport


def normalize_run_report_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Make ``RunReport.model_dump()`` comparable across disk paths and import rounds."""
    out = dict(data)
    out["run_dir"] = str(Path(out["run_dir"]).resolve())
    decs: list[dict[str, Any]] = []
    for dr in out.get("decisions") or []:
        if not isinstance(dr, dict):
            continue
        row = dict(dr)
        sp = row.get("source_path")
        if sp:
            row["source_path"] = str(Path(str(sp)).resolve())
        decs.append(row)
    out["decisions"] = decs
    tu = out.get("tool_usage") or {}
    if isinstance(tu, dict):
        out["tool_usage"] = {k: tu[k] for k in sorted(tu.keys())}
    rli = out.get("retrieved_lesson_ids")
    if isinstance(rli, list):
        out["retrieved_lesson_ids"] = sorted(str(x) for x in rli)
    return out


def normalized_run_report_dict(report: RunReport) -> dict[str, Any]:
    return normalize_run_report_dict(report.model_dump())
