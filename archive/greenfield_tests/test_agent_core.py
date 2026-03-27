from __future__ import annotations

import json

import pytest

from src.agent_core.parse import parse_proposal_json
from src.agent_core.resolve import normalized_command_list, resolve_to_legal_command
from src.agent_core.schemas import StructuredCommandProposal


def test_parse_proposal_plain_json() -> None:
    p = parse_proposal_json('{"command": "END", "rationale": "x"}')
    assert p.command == "END"
    assert p.rationale == "x"


def test_parse_proposal_fenced() -> None:
    raw = '```json\n{"command": "play 0", "rationale": ""}\n```'
    p = parse_proposal_json(raw)
    assert p.command == "play 0"


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="invalid"):
        parse_proposal_json("not json")


def test_resolve_direct_legal() -> None:
    vm = {"actions": [{"command": "END", "label": "End"}]}
    prop = StructuredCommandProposal(command="END", rationale="")
    cmd, tag = resolve_to_legal_command(vm, prop)
    assert cmd == "END"
    assert "direct" in tag


def test_resolve_fallback_when_illegal() -> None:
    vm = {"actions": [{"command": "END", "label": "End"}]}
    prop = StructuredCommandProposal(command="NOPE", rationale="")
    cmd, tag = resolve_to_legal_command(vm, prop)
    assert cmd == "END"
    assert "fallback" in tag


def test_resolve_no_actions() -> None:
    cmd, tag = resolve_to_legal_command({}, StructuredCommandProposal(command="END"))
    assert cmd is None


def test_resolve_no_fallback() -> None:
    vm = {"actions": [{"command": "END", "label": "End"}]}
    prop = StructuredCommandProposal(command="NOPE", rationale="")
    cmd, tag = resolve_to_legal_command(vm, prop, allow_fallback=False)
    assert cmd is None
    assert "no_legal_match" in tag


def test_normalized_command_list_prefers_commands_array() -> None:
    p = StructuredCommandProposal(
        command="SKIP",
        commands=["END", "WAIT"],
        rationale="",
    )
    assert normalized_command_list(p) == ["END", "WAIT"]
