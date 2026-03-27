"""Enrich parsed model output with canonical operator commands (token → PLAY index, etc.)."""

from __future__ import annotations

from typing import Any

from src.agent_core.resolve import resolve_to_legal_command
from src.agent_core.schemas import StructuredCommandProposal
from src.domain.legal_command import is_command_legal
from src.domain.play_resolve import is_numeric_play


def command_steps_for_model_output(
    view_model: dict[str, Any] | None,
    model_commands: list[str],
    *,
    rationale: str = "",
) -> list[dict[str, Any]]:
    """
    One row per model command string: ``model`` (as emitted by the LLM / stub) and ``canonical``
    (CommunicationMod string) when it resolves against the current legal list.

    Token ``PLAY <uuid-prefix>`` rows resolve via the same rules as ``resolve_to_legal_command``.
    Numeric ``PLAY n`` that is already legal is shown as ``canonical == model`` for operator parity.
    """
    if not view_model or not model_commands:
        return []
    out: list[dict[str, Any]] = []
    for c in model_commands:
        s = str(c).strip()
        if not s:
            continue
        if s.upper().startswith("PLAY ") and is_numeric_play(s) and is_command_legal(
            view_model,
            s,
        ):
            out.append(
                {
                    "model": s,
                    "canonical": s,
                    "resolve_tag": "canonical_numeric_play",
                },
            )
            continue
        prop = StructuredCommandProposal(command=s, rationale=rationale)
        canon, tag = resolve_to_legal_command(
            view_model,
            prop,
            allow_fallback=False,
        )
        out.append(
            {
                "model": s,
                "canonical": canon,
                "resolve_tag": tag,
            },
        )
    return out
