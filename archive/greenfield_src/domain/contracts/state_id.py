"""C1b/C1c: deterministic state_id from canonical JSON over the fingerprint payload."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.domain.contracts.ingress import GameAdapterInput

STATE_ID_VERSION = 1

# Keys whose values define command-relevant identity for hashing (top-level ingress).
_FINGERPRINT_KEYS: tuple[str, ...] = (
    "in_game",
    "ready_for_command",
    "available_commands",
    "game_state",
)


def _canonical_json(obj: Any) -> str:
    """Stable JSON: sorted keys recursively, compact separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint_payload(ingress: GameAdapterInput) -> dict[str, Any]:
    """Build the dict that is hashed for state_id (explicit key set)."""
    data = ingress.model_dump()
    return {k: data[k] for k in _FINGERPRINT_KEYS if k in data}


def compute_state_id(ingress: GameAdapterInput) -> str:
    """
    Deterministic content hash. Includes STATE_ID_VERSION prefix so migrations can
    change canonicalization without colliding with old ids.
    """
    body = fingerprint_payload(ingress)
    canonical = _canonical_json(
        {"v": STATE_ID_VERSION, "ingress": body},
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"v{STATE_ID_VERSION}-{digest[:16]}"
