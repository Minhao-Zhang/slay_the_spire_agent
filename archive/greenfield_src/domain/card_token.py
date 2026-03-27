"""Stable short prefix from card UUID for model I/O (legacy parity, longer than archive)."""

from __future__ import annotations

CARD_TOKEN_LEN = 8


def card_uuid_token(uuid_full: str | None) -> str:
    """First ``CARD_TOKEN_LEN`` chars of UUID string (no hyphens in prefix — strip first)."""
    if not uuid_full:
        return ""
    compact = str(uuid_full).replace("-", "")
    return compact[:CARD_TOKEN_LEN] if compact else ""
