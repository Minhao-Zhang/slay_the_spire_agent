from __future__ import annotations

from enum import Enum


class SceneType(str, Enum):
    MAIN_MENU = "MAIN_MENU"
    COMBAT = "COMBAT"
    MAP = "MAP"
    EVENT = "EVENT"
    CARD_REWARD = "CARD_REWARD"
    COMBAT_REWARD = "COMBAT_REWARD"
    SHOP = "SHOP"
    REST = "REST"
    BOSS_REWARD = "BOSS_REWARD"
    CHEST = "CHEST"
    HAND_SELECT = "HAND_SELECT"
    GRID = "GRID"
    GAME_OVER = "GAME_OVER"
    UNKNOWN = "UNKNOWN"


class OperatorMode(str, Enum):
    MANUAL = "manual"
    PROPOSE = "propose"
    AUTO = "auto"


class ActionType(str, Enum):
    PLAY = "play"
    CHOOSE = "choose"
    POTION = "potion"
    END = "end"
    SYSTEM = "system"


class TraceStatus(str, Enum):
    IDLE = "idle"
    BUILDING_CONTEXT = "building_context"
    BUILDING_PROMPT = "building_prompt"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    INVALID = "invalid"
    ERROR = "error"
    DISABLED = "disabled"
    STALE = "stale"
