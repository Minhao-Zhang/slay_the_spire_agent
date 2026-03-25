"""Parse model output into ``StructuredCommandProposal``."""

from __future__ import annotations

import json
import re

from src.agent_core.schemas import StructuredCommandProposal


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _strip_fences(text: str) -> str:
    t = text.strip()
    m = _FENCE_RE.search(t)
    if m:
        return m.group(1).strip()
    return t


def parse_proposal_json(text: str) -> StructuredCommandProposal:
    raw = _strip_fences(text)
    if not raw:
        raise ValueError("empty model output")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return StructuredCommandProposal.model_validate(data)
