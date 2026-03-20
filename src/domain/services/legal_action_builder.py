from __future__ import annotations

from src.domain.enums import ActionType
from src.domain.models.actions import LegalAction, LegalActionSet
from src.domain.models.game import GameSnapshot

_COMMAND_BUTTONS = [
    ("proceed", "PROCEED", "PROCEED", "primary"),
    ("end", "END TURN", "END", "danger"),
    ("cancel", "CANCEL", "CANCEL", "secondary"),
    ("leave", "LEAVE", "LEAVE", "secondary"),
    ("skip", "SKIP", "SKIP", "secondary"),
    ("confirm", "CONFIRM", "CONFIRM", "primary"),
    ("return", "RETURN", "RETURN", "secondary"),
]

_REST_OPTION_LABELS = {
    "rest": "Rest",
    "smith": "Smith",
    "lift": "Lift",
    "toke": "Toke",
    "dig": "Dig",
    "recall": "Recall",
}


class LegalActionBuilder:
    """Derives deterministic legal actions from the normalized snapshot."""

    def build(self, snapshot: GameSnapshot) -> LegalActionSet:
        actions: list[LegalAction] = []
        commands = set(snapshot.available_commands)

        for cmd_key, label, command, style in _COMMAND_BUTTONS:
            if cmd_key in commands:
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(
                            ActionType.END if command == "END" else ActionType.SYSTEM,
                            command,
                        ),
                        label=label,
                        command=command,
                        action_type=ActionType.END if command == "END" else ActionType.SYSTEM,
                        style=style,
                    )
                )

        combat = snapshot.combat
        game = snapshot.raw_game_state
        screen_type = snapshot.screen_type_raw
        screen_state = snapshot.raw_screen_state

        if "play" in commands and combat:
            energy = combat.player.energy or 0
            for hand_index, card in enumerate(combat.hand, start=1):
                cost = card.cost if card.cost is not None else 99
                if not card.is_playable or cost > energy:
                    continue
                if card.has_target:
                    for monster in combat.monsters:
                        if monster.is_gone or monster.half_dead:
                            continue
                        command = f"PLAY {hand_index} {monster.index}"
                        actions.append(
                            LegalAction(
                                action_id=self._build_action_id(ActionType.PLAY, command),
                                label=f"{card.name} -> {monster.name}",
                                command=command,
                                action_type=ActionType.PLAY,
                                style="success",
                                card_token=card.token,
                                hand_index=hand_index,
                                target_index=monster.index,
                                target_required=True,
                            )
                        )
                else:
                    command = f"PLAY {hand_index}"
                    actions.append(
                        LegalAction(
                            action_id=self._build_action_id(ActionType.PLAY, command),
                            label=card.name,
                            command=command,
                            action_type=ActionType.PLAY,
                            style="primary",
                            card_token=card.token,
                            hand_index=hand_index,
                        )
                    )

        if "potion" in commands:
            for index, potion in enumerate(game.get("potions", []) or []):
                if potion.get("can_use"):
                    if potion.get("requires_target") and combat:
                        for monster in combat.monsters:
                            if monster.is_gone or monster.half_dead:
                                continue
                            command = f"POTION USE {index} {monster.index}"
                            actions.append(
                                LegalAction(
                                    action_id=self._build_action_id(ActionType.POTION, command),
                                    label=f"Use {potion['name']} -> {monster.name}",
                                    command=command,
                                    action_type=ActionType.POTION,
                                    style="primary",
                                    target_index=monster.index,
                                    target_required=True,
                                )
                            )
                    else:
                        command = f"POTION USE {index}"
                        actions.append(
                            LegalAction(
                                action_id=self._build_action_id(ActionType.POTION, command),
                                label=f"Use {potion['name']}",
                                command=command,
                                action_type=ActionType.POTION,
                                style="primary",
                            )
                        )
                if potion.get("can_discard"):
                    command = f"POTION DISCARD {index}"
                    actions.append(
                        LegalAction(
                            action_id=self._build_action_id(ActionType.POTION, command),
                            label=f"Discard {potion['name']}",
                            command=command,
                            action_type=ActionType.POTION,
                            style="secondary",
                        )
                    )

        if "choose" in commands:
            actions.extend(self._build_choose_actions(screen_type=screen_type, screen_state=screen_state, game=game))

        return LegalActionSet(actions=actions)

    def _build_choose_actions(
        self,
        *,
        screen_type: str,
        screen_state: dict[str, object],
        game: dict[str, object],
    ) -> list[LegalAction]:
        actions: list[LegalAction] = []
        items = (
            screen_state.get("hand")
            or screen_state.get("cards")
            or screen_state.get("relics")
            or screen_state.get("rewards")
            or screen_state.get("potions")
            or []
        )

        if screen_type == "MAP" and screen_state.get("next_nodes"):
            for index, node in enumerate(screen_state["next_nodes"]):
                command = f"choose {index}"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=f"GO: {node.get('symbol', '?')}",
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="primary",
                        choice_index=index,
                    )
                )
            if screen_state.get("boss_available"):
                command = "choose boss"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label="FIGHT BOSS",
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="danger",
                        choice_index="boss",
                    )
                )
            return actions

        if screen_type == "EVENT" and screen_state.get("options"):
            for index, option in enumerate(screen_state["options"]):
                if option.get("disabled"):
                    continue
                command = f"choose {index}"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=option.get("label", f"Select {index}"),
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="primary",
                        choice_index=index,
                    )
                )
            return actions

        if screen_type == "COMBAT_REWARD" and screen_state.get("rewards"):
            for index, reward in enumerate(screen_state["rewards"]):
                reward_type = reward.get("reward_type", "")
                if reward_type == "GOLD":
                    label = f"Take {reward.get('gold', '?')} Gold"
                elif reward_type == "POTION":
                    label = f"Take {reward.get('potion', {}).get('name', 'Potion')}"
                elif reward_type == "RELIC":
                    label = f"Take {reward.get('relic', {}).get('name', 'Relic')}"
                elif reward_type == "CARD":
                    label = "Reward: Card Draft"
                else:
                    label = str(reward_type)
                command = f"choose {index}"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=label,
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="secondary",
                        choice_index=index,
                    )
                )
            return actions

        if screen_type == "SHOP_ROOM":
            for choice in game.get("choice_list", []) or []:
                command = f"choose {choice}"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=str(choice).title(),
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="primary",
                        choice_index=str(choice),
                    )
                )
            return actions

        if screen_type == "SHOP_SCREEN":
            for index, card in enumerate(screen_state.get("cards", []) or []):
                command = f"choose {card.get('name', index)}"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=f"Buy {card.get('name', '?')} ({card.get('price', '?')}g)",
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="secondary",
                        choice_index=card.get("name", index),
                    )
                )
            for relic in screen_state.get("relics", []) or []:
                command = f"choose {relic.get('name', '?')}"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=f"Buy {relic.get('name', '?')} ({relic.get('price', '?')}g)",
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="secondary",
                        choice_index=relic.get("name", "?"),
                    )
                )
            for potion in screen_state.get("potions", []) or []:
                command = f"choose {potion.get('name', '?')}"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=f"Buy {potion.get('name', '?')} ({potion.get('price', '?')}g)",
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="secondary",
                        choice_index=potion.get("name", "?"),
                    )
                )
            if screen_state.get("purge_available"):
                command = "choose purge"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=f"Remove Card ({screen_state.get('purge_cost', '?')}g)",
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="danger",
                        choice_index="purge",
                    )
                )
            return actions

        if screen_type == "CHEST":
            command = "choose open"
            return [
                LegalAction(
                    action_id=self._build_action_id(ActionType.CHOOSE, command),
                    label="Open Chest",
                    command=command,
                    action_type=ActionType.CHOOSE,
                    style="primary",
                    choice_index="open",
                )
            ]

        if screen_type == "REST" and screen_state.get("rest_options"):
            for option in screen_state["rest_options"]:
                command = f"choose {option}"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=_REST_OPTION_LABELS.get(str(option), str(option).title()),
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="primary",
                        choice_index=str(option),
                    )
                )
            return actions

        if screen_type == "BOSS_REWARD" and screen_state.get("relics"):
            for index, relic in enumerate(screen_state["relics"]):
                command = f"choose {index}"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=relic.get("name", f"Relic {index}"),
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="primary",
                        choice_index=index,
                    )
                )
            return actions

        if items:
            for index, item in enumerate(items):
                label = (
                    item.get("name")
                    or item.get("reward_type")
                    or item.get("label")
                    or item.get("id")
                    or f"Option {index}"
                )
                command = f"choose {index}"
                actions.append(
                    LegalAction(
                        action_id=self._build_action_id(ActionType.CHOOSE, command),
                        label=str(label),
                        command=command,
                        action_type=ActionType.CHOOSE,
                        style="secondary",
                        choice_index=index,
                    )
                )
            return actions

        for index, choice in enumerate(game.get("choice_list", []) or []):
            command = f"choose {index}"
            actions.append(
                LegalAction(
                    action_id=self._build_action_id(ActionType.CHOOSE, command),
                    label=str(choice),
                    command=command,
                    action_type=ActionType.CHOOSE,
                    style="secondary",
                    choice_index=index,
                )
            )
        return actions

    @staticmethod
    def _build_action_id(action_type: ActionType, command: str) -> str:
        safe = "_".join(command.strip().lower().split())
        return f"{action_type.value}:{safe}"
