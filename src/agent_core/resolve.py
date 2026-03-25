"""Map a structured proposal to a single legal CommunicationMod command."""

from __future__ import annotations

from typing import Any

from src.agent_core.schemas import StructuredCommandProposal
from src.decision_engine.proposal_logic import mock_propose_command
from src.domain.legal_command import is_command_legal


def resolve_to_legal_command(
    view_model: dict[str, Any] | None,
    proposal: StructuredCommandProposal,
) -> tuple[str | None, str]:
    """
    Return ``(command, rationale_tag)``.

    Order: exact legality → normalized match → first legal fallback (same as mock).
    """
    vm = view_model
    cmd = proposal.command
    if cmd and is_command_legal(vm, cmd):
        return " ".join(cmd.strip().split()), "resolved:direct"

    if cmd and vm:
        want = " ".join(cmd.strip().split()).lower()
        for a in vm.get("actions") or []:
            c = a.get("command")
            if c and " ".join(str(c).strip().split()).lower() == want:
                return str(c).strip(), "resolved:normalized"

    fb, tag = mock_propose_command(vm)
    if fb:
        return fb, f"fallback_first_legal:{tag}"
    return None, "no_legal_fallback"
