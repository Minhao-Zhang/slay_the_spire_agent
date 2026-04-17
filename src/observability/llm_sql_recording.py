"""Bridge Langfuse + SQL ``llm_call`` persistence after each LLM completion."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from src.agent.llm_context import LlmCallContext
from src.agent.schemas import TraceTokenUsage
from src.observability.langfuse_client import get_langfuse_client
from src.persistence.settings import get_persistence_settings
from src.persistence.sql_repository import get_sql_repository

logger = logging.getLogger(__name__)


def _usage_dict(u: TraceTokenUsage | None) -> dict[str, int | None]:
    if not u:
        return {}
    return {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "total_tokens": u.total_tokens,
        "cached_input_tokens": u.cached_input_tokens,
        "uncached_input_tokens": u.uncached_input_tokens,
    }


def persist_llm_completion(
    ctx: LlmCallContext | None,
    *,
    stage: str,
    model: str | None,
    system_prompt: str,
    user_blob: str,
    output_text: str,
    usage: TraceTokenUsage | None,
    latency_ms: int | None,
    status: str,
    error_code: str | None = None,
    round_index: int | None = None,
) -> None:
    if ctx is None:
        return
    run_key = (ctx.run_id or "").strip()
    if not run_key:
        return
    settings = get_persistence_settings()
    lf = get_langfuse_client()
    eff_stage = stage or ctx.stage
    ri = int(round_index if round_index is not None else ctx.round_index)
    combined = f"[system]\n{system_prompt}\n\n[user]\n{user_blob}"
    trace_hex = ctx.langfuse_trace_id
    if trace_hex and (len(trace_hex) != 32 or any(c not in "0123456789abcdef" for c in trace_hex)):
        trace_hex = None
    tid_base = trace_hex or lf.new_trace_id()
    meta = {
        **(ctx.tags or {}),
        "stage": eff_stage,
        "run_id": run_key,
        "user_id": run_key,
        "session_id": run_key,
        "prompt_profile": ctx.prompt_profile,
        "frame_id": ctx.frame_id,
        "event_index": ctx.event_index,
        "client_decision_id": ctx.client_decision_id,
        "decision_id": ctx.client_decision_id,
        "experiment_id": ctx.experiment_id,
    }
    ud = _usage_dict(usage)
    ltid, loid = lf.log_generation(
        trace_id=tid_base,
        name=eff_stage,
        input_text=combined,
        output_text=output_text or "",
        model=model or "",
        metadata=meta,
        usage=ud,
        latency_ms=latency_ms,
    )
    if not (settings.sql_shadow_or_primary and ctx.mirror_llm_to_sql):
        return
    repo = get_sql_repository()
    if repo is None:
        return
    try:
        repo.record_llm_call(
            {
                "id": str(uuid.uuid4()),
                "run_id": run_key,
                "frame_id": ctx.frame_id,
                "event_index": ctx.event_index,
                "state_id": ctx.state_id or "",
                "client_decision_id": ctx.client_decision_id or "",
                "turn_key": ctx.turn_key,
                "stage": eff_stage,
                "round_index": ri,
                "model": model,
                "reasoning_effort": ctx.reasoning_effort
                or (ctx.tags.get("reasoning_effort") if ctx.tags else None),
                "input_tokens": ud.get("input_tokens"),
                "cached_input_tokens": ud.get("cached_input_tokens"),
                "uncached_input_tokens": ud.get("uncached_input_tokens"),
                "output_tokens": ud.get("output_tokens"),
                "reasoning_tokens": ctx.tags.get("reasoning_tokens") if ctx.tags else None,
                "total_tokens": ud.get("total_tokens"),
                "latency_ms": latency_ms,
                "status": status,
                "error_code": error_code,
                "langfuse_trace_id": ltid,
                "langfuse_observation_id": loid,
                "prompt_profile": ctx.prompt_profile,
                "knowledge_version_id": None,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQL llm_call record failed: %s", exc)


def serialize_messages_for_log(messages: list[dict[str, Any]], *, limit: int = 80_000) -> str:
    try:
        raw = json.dumps(messages, ensure_ascii=False, default=str)
    except TypeError:
        raw = str(messages)
    if len(raw) > limit:
        return raw[:limit] + "\n…(truncated)…"
    return raw
