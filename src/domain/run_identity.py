"""Derive stable LangGraph thread_id and display run_seed from CommunicationMod ingress."""

from __future__ import annotations

from typing import Any

from src.domain.contracts.ingress import parse_ingress_envelope

MENU_RUN_SEED = "menu"
MENU_THREAD_ID = "run-menu"


def _canonical_seed(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, float):
        if raw != raw:  # NaN
            return None
        return str(int(raw))
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            return str(int(s, 10))
        except ValueError:
            return s
    return None


def extract_run_seed_and_thread_id(ingress_body: dict[str, Any]) -> tuple[str, str]:
    """
    Returns ``(run_seed, graph_thread_id)``.

    - Not in-game → ``("menu", "run-menu")``.
    - In-game with usable ``game_state["seed"]`` → ``(<canonical>, "run-<canonical>")``.
    - In-game but missing seed → ``("menu", "run-menu")`` (add seed on wire for per-run isolation).
    """
    parsed = parse_ingress_envelope(ingress_body)
    if not parsed.in_game:
        return (MENU_RUN_SEED, MENU_THREAD_ID)
    canonical = _canonical_seed(parsed.game_state.get("seed") if isinstance(parsed.game_state, dict) else None)
    if canonical is None:
        return (MENU_RUN_SEED, MENU_THREAD_ID)
    return (canonical, f"run-{canonical}")
