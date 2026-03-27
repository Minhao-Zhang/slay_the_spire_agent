from __future__ import annotations

from src.agent_core.resolve import resolve_to_legal_command
from src.agent_core.schemas import StructuredCommandProposal
from src.domain.card_token import CARD_TOKEN_LEN, card_uuid_token
from src.domain.play_resolve import (
    is_numeric_play,
    resolve_play_with_token,
    resolve_token_play,
    token_play_command_for_action,
)


def test_card_token_len() -> None:
    assert CARD_TOKEN_LEN == 8


def test_card_uuid_token_strips_hyphens() -> None:
    assert card_uuid_token("92e7bbdb-07e0-4f17-ad63-cb2539622651") == "92e7bbdb"
    assert card_uuid_token("abcdef123456") == "abcdef12"


def test_is_numeric_play() -> None:
    assert is_numeric_play("PLAY 1")
    assert is_numeric_play("PLAY 12 0")
    assert not is_numeric_play("PLAY abcdef12")


def test_resolve_token_play_targeted() -> None:
    legal = [
        {
            "command": "PLAY 1 0",
            "card_uuid_token": "abcdef12",
            "monster_index": 0,
        },
    ]
    assert resolve_token_play("PLAY abcdef12 0", legal) == "PLAY 1 0"
    assert resolve_token_play("play ABCDEF12 0", legal) == "PLAY 1 0"
    assert resolve_play_with_token("PLAY abcdef12 0", legal) == "PLAY 1 0"


def test_resolve_token_play_targeted_omits_monster_index() -> None:
    """LLM often returns ``PLAY <token>`` only; map to the sole legal targeted row."""
    legal = [
        {
            "command": "PLAY 3 0",
            "card_uuid_token": "f850bbd5",
            "monster_index": 0,
        },
    ]
    assert resolve_token_play("PLAY f850bbd5", legal) == "PLAY 3 0"
    assert resolve_play_with_token("PLAY f850bbd5", legal) == "PLAY 3 0"


def test_resolve_token_play_untargeted_with_null_monster_in_dict() -> None:
    legal = [
        {
            "command": "PLAY 2",
            "card_uuid_token": "feedface",
            "hand_index": 2,
            "monster_index": None,
        },
    ]
    assert resolve_token_play("PLAY feedface", legal) == "PLAY 2"


def test_token_play_command_for_action() -> None:
    assert (
        token_play_command_for_action(
            {
                "command": "PLAY 2 0",
                "card_uuid_token": "AB12CD34",
                "monster_index": 0,
            },
        )
        == "PLAY ab12cd34 0"
    )
    assert token_play_command_for_action({"command": "PLAY 1", "card_uuid_token": "ffeeddcc"}) == "PLAY ffeeddcc"


def test_resolve_token_play_untargeted() -> None:
    legal = [
        {"command": "PLAY 2", "card_uuid_token": "feedface"},
    ]
    assert resolve_token_play("PLAY feedface", legal) == "PLAY 2"


def test_resolve_numeric_play_rejected_without_fallback() -> None:
    vm = {
        "actions": [
            {"command": "PLAY 1 0", "label": "x", "card_uuid_token": "abcdef12", "monster_index": 0},
            {"command": "END", "label": "e"},
        ],
    }
    prop = StructuredCommandProposal(command="PLAY 1 0", rationale="")
    cmd, tag = resolve_to_legal_command(vm, prop, allow_fallback=False)
    assert cmd is None
    assert tag == "numeric_play_disallowed"


def test_resolve_numeric_play_policy_fallback() -> None:
    vm = {
        "actions": [
            {"command": "END", "label": "e"},
            {"command": "PLAY 1 0", "label": "x", "card_uuid_token": "abcdef12", "monster_index": 0},
        ],
    }
    prop = StructuredCommandProposal(command="PLAY 1 0", rationale="")
    cmd, tag = resolve_to_legal_command(vm, prop, allow_fallback=True)
    assert cmd == "END"
    assert "replaced_numeric" in tag


def test_resolve_to_legal_command_play_token() -> None:
    vm = {
        "actions": [
            {"command": "PLAY 1 0", "label": "x", "card_uuid_token": "abcdef12", "monster_index": 0},
            {"command": "END", "label": "e"},
        ],
    }
    prop = StructuredCommandProposal(command="PLAY abcdef12 0", rationale="")
    cmd, tag = resolve_to_legal_command(vm, prop)
    assert cmd == "PLAY 1 0"
    assert tag == "resolved:play_token"


def test_resolve_to_legal_command_play_token_no_target_index() -> None:
    vm = {
        "actions": [
            {"command": "END", "label": "e"},
            {"command": "PLAY 1 0", "label": "x", "card_uuid_token": "abcdef12", "monster_index": 0},
        ],
    }
    prop = StructuredCommandProposal(command="PLAY abcdef12", rationale="")
    cmd, tag = resolve_to_legal_command(vm, prop)
    assert cmd == "PLAY 1 0"
    assert tag == "resolved:play_token"
