"""LangGraph nodes: bounded episodic log + long-term namespace writes."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.memory.runtime import get_app_memory_store


def memory_update_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    """
    Append one episodic record (``state_id``, header hints) and trim to ``memory_max_turns``.

    Writes idempotent ``last_turn`` under namespace ``("strategy", <class>)`` for retrieval
    across runs (same process).
    """
    log = list(state.get("memory_log") or [])
    cursor = int(state.get("memory_seq_cursor") or 0) + 1
    vm = state.get("view_model")
    sid = state.get("state_id")
    header = (vm or {}).get("header") or {}
    entry: dict[str, Any] = {
        "state_id": sid,
        "class": header.get("class"),
        "floor": header.get("floor"),
        "seq": cursor,
    }
    log.append(entry)
    conf = config.get("configurable") or {}
    max_n = int(conf.get("memory_max_turns", 32))
    if max_n < 1:
        max_n = 32
    if len(log) > max_n:
        log = log[-max_n:]

    cls = str(header.get("class") or "unknown")
    ns = ("strategy", cls)
    get_app_memory_store().put(
        ns,
        "last_turn",
        {"state_id": sid, "floor": header.get("floor")},
    )

    return {"memory_log": log, "memory_seq_cursor": cursor}
