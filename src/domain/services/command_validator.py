from __future__ import annotations

from dataclasses import dataclass

from src.domain.models.actions import LegalActionSet


@dataclass
class CommandValidationResult:
    valid: bool
    action_id: str | None = None
    command: str | None = None
    error: str = ""


class CommandValidator:
    """Validates selected action IDs or commands against the current legal action set."""

    def validate_action_id(
        self,
        action_id: str,
        legal_actions: LegalActionSet,
    ) -> CommandValidationResult:
        raise NotImplementedError("CommandValidator.validate_action_id() is part of the v2 rewrite scaffold.")

    def validate_command(
        self,
        command: str,
        legal_actions: LegalActionSet,
    ) -> CommandValidationResult:
        raise NotImplementedError("CommandValidator.validate_command() is part of the v2 rewrite scaffold.")
