from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.enums import SceneType


class DecisionContext(BaseModel):
    scene_type: SceneType
    state_id: str
    turn_key: str
    summary: dict[str, object] = Field(default_factory=dict)
    legal_actions: list[dict[str, object]] = Field(default_factory=list)
    memory: dict[str, object] = Field(default_factory=dict)
