from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.enums import ActionType


class LegalAction(BaseModel):
    action_id: str
    label: str
    command: str
    action_type: ActionType
    style: str = "primary"

    card_token: str | None = None
    hand_index: int | None = None
    target_index: int | None = None
    choice_index: int | str | None = None
    target_required: bool = False

    metadata: dict[str, object] = Field(default_factory=dict)


class LegalActionSet(BaseModel):
    actions: list[LegalAction] = Field(default_factory=list)

    def by_id(self) -> dict[str, LegalAction]:
        return {action.action_id: action for action in self.actions}

    def by_command(self) -> dict[str, LegalAction]:
        return {action.command: action for action in self.actions}
