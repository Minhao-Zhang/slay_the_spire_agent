"""FastAPI app: debug ingress projection + WebSocket fan-out for `apps/web`."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from collections import deque
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from src.domain.contracts import compute_state_id, parse_ingress_envelope
from src.domain.contracts.ingress import GameAdapterInput
from src.domain.legal_command import canonical_legal_command
from src.domain.state_projection import project_state
from src.control_api import agent_runtime
from src.control_api.history import router as history_router
from src.trace_telemetry.runtime import get_app_trace_store, shutdown_trace_store
from src.trace_telemetry.schema import TRACE_SCHEMA_VERSION


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    yield
    agent_runtime.shutdown_checkpoint_resources()
    shutdown_trace_store()


app = FastAPI(
    title="Slay the Spire Agent — control API",
    version="0.1.0",
    lifespan=_lifespan,
)
app.include_router(history_router)

_lock = threading.Lock()
_snapshot: dict[str, Any] = {
    "view_model": None,
    "state_id": None,
    "ingress": None,
    "error": None,
    "agent": None,
}
_ws_clients: set[WebSocket] = set()
_broadcast_lock = asyncio.Lock()

_instruction_lock = threading.Lock()
_manual_command_queue: deque[str] = deque()


def _enqueue_manual_command(cmd: str) -> None:
    with _lock:
        vm = _snapshot.get("view_model")
    if vm is None:
        return
    try:
        canon = canonical_legal_command(vm, cmd)
    except ValueError:
        sys.stderr.write(
            f"[control_api] dropped illegal graph/manual command: {cmd!r}\n",
        )
        return
    with _instruction_lock:
        _manual_command_queue.append(canon)


def _parse_ingress_http(body: dict[str, Any]) -> GameAdapterInput:
    try:
        return parse_ingress_envelope(body)
    except (TypeError, ValueError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _is_snapshot_unchanged(new_state_id: str) -> bool:
    with _lock:
        return (
            new_state_id == _snapshot.get("state_id")
            and _snapshot.get("view_model") is not None
        )


def _apply_ingress_body(
    body: dict[str, Any],
    *,
    ingress: GameAdapterInput | None = None,
) -> tuple[dict[str, Any], str]:
    if ingress is None:
        ingress = _parse_ingress_http(body)
    action = body.get("action")
    vm = project_state(ingress)
    if action is not None:
        vm = vm.model_copy(update={"last_action": action})
    sid = compute_state_id(ingress)
    vm_json = vm.model_dump(mode="json", by_alias=True)
    with _lock:
        global _snapshot
        _snapshot = {
            "view_model": vm_json,
            "state_id": sid,
            "ingress": body,
            "error": None,
        }
    return vm_json, sid


def _snapshot_for_client() -> dict[str, Any]:
    """
    Full snapshot for HTTP/WS clients. Always attach ``get_agent_status()`` so
    env-derived fields (``proposer``, ``llm_backend``, ``memory_max_turns``) are
    current; raw ``step_ingress`` summaries omit those keys and would otherwise
    make the UI fall back to mock/stub.
    """
    with _lock:
        out = dict(_snapshot)
    out["agent"] = agent_runtime.get_agent_status()
    return out


async def _broadcast_snapshot() -> None:
    payload = _snapshot_for_client()
    msg = {"type": "snapshot", "payload": payload}
    async with _broadcast_lock:
        dead: list[WebSocket] = []
        for ws in list(_ws_clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_clients.discard(ws)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/debug/trace")
def get_debug_trace(limit: int = 100, thread_id: str | None = None) -> dict[str, Any]:
    lim = max(1, min(int(limit), 500))
    tid = thread_id.strip() if isinstance(thread_id, str) and thread_id.strip() else None
    ev = get_app_trace_store().list_events(thread_id=tid)
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "events": ev[-lim:],
        "count": len(ev),
    }


@app.get("/api/debug/snapshot")
def get_snapshot() -> dict[str, Any]:
    return _snapshot_for_client()


@app.get("/api/agent/status")
def get_agent_status_route() -> dict[str, Any]:
    return agent_runtime.get_agent_status()


@app.post("/api/agent/resume")
async def post_agent_resume(body: dict[str, Any]) -> dict[str, Any]:
    try:
        agent_runtime.resume_agent(body, _enqueue_manual_command)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    with _lock:
        _snapshot["agent"] = agent_runtime.get_agent_status()
    await _broadcast_snapshot()
    return agent_runtime.get_agent_status()


@app.post("/api/agent/retry")
async def post_agent_retry() -> dict[str, Any]:
    """
    Re-run the LangGraph agent on the snapshot's last ingress (same game state).

    Skips the ``/api/debug/ingress`` unchanged-state short-circuit so LLM / mock
    proposal runs again. If approval is pending, rejects first then re-ingests.
    """
    with _lock:
        body = _snapshot.get("ingress")
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400,
            detail="No ingress in snapshot; load a state via debug ingress first.",
        )
    agent_runtime.retry_agent(body, _enqueue_manual_command)
    with _lock:
        _snapshot["agent"] = agent_runtime.get_agent_status()
    await _broadcast_snapshot()
    return _snapshot_for_client()


@app.post("/api/debug/ingress")
async def post_debug_ingress(body: dict[str, Any]) -> dict[str, Any]:
    ingress = _parse_ingress_http(body)
    new_sid = compute_state_id(ingress)
    if _is_snapshot_unchanged(new_sid):
        return _snapshot_for_client()
    _apply_ingress_body(body, ingress=ingress)
    agent_runtime.step_ingress(body, _enqueue_manual_command)
    with _lock:
        _snapshot["agent"] = agent_runtime.get_agent_status()
    await _broadcast_snapshot()
    return _snapshot_for_client()


@app.post("/api/debug/manual_command")
def post_manual_command(body: dict[str, Any]) -> dict[str, Any]:
    raw = body.get("command")
    if not isinstance(raw, str) or not raw.strip():
        raise HTTPException(status_code=400, detail="command (non-empty string) required")
    cmd = " ".join(raw.strip().split())
    with _lock:
        vm = _snapshot.get("view_model")
    if vm is None:
        raise HTTPException(
            status_code=400,
            detail="no projection yet; POST /api/debug/ingress first",
        )
    try:
        canon = canonical_legal_command(vm, cmd)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"command not legal: {e}") from e
    with _instruction_lock:
        _manual_command_queue.append(canon)
        depth = len(_manual_command_queue)
    return {"ok": True, "queued": depth, "command": canon}


@app.get("/api/debug/poll_instruction")
def poll_instruction() -> dict[str, Any]:
    with _instruction_lock:
        manual = _manual_command_queue.popleft() if _manual_command_queue else None
    return {
        "manual_action": manual,
        "approved_action": None,
        "agent_mode": agent_runtime.agent_mode(),
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _ws_clients.add(ws)
    try:
        await ws.send_json({"type": "snapshot", "payload": _snapshot_for_client()})
        while True:
            # Client may send ping messages or new ingress JSON for live debug.
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "detail": "invalid JSON"})
                continue
            if data.get("type") == "debug_ingress" and "body" in data:
                wb = data["body"]
                if not isinstance(wb, dict):
                    await ws.send_json({"type": "error", "detail": "body must be object"})
                    continue
                try:
                    ingress = parse_ingress_envelope(wb)
                except (TypeError, ValueError, ValidationError) as e:
                    await ws.send_json({"type": "error", "detail": str(e)})
                    continue
                new_sid = compute_state_id(ingress)
                if not _is_snapshot_unchanged(new_sid):
                    _apply_ingress_body(wb, ingress=ingress)
                    agent_runtime.step_ingress(wb, _enqueue_manual_command)
                    with _lock:
                        _snapshot["agent"] = agent_runtime.get_agent_status()
                    await _broadcast_snapshot()
                await ws.send_json({"type": "snapshot", "payload": _snapshot_for_client()})
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


def get_app() -> FastAPI:
    return app
