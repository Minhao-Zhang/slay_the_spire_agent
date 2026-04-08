from __future__ import annotations

import re
from typing import Any


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify_token(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = _slug_re.sub("_", s)
    return s.strip("_") or ""


def flatten_tag_mapping(m: dict[str, Any]) -> frozenset[str]:
    """Lowercase slug tokens from values in a mapping (recurse one level into lists)."""
    out: set[str] = set()
    for _k, v in (m or {}).items():
        if isinstance(v, str):
            t = slugify_token(v)
            if t:
                out.add(t)
        elif isinstance(v, bool):
            out.add("true" if v else "false")
        elif isinstance(v, int) and not isinstance(v, bool):
            t = slugify_token(str(v))
            if t:
                out.add(t)
        elif isinstance(v, float) and v == int(v):
            t = slugify_token(str(int(v)))
            if t:
                out.add(t)
        elif isinstance(v, (list, tuple)):
            for item in v:
                if isinstance(item, str):
                    t = slugify_token(item)
                    if t:
                        out.add(t)
                elif isinstance(item, bool):
                    out.add("true" if item else "false")
                elif isinstance(item, int) and not isinstance(item, bool):
                    t = slugify_token(str(item))
                    if t:
                        out.add(t)
                elif isinstance(item, float) and item == int(item):
                    t = slugify_token(str(int(item)))
                    if t:
                        out.add(t)
    return frozenset(out)
