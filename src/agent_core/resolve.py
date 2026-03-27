"""Map a structured proposal to a single legal CommunicationMod command."""



from __future__ import annotations



from typing import Any



from src.agent_core.schemas import StructuredCommandProposal

from src.decision_engine.proposal_logic import mock_propose_command

from src.domain.legal_command import is_command_legal

from src.domain.play_resolve import (

    is_numeric_play,

    resolve_play_with_token,

)





def normalized_command_list(proposal: StructuredCommandProposal) -> list[str]:

    """Prefer ``commands`` when present and non-empty; otherwise ``[command]``."""

    if proposal.commands:

        out = [

            str(c).strip()

            for c in proposal.commands

            if c is not None and str(c).strip() != ""

        ]

        if out:

            return out

    if proposal.command is not None and str(proposal.command).strip() != "":

        return [str(proposal.command).strip()]

    return []





def resolve_to_legal_command(

    view_model: dict[str, Any] | None,

    proposal: StructuredCommandProposal,

    *,

    allow_fallback: bool = True,

) -> tuple[str | None, str]:

    """

    Return ``(command, rationale_tag)``.



    Card plays: only ``PLAY <token>`` / ``PLAY <token> <target>`` (see ``CARD_TOKEN_LEN``).

    Numeric ``PLAY n`` / ``PLAY n m`` from model output are rejected (optional policy fallback).



    Non-PLAY: exact legal → case-normalized match → mock fallback.

    """

    vm = view_model

    cmd_raw = proposal.command

    if not cmd_raw or not str(cmd_raw).strip():

        if not allow_fallback:

            return None, "no_legal_match"

        fb, tag = mock_propose_command(vm)

        if fb:

            return " ".join(str(fb).strip().split()), f"fallback_first_legal:{tag}"

        return None, "no_legal_fallback"



    cmd = " ".join(str(cmd_raw).strip().split())

    is_play = cmd.upper().startswith("PLAY ")



    if is_play and is_numeric_play(cmd):

        if allow_fallback:

            fb, tag = mock_propose_command(vm)

            if fb:

                return (

                    " ".join(str(fb).strip().split()),

                    f"replaced_numeric_play_with_policy:{tag}",

                )

        return None, "numeric_play_disallowed"



    if not is_play:

        if vm and is_command_legal(vm, cmd):

            return cmd, "resolved:direct"

        if vm:

            want = " ".join(cmd.strip().split()).lower()

            for a in vm.get("actions") or []:

                c = a.get("command")

                if c and " ".join(str(c).strip().split()).lower() == want:

                    return str(c).strip(), "resolved:normalized"

        if not allow_fallback:

            return None, "no_legal_match"

        fb, tag = mock_propose_command(vm)

        if fb:

            return " ".join(str(fb).strip().split()), f"fallback_first_legal:{tag}"

        return None, "no_legal_fallback"



    actions = (vm.get("actions") or []) if vm else []

    resolved_play = resolve_play_with_token(cmd, actions)

    if resolved_play and vm and is_command_legal(vm, resolved_play):

        return resolved_play.strip(), "resolved:play_token"



    if not allow_fallback:

        return None, "no_legal_match"

    fb, tag = mock_propose_command(vm)

    if fb:

        return " ".join(str(fb).strip().split()), f"fallback_first_legal:{tag}"

    return None, "no_legal_fallback"


