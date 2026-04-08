from __future__ import annotations

import logging
from typing import Any

import yaml

log = logging.getLogger(__name__)


def parse_strategy_markdown(raw: str) -> tuple[list[str], str]:
    """Split YAML frontmatter (first ``---`` … ``---``) from markdown body.

    On failure, returns ``([], stripped_full_text)`` so the file can still be used untagged.
    """
    text = raw.lstrip("\ufeff")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return [], text.strip()

    end: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        log.warning("strategy markdown: opening --- without closing ---; using whole file as body")
        return [], text.strip()

    fm_block = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :]).strip()
    tags: list[str] = []
    try:
        meta = yaml.safe_load(fm_block)
        if isinstance(meta, dict):
            raw_tags = meta.get("tags")
            if isinstance(raw_tags, list):
                tags = [str(t).strip().lower() for t in raw_tags if str(t).strip()]
            elif isinstance(raw_tags, str) and raw_tags.strip():
                tags = [raw_tags.strip().lower()]
    except yaml.YAMLError as exc:
        log.warning("strategy markdown: invalid YAML frontmatter: %s", exc)

    return tags, body
