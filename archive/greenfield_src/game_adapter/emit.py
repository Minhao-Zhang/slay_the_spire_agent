"""
Validate commands before emitting them to CommunicationMod (write path).

Operator / graph commands must match the current legal action list. Idle /
heartbeat strings use ``available_commands`` on the raw ingress dict.
"""

from __future__ import annotations

from typing import Any

from src.domain.legal_command import canonical_legal_command


def validate_operator_command(view_model: dict[str, Any], command: str) -> str:
    """Return canonical command text for a card / UI action."""
    return canonical_legal_command(view_model, command)


def validate_idle_command(ingress_raw: dict[str, Any], command: str) -> str:
    """Ensure ``wait 10`` / ``state`` style heartbeats are allowed this turn."""
    if not command or not isinstance(ingress_raw, dict):
        raise ValueError("invalid_idle_context")
    avail = ingress_raw.get("available_commands") or []
    norm = " ".join(command.strip().split()).lower()
    if norm == "wait 10":
        if "wait" not in avail:
            raise ValueError("wait_not_available")
        return "wait 10"
    if norm == "state":
        if "state" not in avail:
            raise ValueError("state_not_available")
        return "state"
    raise ValueError(f"not_an_idle_command:{command!r}")
