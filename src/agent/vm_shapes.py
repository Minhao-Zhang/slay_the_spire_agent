"""Normalize view-model / ingress shapes that sometimes arrive as the wrong type."""

from __future__ import annotations

from typing import Any


def normalize_legal_actions(raw: Any) -> list[dict[str, Any]]:
    """Ensure ``vm['actions']`` is a list of dicts.

    Some ingress shapes may include bare command strings; code that does
    ``action.get(...)`` then raises ``'str' object has no attribute 'get'``.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str) and item.strip():
            s = item.strip()
            out.append({"label": s, "command": s, "style": "secondary"})
    return out


def as_dict(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}
