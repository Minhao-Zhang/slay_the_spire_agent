from __future__ import annotations

from src.agent_core.resolve_display import command_steps_for_model_output


def test_command_steps_token_to_canonical() -> None:
    vm = {
        "actions": [
            {
                "command": "PLAY 3 0",
                "card_uuid_token": "2ac45d01",
                "monster_index": 0,
                "label": "Bash",
            },
            {"command": "END", "label": "End"},
        ],
    }
    steps = command_steps_for_model_output(
        vm,
        ["PLAY 2ac45d01 0", "END"],
        rationale="",
    )
    assert len(steps) == 2
    assert steps[0]["model"] == "PLAY 2ac45d01 0"
    assert steps[0]["canonical"] == "PLAY 3 0"
    assert steps[0]["resolve_tag"] == "resolved:play_token"
    assert steps[1]["canonical"] == "END"
