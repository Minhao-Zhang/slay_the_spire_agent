from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.enums import SceneType


class CardState(BaseModel):
    id: str | None = None
    uuid: str | None = None
    token: str | None = None
    name: str
    cost: int | None = None
    upgrades: int = 0
    type: str | None = None
    has_target: bool = False
    is_playable: bool = True
    description: str | None = None


class MonsterState(BaseModel):
    id: str | None = None
    index: int
    name: str
    current_hp: int | None = None
    max_hp: int | None = None
    block: int = 0
    intent: str | None = None
    intent_display: str | None = None
    powers: list[dict[str, object]] = Field(default_factory=list)
    is_gone: bool = False
    half_dead: bool = False


class PlayerCombatState(BaseModel):
    energy: int | None = None
    block: int = 0
    powers: list[dict[str, object]] = Field(default_factory=list)
    orbs: list[dict[str, object]] = Field(default_factory=list)


class CombatState(BaseModel):
    turn: int | None = None
    player: PlayerCombatState = Field(default_factory=PlayerCombatState)
    hand: list[CardState] = Field(default_factory=list)
    draw_pile: list[CardState] = Field(default_factory=list)
    discard_pile: list[CardState] = Field(default_factory=list)
    exhaust_pile: list[CardState] = Field(default_factory=list)
    monsters: list[MonsterState] = Field(default_factory=list)
    current_action: str | None = None


class HeaderState(BaseModel):
    character_class: str = "?"
    floor: int | None = None
    gold: int | None = None
    current_hp: int | None = None
    max_hp: int | None = None
    energy: int | None = None
    turn: int | None = None


class InventoryState(BaseModel):
    relics: list[dict[str, object]] = Field(default_factory=list)
    potions: list[dict[str, object]] = Field(default_factory=list)
    deck: list[CardState] = Field(default_factory=list)


class GameSnapshot(BaseModel):
    run_id: str
    state_id: str
    turn_key: str
    scene_type: SceneType = SceneType.UNKNOWN
    in_game: bool = False
    ready_for_command: bool = False

    header: HeaderState = Field(default_factory=HeaderState)
    inventory: InventoryState = Field(default_factory=InventoryState)
    combat: CombatState | None = None
    screen: dict[str, object] | None = None
    map_state: dict[str, object] | None = None

    available_commands: list[str] = Field(default_factory=list)
    raw_state: dict[str, object] = Field(default_factory=dict)
    last_action: str | None = None
