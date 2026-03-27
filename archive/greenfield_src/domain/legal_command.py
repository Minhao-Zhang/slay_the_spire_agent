"""Command legality against a projected view model (pure, no I/O)."""

from __future__ import annotations

from typing import Any


def normalize_command_key(command: str) -> str:
    return " ".join(command.strip().split()).lower()


def is_command_legal(view_model: dict[str, Any] | None, command: str) -> bool:
    if not view_model or not command:
        return False
    want = normalize_command_key(command)
    for a in view_model.get("actions") or []:
        c = a.get("command")
        if c and normalize_command_key(str(c)) == want:
            return True
    return False


def canonical_legal_command(view_model: dict[str, Any] | None, command: str) -> str:
    """
    Return the exact ``command`` string from the legal action list.

    Raises ``ValueError`` if the command is not currently legal.
    """
    if not view_model or not command:
        raise ValueError("missing_view_model_or_command")
    want = normalize_command_key(command)
    for a in view_model.get("actions") or []:
        c = a.get("command")
        if c and normalize_command_key(str(c)) == want:
            return str(c).strip()
    raise ValueError(f"command_not_legal:{command!r}")
