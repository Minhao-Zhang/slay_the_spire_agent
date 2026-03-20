from __future__ import annotations

from src.agent.tracing import build_state_id
from src.domain.enums import SceneType
from src.domain.models.game import CardState, CombatState, GameSnapshot, HeaderState, InventoryState, MonsterState, PlayerCombatState


class StateNormalizer:
    """Converts a raw CommunicationMod payload into a typed internal snapshot."""

    def normalize(self, raw_payload: dict, run_id: str) -> GameSnapshot:
        state = raw_payload.get("state", raw_payload)
        action = raw_payload.get("action")
        game = state.get("game_state", {}) or {}
        combat = game.get("combat_state") or {}
        screen_type = str(game.get("screen_type", "NONE") or "NONE")
        screen_state = game.get("screen_state") or {}
        state_id = build_state_id(state)
        scene_type = self._classify_scene(state=state, combat=combat, screen_type=screen_type)
        header = HeaderState(
            character_class=str(game.get("class", "?")),
            floor=self._as_int(game.get("floor")),
            gold=self._as_int(game.get("gold")),
            current_hp=self._as_int(game.get("current_hp")),
            max_hp=self._as_int(game.get("max_hp")),
            energy=self._as_int((combat.get("player") or {}).get("energy")) if combat else None,
            turn=self._as_int(combat.get("turn")) if combat else None,
        )
        inventory = InventoryState(
            relics=list(game.get("relics", []) or []),
            potions=list(game.get("potions", []) or []),
            deck=[self._normalize_card(card) for card in game.get("deck", []) or []],
        )
        combat_state = None
        if combat:
            player = combat.get("player", {}) or {}
            combat_state = CombatState(
                turn=self._as_int(combat.get("turn")),
                player=PlayerCombatState(
                    energy=self._as_int(player.get("energy")),
                    block=self._as_int(player.get("block"), default=0) or 0,
                    powers=list(player.get("powers", []) or []),
                    orbs=list(player.get("orbs", []) or []),
                ),
                hand=[self._normalize_card(card) for card in combat.get("hand", []) or []],
                draw_pile=[self._normalize_card(card) for card in combat.get("draw_pile", []) or []],
                discard_pile=[self._normalize_card(card) for card in combat.get("discard_pile", []) or []],
                exhaust_pile=[self._normalize_card(card) for card in combat.get("exhaust_pile", []) or []],
                monsters=[
                    self._normalize_monster(index=index, monster=monster)
                    for index, monster in enumerate(combat.get("monsters", []) or [])
                ],
                current_action=str(combat.get("current_action")) if combat.get("current_action") else None,
            )

        return GameSnapshot(
            run_id=run_id,
            state_id=state_id,
            turn_key=self._build_turn_key(scene_type=scene_type, floor=header.floor, combat_present=bool(combat_state)),
            scene_type=scene_type,
            screen_type_raw=screen_type,
            in_game=bool(state.get("in_game", False)),
            ready_for_command=bool(state.get("ready_for_command", False)),
            header=header,
            inventory=inventory,
            combat=combat_state,
            screen={"type": screen_type, "state": screen_state} if screen_type != "NONE" else None,
            map_state={
                "nodes": list(game.get("map", []) or []),
                "current_node": screen_state.get("current_node") if screen_type == "MAP" else None,
                "next_nodes": list(screen_state.get("next_nodes", []) or []) if screen_type == "MAP" else [],
                "boss_available": bool(screen_state.get("boss_available", False)) if screen_type == "MAP" else False,
                "boss_name": game.get("act_boss"),
            }
            if game.get("map")
            else None,
            available_commands=list(state.get("available_commands", []) or []),
            raw_state=state,
            raw_game_state=game,
            raw_screen_state=screen_state,
            last_action=action,
        )

    @staticmethod
    def _build_turn_key(*, scene_type: SceneType, floor: int | None, combat_present: bool) -> str:
        floor_value = floor if floor is not None else "?"
        if combat_present:
            return f"COMBAT:{floor_value}"
        return f"{scene_type.value}:{floor_value}"

    @staticmethod
    def _classify_scene(*, state: dict, combat: dict, screen_type: str) -> SceneType:
        if not state.get("in_game", False):
            return SceneType.MAIN_MENU
        if combat:
            return SceneType.COMBAT
        if screen_type == "MAP":
            return SceneType.MAP
        if screen_type == "EVENT":
            return SceneType.EVENT
        if screen_type == "CARD_REWARD":
            return SceneType.CARD_REWARD
        if screen_type == "COMBAT_REWARD":
            return SceneType.COMBAT_REWARD
        if screen_type in {"SHOP_ROOM", "SHOP_SCREEN"}:
            return SceneType.SHOP
        if screen_type == "REST":
            return SceneType.REST
        if screen_type == "BOSS_REWARD":
            return SceneType.BOSS_REWARD
        if screen_type == "CHEST":
            return SceneType.CHEST
        if screen_type == "HAND_SELECT":
            return SceneType.HAND_SELECT
        if screen_type == "GRID":
            return SceneType.GRID
        if screen_type == "GAME_OVER":
            return SceneType.GAME_OVER
        return SceneType.UNKNOWN

    @staticmethod
    def _normalize_card(card: dict) -> CardState:
        uuid = str(card.get("uuid") or "") or None
        return CardState(
            id=str(card.get("id")) if card.get("id") is not None else None,
            uuid=uuid,
            token=uuid[:6] if uuid else None,
            name=str(card.get("name", "?")),
            cost=StateNormalizer._as_int(card.get("cost")),
            upgrades=StateNormalizer._as_int(card.get("upgrades"), default=0) or 0,
            type=str(card.get("type")) if card.get("type") else None,
            has_target=bool(card.get("has_target", False)),
            is_playable=bool(card.get("is_playable", True)),
            description=str(card.get("description")) if card.get("description") else None,
        )

    @staticmethod
    def _normalize_monster(*, index: int, monster: dict) -> MonsterState:
        damage = monster.get("move_base_damage", -1)
        hits = monster.get("move_hits", 1)
        if isinstance(damage, int) and damage > 0:
            adjusted = monster.get("move_adjusted_damage", damage)
            intent_display = f"Attack: {adjusted}x{hits}" if hits and hits > 1 else f"Attack: {adjusted}"
        else:
            intent_display = f"Intent: {monster.get('intent', '?')}"
        return MonsterState(
            id=str(monster.get("id")) if monster.get("id") is not None else None,
            index=index,
            name=str(monster.get("name", "?")),
            current_hp=StateNormalizer._as_int(monster.get("current_hp")),
            max_hp=StateNormalizer._as_int(monster.get("max_hp")),
            block=StateNormalizer._as_int(monster.get("block"), default=0) or 0,
            intent=str(monster.get("intent")) if monster.get("intent") else None,
            intent_display=intent_display,
            powers=list(monster.get("powers", []) or []),
            is_gone=bool(monster.get("is_gone", False)),
            half_dead=bool(monster.get("half_dead", False)),
        )

    @staticmethod
    def _as_int(value: object, default: int | None = None) -> int | None:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
