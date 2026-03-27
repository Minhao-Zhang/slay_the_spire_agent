"""C2: View model and legal action candidates (UI + prompt pipeline)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ActionStyle = Literal["primary", "secondary", "danger", "success"]


class ActionCandidate(BaseModel):
    """One legal operator action (button)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    label: str
    command: str
    style: ActionStyle = "primary"
    card_uuid_token: str | None = None
    hand_index: int | None = None
    monster_index: int | None = None


class HeaderView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    class_: str = Field(alias="class", default="?")
    floor: str = "-"
    gold: str = "-"
    hp_display: str = "-"
    energy: str = "-"
    turn: str = "-"


class ViewModel(BaseModel):
    """C2 top-level shape."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: int = 1
    in_game: bool = False
    header: HeaderView | None = None
    actions: list[ActionCandidate] = Field(default_factory=list)
    combat: dict[str, Any] | None = None
    screen: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None
    map: dict[str, Any] | None = None
    sidebar: dict[str, Any] | None = None
    last_action: Any | None = None

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_actions(cls, v: Any) -> list:
        if v is None:
            return []
        return list(v)
