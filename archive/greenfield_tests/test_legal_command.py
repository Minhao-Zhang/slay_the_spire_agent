from __future__ import annotations

import pytest

from src.domain.legal_command import canonical_legal_command


def test_canonical_matches_action_list_string() -> None:
    vm = {"actions": [{"command": "END"}]}
    assert canonical_legal_command(vm, "end") == "END"


def test_canonical_raises() -> None:
    with pytest.raises(ValueError):
        canonical_legal_command({"actions": []}, "END")
