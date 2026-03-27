import json
import os
from copy import deepcopy
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.agent.config import get_agent_config, load_system_prompt
from src.agent.tracing import build_state_id
from src.repo_paths import REPO_ROOT
from src.ui.state_processor import process_state

app = FastAPI()

manual_actions_queue: list[str] = []

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
LOGS_DIR = os.path.join(str(REPO_ROOT), "logs")
AGENT_CONFIG = get_agent_config()
SYSTEM_PROMPT = load_system_prompt()

ai_runtime: dict[str, Any] = {
    "mode": AGENT_CONFIG.default_mode,
    "latest_state_id": "",
    "latest_trace": None,
    "trace_history": [],
    "approved_action": None,
    "ai_enabled": False,
    "ai_status": "unknown",
    "ai_api_style": "",
    "ai_status_message": "",
}

# Last envelope or raw ingress (CommunicationMod JSON) for React monitor / debug paste.
_last_ingress_body: dict[str, Any] | None = None


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


def _inner_game_payload(data: dict[str, Any]) -> dict[str, Any]:
    inner = data.get("state", data)
    return inner if isinstance(inner, dict) else {}


def _react_snapshot_state_id(
    data: dict[str, Any] | None,
    meta_state_id: str,
) -> str:
    if meta_state_id:
        return meta_state_id
    inner = _inner_game_payload(data or {})
    if inner:
        return build_state_id(inner)
    return ""


def _trace_as_dict(trace: Any) -> dict[str, Any] | None:
    if trace is None:
        return None
    if isinstance(trace, dict):
        return trace
    if hasattr(trace, "model_dump"):
        return trace.model_dump(mode="json")
    return None


def _trace_to_proposal(trace: dict[str, Any] | None) -> dict[str, Any] | None:
    if not trace:
        return None
    val = trace.get("validation")
    err = None
    if isinstance(val, dict):
        err = val.get("error") or None
    if not err:
        err_raw = trace.get("error")
        err = err_raw if err_raw else None
    raw = (trace.get("raw_output") or "").strip()
    if not raw:
        rt = (trace.get("reasoning_text") or "").strip()
        rs = (trace.get("response_text") or "").strip()
        chunks = [x for x in (rt, rs) if x]
        raw = "\n\n".join(chunks)
    return {
        "llm_raw": raw or None,
        "parsed_model": trace.get("parsed_proposal"),
        "command": trace.get("final_decision"),
        "rationale": (trace.get("reasoning_text") or None)
        or None,
        "status": str(trace.get("status") or trace.get("approval_status") or ""),
        "error_reason": str(err) if err else None,
        "resolve_tag": "legacy:trace",
        "for_state_id": trace.get("state_id"),
    }


def _pending_approval_from_trace(
    trace: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not trace or trace.get("status") != "awaiting_approval":
        return None
    seq = list(trace.get("final_decision_sequence") or [])
    head = trace.get("final_decision") or (seq[0] if seq else None)
    tail = seq[1:] if len(seq) > 1 else []
    if not head:
        return None
    return {
        "interrupt": {
            "state_id": trace.get("state_id"),
            "command": head,
            "command_queue": tail or None,
        },
        "thread_id": None,
    }


def _build_agent_snapshot() -> dict[str, Any]:
    t = _trace_as_dict(ai_runtime.get("latest_trace"))
    pending = _pending_approval_from_trace(t)
    api_style = str(ai_runtime.get("ai_api_style") or "").strip()
    llm_backend = api_style if api_style else (
        "openai" if ai_runtime.get("ai_enabled") else "off"
    )
    agent_err = None
    if t and t.get("status") == "error" and t.get("error"):
        agent_err = str(t.get("error"))
    elif t and isinstance(t.get("validation"), dict):
        ve = t["validation"].get("error")
        if ve and t.get("status") in {"invalid", "error"}:
            agent_err = str(ve)

    interrupt = (pending or {}).get("interrupt") if pending else None
    queue = None
    if isinstance(interrupt, dict):
        queue = interrupt.get("command_queue")

    return {
        "pending_approval": pending,
        "command_queue": queue,
        "emitted_command": None,
        "proposal": _trace_to_proposal(t),
        "failure_streak": 0,
        "decision_trace": [],
        "awaiting_interrupt": bool(pending),
        "agent_mode": ai_runtime.get("mode"),
        "thread_id": None,
        "run_seed": None,
        "ingress_derived_thread_id": None,
        "pending_graph_thread_id": None,
        "proposer": "legacy",
        "llm_backend": llm_backend,
        "agent_error": agent_err,
    }


def _build_react_snapshot_payload() -> dict[str, Any]:
    vm: dict[str, Any] | None = None
    err_msg: str | None = None
    state_id = str(ai_runtime.get("latest_state_id") or "")
    if _last_ingress_body is not None:
        try:
            vm = process_state(_last_ingress_body)
        except Exception as e:
            vm = None
            err_msg = str(e)
        state_id = _react_snapshot_state_id(_last_ingress_body, state_id)
    return {
        "view_model": vm,
        "state_id": state_id or None,
        "ingress": _last_ingress_body,
        "error": err_msg,
        "agent": _build_agent_snapshot(),
    }


async def _broadcast_react_snapshot() -> None:
    payload = _build_react_snapshot_payload()
    await manager.broadcast(
        json.dumps({"type": "snapshot", "payload": payload}, default=str),
    )


async def broadcast_event(event_type: str, payload):
    await manager.broadcast(json.dumps({"type": event_type, "payload": payload}))


def _replace_trace(trace: dict):
    trace_history = ai_runtime["trace_history"]
    decision_id = trace.get("decision_id")
    incoming_seq = int(trace.get("update_seq", 0))
    for idx, item in enumerate(trace_history):
        if item.get("decision_id") == decision_id:
            existing_seq = int(item.get("update_seq", 0))
            if incoming_seq < existing_seq:
                return False
            trace_history[idx] = trace
            break
    else:
        trace_history.append(trace)
    ai_runtime["trace_history"] = trace_history[-50:]
    latest = ai_runtime["latest_trace"]
    if not latest:
        ai_runtime["latest_trace"] = trace
    elif latest.get("decision_id") == decision_id:
        if incoming_seq >= int(latest.get("update_seq", 0)):
            ai_runtime["latest_trace"] = trace
    else:
        ai_runtime["latest_trace"] = trace
    return True


def _mark_trace_stale():
    trace = ai_runtime.get("latest_trace")
    if not trace:
        return None
    if trace.get("approval_status") in {"approved", "edited"}:
        return None
    if trace.get("status") in {"awaiting_approval", "running", "building_prompt"}:
        stale = deepcopy(trace)
        stale["update_seq"] = int(stale.get("update_seq", 0)) + 1
        stale["status"] = "stale"
        stale["approval_status"] = "stale"
        _replace_trace(stale)
        return stale
    return None


def _canonical_legal_command(vm: dict[str, Any], cmd: str) -> str:
    norm = " ".join(cmd.strip().split())
    if not norm:
        raise ValueError("empty command")
    actions = vm.get("actions") or []
    want = norm.lower()
    for a in actions:
        c = str(a.get("command", "")).strip()
        if " ".join(c.split()).lower() == want:
            return c
    raise ValueError(f"command not in legal list: {cmd!r}")


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/ai", response_class=HTMLResponse)
async def get_ai_debugger(request: Request):
    return templates.TemplateResponse(request, "ai_debugger.html")


@app.get("/api/ai/state")
async def get_ai_state():
    latest_trace = ai_runtime["latest_trace"]
    sequence_preview = []
    if latest_trace:
        sequence_preview = latest_trace.get("final_decision_sequence") or []
    return {
        "mode": ai_runtime["mode"],
        "system_prompt": SYSTEM_PROMPT,
        "latest_state_id": ai_runtime["latest_state_id"],
        "latest_trace": latest_trace,
        "sequence_preview": sequence_preview,
        "trace_history": ai_runtime["trace_history"],
        "ai_enabled": ai_runtime["ai_enabled"],
        "ai_status": ai_runtime["ai_status"],
        "ai_api_style": ai_runtime["ai_api_style"],
        "ai_status_message": ai_runtime["ai_status_message"],
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_text(
            json.dumps(
                {"type": "snapshot", "payload": _build_react_snapshot_payload()},
                default=str,
            ),
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/update_state")
async def update_state(request: Request):
    global _last_ingress_body
    try:
        data = await request.json()
        meta = data.get("meta", {})
        state_id = meta.get("state_id", "")
        if state_id and state_id != ai_runtime["latest_state_id"]:
            stale_trace = _mark_trace_stale()
            ai_runtime["latest_state_id"] = state_id
            ai_runtime["approved_action"] = None
            if stale_trace:
                await broadcast_event("agent_trace", stale_trace)

        vm = process_state(data)
        _last_ingress_body = data
        await broadcast_event("state", {"vm": vm, "state_id": state_id})
        await _broadcast_react_snapshot()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/runs")
async def get_runs():
    try:
        if not os.path.exists(LOGS_DIR):
            return {"runs": []}
        runs = [
            d for d in os.listdir(LOGS_DIR) if os.path.isdir(os.path.join(LOGS_DIR, d))
        ]
        runs.sort(reverse=True)
        return {"runs": runs}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/runs/{run_name}")
async def get_run_states(run_name: str):
    try:
        run_path = os.path.join(LOGS_DIR, run_name)
        if not os.path.exists(run_path):
            return {"status": "error", "message": "Run not found"}

        states = []
        files = [
            f
            for f in os.listdir(run_path)
            if f.endswith(".json") and not f.endswith(".ai.json")
        ]
        files.sort()

        for file in files:
            with open(os.path.join(run_path, file), "r", encoding="utf-8") as f:
                data = json.load(f)
                states.append(process_state(data))

        return {"states": states}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/poll_instruction")
async def poll_instruction():
    approved = ai_runtime["approved_action"]
    ai_runtime["approved_action"] = None
    return {
        "manual_action": manual_actions_queue.pop(0) if manual_actions_queue else None,
        "approved_action": approved,
        "agent_mode": ai_runtime["mode"],
    }


@app.get("/api/debug/poll_instruction")
async def api_poll_instruction():
    """Alias for CommunicationMod when using /api/debug/* namespace."""
    return await poll_instruction()


@app.post("/log")
async def log_message(request: Request):
    try:
        data = await request.json()
        message = data.get("message", "")
        await broadcast_event("log", message)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/action_taken")
async def action_taken(request: Request):
    try:
        data = await request.json()
        await broadcast_event("action", data)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/agent_trace")
async def update_agent_trace(request: Request):
    try:
        trace = await request.json()
        replaced = _replace_trace(trace)
        if not replaced:
            return {"status": "ignored", "reason": "stale_trace"}
        await broadcast_event("agent_trace", trace)
        await _broadcast_react_snapshot()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class ManualAction(BaseModel):
    action: str


class ModeUpdate(BaseModel):
    mode: str


class ApprovalRequest(BaseModel):
    action: str = ""


class AiStatusUpdate(BaseModel):
    enabled: bool = False
    status: str = "unknown"
    api_style: str = ""
    message: str = ""


class ResumeBody(BaseModel):
    kind: str
    command: str | None = None


async def _store_ai_status(payload: dict) -> dict:
    ai_runtime["ai_enabled"] = payload.get("enabled", ai_runtime["ai_enabled"])
    ai_runtime["ai_status"] = payload.get("status", ai_runtime["ai_status"])
    ai_runtime["ai_api_style"] = payload.get("api_style", ai_runtime["ai_api_style"])
    ai_runtime["ai_status_message"] = payload.get(
        "message",
        ai_runtime["ai_status_message"],
    )
    merged = {
        "enabled": ai_runtime["ai_enabled"],
        "status": ai_runtime["ai_status"],
        "api_style": ai_runtime["ai_api_style"],
        "message": ai_runtime["ai_status_message"],
    }
    await broadcast_event("ai_status", merged)
    return merged


@app.post("/submit_action")
async def submit_action(cmd: ManualAction):
    action_str = cmd.action.strip()
    if action_str:
        manual_actions_queue.append(action_str)
        return {"status": "queued", "action": action_str}
    return {"status": "ignored"}


@app.post("/api/ai/mode")
async def set_ai_mode(cmd: ModeUpdate):
    mode = cmd.mode.strip().lower()
    if mode not in {"manual", "propose", "auto"}:
        return {"status": "error", "message": "Invalid mode"}
    ai_runtime["mode"] = mode
    await broadcast_event("agent_mode", {"mode": mode})
    await _broadcast_react_snapshot()
    return {"status": "success", "mode": mode}


@app.post("/api/ai/approve")
async def approve_ai_action(cmd: ApprovalRequest):
    trace = ai_runtime.get("latest_trace")
    if not trace:
        return {"status": "error", "message": "No proposal available"}

    if trace.get("status") == "stale" or trace.get("state_id") != ai_runtime["latest_state_id"]:
        return {
            "status": "error",
            "message": "This proposal is for a previous state; the game has moved on. Approve only the current proposal.",
        }

    parsed_proposal = trace.get("parsed_proposal") or {}
    chosen_commands = parsed_proposal.get("chosen_commands") or []
    first_chosen = (
        chosen_commands[0] if chosen_commands else parsed_proposal.get("chosen_command", "")
    )
    action = cmd.action.strip() or trace.get("final_decision") or first_chosen
    if not action:
        return {"status": "error", "message": "No action available to approve"}

    ai_runtime["approved_action"] = {
        "state_id": trace.get("state_id"),
        "action": action,
        "edited": bool(cmd.action.strip()),
    }
    updated = deepcopy(trace)
    updated["status"] = "approved"
    updated["approval_status"] = "edited" if cmd.action.strip() else "approved"
    updated["update_seq"] = int(updated.get("update_seq", 0)) + 1
    if cmd.action.strip():
        updated["edited_action"] = action
    updated["final_decision"] = action
    _replace_trace(updated)
    await broadcast_event("agent_trace", updated)
    await _broadcast_react_snapshot()
    return {"status": "success", "action": action}


@app.post("/api/ai/reject")
async def reject_ai_action():
    trace = ai_runtime.get("latest_trace")
    if not trace:
        return {"status": "ignored"}
    updated = deepcopy(trace)
    updated["update_seq"] = int(updated.get("update_seq", 0)) + 1
    updated["status"] = "rejected"
    updated["approval_status"] = "rejected"
    ai_runtime["approved_action"] = None
    _replace_trace(updated)
    await broadcast_event("agent_trace", updated)
    await _broadcast_react_snapshot()
    return {"status": "success"}


@app.post("/api/ai/status")
async def update_ai_status(cmd: AiStatusUpdate):
    payload = {
        "enabled": cmd.enabled,
        "status": cmd.status,
        "api_style": cmd.api_style,
        "message": cmd.message,
    }
    stored = await _store_ai_status(payload)
    await _broadcast_react_snapshot()
    return {"status": "success", **stored}


# ---------------------------------------------------------------------------
# React monitor compatibility (greenfield-shaped control plane)
# ---------------------------------------------------------------------------


@app.get("/api/debug/snapshot")
def get_debug_snapshot() -> dict[str, Any]:
    return _build_react_snapshot_payload()


@app.post("/api/debug/ingress")
async def post_debug_ingress(request: Request) -> dict[str, Any]:
    """Debug / operator paste: accept CommunicationMod JSON or update_state envelope."""
    global _last_ingress_body
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    _last_ingress_body = body
    await _broadcast_react_snapshot()
    return _build_react_snapshot_payload()


@app.post("/api/debug/manual_command")
async def post_debug_manual_command(body: dict[str, Any]) -> dict[str, Any]:
    raw = body.get("command")
    if not isinstance(raw, str) or not raw.strip():
        raise HTTPException(
            status_code=400,
            detail="command (non-empty string) required",
        )
    snap = _build_react_snapshot_payload()
    vm = snap.get("view_model")
    if not isinstance(vm, dict):
        raise HTTPException(
            status_code=400,
            detail="no projection yet; POST /api/debug/ingress or run the game",
        )
    try:
        canon = _canonical_legal_command(vm, raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    manual_actions_queue.append(canon)
    return {"ok": True, "queued": len(manual_actions_queue), "command": canon}


@app.post("/api/agent/resume")
async def post_agent_resume(body: ResumeBody) -> dict[str, Any]:
    kind = (body.kind or "").strip().lower()
    if kind == "approve":
        res = await approve_ai_action(ApprovalRequest(action=""))
    elif kind == "reject":
        res = await reject_ai_action()
    elif kind == "edit":
        cmd = (body.command or "").strip()
        if not cmd:
            raise HTTPException(
                status_code=400,
                detail="edit requires non-empty command",
            )
        res = await approve_ai_action(ApprovalRequest(action=cmd))
    else:
        raise HTTPException(status_code=400, detail="kind must be approve, reject, or edit")
    if isinstance(res, dict) and res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "resume failed"))
    return _build_agent_snapshot()


@app.post("/api/agent/retry")
async def post_agent_retry() -> dict[str, Any]:
    """
    Legacy: cannot re-invoke LLM from the server alone. Reject a pending proposal
    if any so the operator can get a fresh one on the next game tick / state.
    """
    trace = ai_runtime.get("latest_trace")
    if trace and trace.get("status") in {
        "awaiting_approval",
        "running",
        "building_prompt",
    }:
        await reject_ai_action()
    await _broadcast_react_snapshot()
    return _build_react_snapshot_payload()


@app.get("/api/agent/status")
def get_agent_status() -> dict[str, Any]:
    return _build_agent_snapshot()


@app.get("/api/history/threads")
def history_threads(merge_checkpoint_threads: bool = False) -> dict[str, Any]:
    _ = merge_checkpoint_threads
    return {"threads": []}


@app.get("/api/history/events")
def history_events(
    thread_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    _ = thread_id, limit, offset
    return {"events": []}


@app.get("/api/history/checkpoints")
def history_checkpoints(thread_id: str, limit: int = 30) -> dict[str, Any]:
    _ = thread_id, limit
    return {"checkpoints": []}


@app.get("/api/history/checkpoint")
def history_checkpoint(
    thread_id: str,
    checkpoint_id: str | None = None,
    checkpoint_ns: str = "",
) -> dict[str, Any]:
    _ = checkpoint_id, checkpoint_ns
    return {
        "thread_id": thread_id,
        "checkpoint": {
            "checkpoint_id": None,
            "state_id": None,
            "values": {},
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
