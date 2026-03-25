"""Derive legal ActionCandidate rows from game_state + available_commands (pure)."""

from __future__ import annotations

from typing import Any

from src.domain.contracts.view_model import ActionCandidate, ActionStyle

_COMMAND_BUTTONS: list[tuple[str, str, str, ActionStyle]] = [
    ("proceed", "PROCEED", "PROCEED", "primary"),
    ("end", "END TURN", "END", "danger"),
    ("cancel", "CANCEL", "CANCEL", "secondary"),
    ("leave", "LEAVE", "LEAVE", "secondary"),
    ("skip", "SKIP", "SKIP", "secondary"),
    ("confirm", "CONFIRM", "CONFIRM", "primary"),
    ("return", "RETURN", "RETURN", "secondary"),
]

_REST_OPTION_META: dict[str, tuple[str, str]] = {
    "rest": ("Rest", "Heal for 30% of your max HP."),
    "smith": ("Smith", "Upgrade a card in your deck."),
    "lift": ("Lift", "Gain 1 Strength (Girya)."),
    "toke": ("Toke", "Remove a card from your deck (Peace Pipe)."),
    "dig": ("Dig", "Obtain a random relic (Shovel)."),
    "recall": ("Recall", "Add a card to your deck (Dream Catcher)."),
}


def build_legal_actions(
    commands: list[str],
    game: dict[str, Any],
    combat: dict[str, Any] | None,
    screen_type: str,
    screen_state: dict[str, Any],
) -> list[ActionCandidate]:
    command_set = set(commands)
    out: list[ActionCandidate] = []

    for cmd_key, label, command, style in _COMMAND_BUTTONS:
        if cmd_key in command_set:
            out.append(ActionCandidate(label=label, command=command, style=style))

    if "play" in command_set and combat:
        out.extend(_play_actions(combat))

    if "potion" in command_set:
        out.extend(_potion_actions(game, combat))

    if "choose" in command_set:
        out.extend(
            _choose_actions(screen_type, screen_state, game),
        )

    return out


def _play_actions(combat: dict[str, Any]) -> list[ActionCandidate]:
    out: list[ActionCandidate] = []
    hand = combat.get("hand", [])
    energy = (combat.get("player") or {}).get("energy", 0)
    monsters = combat.get("monsters", [])
    for i, card in enumerate(hand):
        if not card.get("is_playable") or card.get("cost", 99) > energy:
            continue
        uuid_full = card.get("uuid", "") or ""
        card_uuid_token = uuid_full[:6] if uuid_full else ""
        if card.get("has_target"):
            for mi, m in enumerate(monsters):
                if m.get("is_gone") or m.get("half_dead"):
                    continue
                out.append(
                    ActionCandidate(
                        label=f"{card['name']} → {m['name']}",
                        command=f"PLAY {i + 1} {mi}",
                        style="success",
                        card_uuid_token=card_uuid_token or None,
                        hand_index=i + 1,
                        monster_index=mi,
                    ),
                )
        else:
            out.append(
                ActionCandidate(
                    label=card["name"],
                    command=f"PLAY {i + 1}",
                    style="primary",
                    card_uuid_token=card_uuid_token or None,
                    hand_index=i + 1,
                ),
            )
    return out


def _potion_actions(
    game: dict[str, Any],
    combat: dict[str, Any] | None,
) -> list[ActionCandidate]:
    out: list[ActionCandidate] = []
    for i, pot in enumerate(game.get("potions", [])):
        if pot.get("can_use"):
            if pot.get("requires_target") and combat:
                for mi, m in enumerate(combat.get("monsters", [])):
                    if m.get("is_gone") or m.get("half_dead"):
                        continue
                    out.append(
                        ActionCandidate(
                            label=f"Use {pot['name']} → {m['name']}",
                            command=f"POTION USE {i} {mi}",
                            style="primary",
                        ),
                    )
            else:
                out.append(
                    ActionCandidate(
                        label=f"Use {pot['name']}",
                        command=f"POTION USE {i}",
                        style="primary",
                    ),
                )
        if pot.get("can_discard"):
            out.append(
                ActionCandidate(
                    label=f"Discard {pot['name']}",
                    command=f"POTION DISCARD {i}",
                    style="secondary",
                ),
            )
    return out


def _choose_actions(
    screen_type: str,
    s: dict[str, Any],
    game: dict[str, Any],
) -> list[ActionCandidate]:
    out: list[ActionCandidate] = []
    items = s.get("hand") or s.get("cards") or s.get("relics") or s.get("rewards") or s.get("potions")

    if screen_type == "MAP" and s.get("next_nodes"):
        for i, n in enumerate(s["next_nodes"]):
            out.append(
                ActionCandidate(
                    label=f"GO: {n.get('symbol', '?')}",
                    command=f"choose {i}",
                    style="primary",
                ),
            )
        if s.get("boss_available"):
            out.append(
                ActionCandidate(
                    label="FIGHT BOSS",
                    command="choose boss",
                    style="danger",
                ),
            )

    elif screen_type == "EVENT" and s.get("options"):
        for i, o in enumerate(s["options"]):
            if o.get("disabled"):
                continue
            out.append(
                ActionCandidate(
                    label=o.get("label", f"Select {i}"),
                    command=f"choose {i}",
                    style="primary",
                ),
            )

    elif screen_type == "COMBAT_REWARD" and s.get("rewards"):
        for i, r in enumerate(s["rewards"]):
            rtype = r.get("reward_type", "")
            if rtype == "GOLD":
                label = f"Take {r.get('gold', '?')} Gold"
            elif rtype == "POTION":
                label = f"Take {r.get('potion', {}).get('name', 'Potion')}"
            elif rtype == "RELIC":
                label = f"Take {r.get('relic', {}).get('name', 'Relic')}"
            elif rtype == "CARD":
                label = "Reward: Card Draft"
            else:
                label = str(rtype)
            out.append(
                ActionCandidate(label=label, command=f"choose {i}", style="secondary"),
            )

    elif screen_type == "SHOP_ROOM":
        for choice in game.get("choice_list", []):
            out.append(
                ActionCandidate(
                    label=str(choice).title(),
                    command=f"choose {choice}",
                    style="primary",
                ),
            )

    elif screen_type == "SHOP_SCREEN":
        for i, c in enumerate(s.get("cards", [])):
            out.append(
                ActionCandidate(
                    label=f"Buy {c.get('name', '?')} ({c.get('price', '?')}g)",
                    command=f"choose {c.get('name', i)}",
                    style="secondary",
                ),
            )
        for r in s.get("relics", []):
            out.append(
                ActionCandidate(
                    label=f"Buy {r.get('name', '?')} ({r.get('price', '?')}g)",
                    command=f"choose {r.get('name', '?')}",
                    style="secondary",
                ),
            )
        for p in s.get("potions", []):
            out.append(
                ActionCandidate(
                    label=f"Buy {p.get('name', '?')} ({p.get('price', '?')}g)",
                    command=f"choose {p.get('name', '?')}",
                    style="secondary",
                ),
            )
        if s.get("purge_available"):
            out.append(
                ActionCandidate(
                    label=f"Remove Card ({s.get('purge_cost', '?')}g)",
                    command="choose purge",
                    style="danger",
                ),
            )

    elif screen_type == "CHEST":
        out.append(
            ActionCandidate(label="Open Chest", command="choose open", style="primary"),
        )

    elif screen_type == "REST" and s.get("rest_options"):
        for o in s["rest_options"]:
            label, _ = _REST_OPTION_META.get(o, (str(o).title(), ""))
            out.append(
                ActionCandidate(label=label, command=f"choose {o}", style="primary"),
            )

    elif screen_type == "BOSS_REWARD" and s.get("relics"):
        for i, r in enumerate(s["relics"]):
            out.append(
                ActionCandidate(
                    label=r.get("name", f"Relic {i}"),
                    command=f"choose {i}",
                    style="primary",
                ),
            )

    elif items:
        for i, it in enumerate(items):
            label = (
                it.get("name")
                or it.get("reward_type")
                or it.get("label")
                or it.get("id")
                or f"Option {i}"
            )
            out.append(
                ActionCandidate(label=str(label), command=f"choose {i}", style="secondary"),
            )

    else:
        for i, choice in enumerate(game.get("choice_list", [])):
            out.append(
                ActionCandidate(label=str(choice), command=f"choose {i}", style="secondary"),
            )

    return out
