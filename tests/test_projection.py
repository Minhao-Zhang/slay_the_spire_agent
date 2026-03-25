from __future__ import annotations

import json
from pathlib import Path

from src.domain.contracts.ingress import parse_ingress_envelope
from src.domain.contracts.state_id import compute_state_id
from src.domain.state_projection import project_state, project_state_from_envelope

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    path = _FIXTURES / name
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_menu_not_in_game() -> None:
    raw = _load("ingress_menu.json")
    ingress = parse_ingress_envelope(raw)
    vm = project_state(ingress)
    assert vm.in_game is False
    assert vm.header is not None
    assert vm.header.class_ == "Main Menu"
    assert vm.actions == []


def test_combat_legal_actions_include_end_and_play() -> None:
    raw = _load("ingress_combat.json")
    ingress = parse_ingress_envelope(raw)
    vm = project_state(ingress)
    cmds = [a.command for a in vm.actions]
    assert "END" in cmds
    assert "PLAY 1 0" in cmds


def test_project_envelope_with_action() -> None:
    envelope = {"state": _load("ingress_combat.json"), "action": "PREV"}
    vm = project_state_from_envelope(envelope)
    assert vm.last_action == "PREV"
    assert vm.in_game is True


def test_state_id_round_trip_fixture() -> None:
    raw = _load("ingress_combat.json")
    ingress = parse_ingress_envelope(raw)
    sid = compute_state_id(ingress)
    assert sid.startswith("v1-")
    assert len(sid) > 8


def test_projection_enriches_hand_and_monster_with_kb() -> None:
    raw = _load("ingress_combat.json")
    ingress = parse_ingress_envelope(raw)
    vm = project_state(ingress)
    assert vm.combat is not None
    strike = vm.combat["hand"][0]
    assert strike.get("kb") is not None
    assert "description" in strike["kb"]
    assert len(str(strike["kb"]["description"])) > 0
    cultist = vm.combat["monsters"][0]
    assert cultist.get("kb") is not None
    kb = cultist["kb"]
    assert kb.get("ai") or kb.get("moves")
