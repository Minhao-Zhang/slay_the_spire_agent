"""C2: Project ingress → ViewModel. Optional FS read: ``data/processed`` for KB enrichment."""

from __future__ import annotations

from typing import Any

from src.domain.contracts.ingress import GameAdapterInput
from src.domain.contracts.view_model import ActionCandidate, HeaderView, ViewModel
from src.domain.state_projection.legal_actions import build_legal_actions
from src.domain.state_projection.kb_enrich import monster_kb_public
from src.domain.state_projection.screens import (
    build_combat_view,
    build_inventory_view,
    build_screen_view,
)


def project_state(ingress: GameAdapterInput) -> ViewModel:
    """Project validated ingress into a view model + legal actions."""
    game = ingress.game_state
    combat = game.get("combat_state")
    screen_type = str(game.get("screen_type") or "NONE")
    screen_state = game.get("screen_state") or {}
    if not isinstance(screen_state, dict):
        screen_state = {}

    if not ingress.in_game:
        return ViewModel(
            in_game=False,
            header=HeaderView.model_validate(
                {
                    "class": "Main Menu",
                    "floor": "-",
                    "gold": "-",
                    "hp_display": "-",
                    "energy": "-",
                    "turn": "-",
                },
            ),
            actions=[],
            combat=None,
            screen=None,
            inventory=None,
            map=None,
            sidebar=None,
            last_action=None,
        )

    hp_display = f"{game.get('current_hp', '?')}/{game.get('max_hp', '?')}"
    player = (combat.get("player") if combat else None) or {}
    header = HeaderView.model_validate(
        {
            "class": str(game.get("class", "?")),
            "floor": str(game.get("floor", "?")),
            "gold": str(game.get("gold", "?")),
            "hp_display": hp_display,
            "energy": str(player.get("energy", "-")) if combat else "-",
            "turn": str(combat.get("turn", "-")) if combat else "-",
        },
    )

    inventory = build_inventory_view(game)
    combat_vm = build_combat_view(combat) if combat else None
    screen_vm = build_screen_view(screen_type, screen_state, game, combat)

    map_vm: dict[str, Any] | None = None
    if game.get("map"):
        boss_name = game.get("act_boss")
        map_vm = {
            "nodes": game["map"],
            "current_node": screen_state.get("current_node") if screen_type == "MAP" else None,
            "next_nodes": screen_state.get("next_nodes") if screen_type == "MAP" else None,
            "boss_available": screen_state.get("boss_available", False) if screen_type == "MAP" else False,
            "boss_name": boss_name,
            "boss_kb": monster_kb_public(str(boss_name)) if boss_name else None,
        }

    sidebar = {
        "floor": game.get("floor"),
        "hp_display": hp_display,
        "gold": game.get("gold"),
        "relics": inventory["relics"],
        "potions": inventory["potions"],
    }

    actions = build_legal_actions(
        ingress.available_commands,
        game,
        combat,
        screen_type,
        screen_state,
    )

    return ViewModel(
        in_game=True,
        header=header,
        actions=actions,
        combat=combat_vm,
        screen=screen_vm,
        inventory=inventory,
        map=map_vm,
        sidebar=sidebar,
        last_action=None,
    )


def project_state_from_envelope(raw: dict[str, Any], last_action: Any = None) -> ViewModel:
    """Parse CommunicationMod envelope and project; attach ``last_action`` when present."""
    from src.domain.contracts.ingress import parse_ingress_envelope

    inner = raw.get("state", raw)
    action = raw.get("action", last_action)
    ingress = parse_ingress_envelope(raw)
    vm = project_state(ingress)
    return vm.model_copy(update={"last_action": action})
