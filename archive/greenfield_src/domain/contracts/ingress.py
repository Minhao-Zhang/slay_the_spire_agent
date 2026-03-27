from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GameAdapterInput(BaseModel):
    """C1: CommunicationMod → adapter boundary. Validated at ingestion."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    in_game: bool = False
    ready_for_command: bool = False
    available_commands: list[str] = Field(default_factory=list)
    game_state: dict[str, Any] = Field(default_factory=dict)

    @field_validator("available_commands", mode="before")
    @classmethod
    def _coerce_commands(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise TypeError("available_commands must be a list")
        return [str(x) for x in v]

    @field_validator("game_state", mode="before")
    @classmethod
    def _coerce_game_state(cls, v: Any) -> dict[str, Any]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise TypeError("game_state must be an object")
        return v


def parse_ingress_envelope(raw: dict[str, Any]) -> GameAdapterInput:
    """Accept top-level CommunicationMod object or ``{\"state\": {...}}`` wrapper."""
    base = raw.get("state", raw)
    if not isinstance(base, dict):
        raise TypeError("ingress root must be a dict")
    payload = dict(base)
    return GameAdapterInput.model_validate(payload)
