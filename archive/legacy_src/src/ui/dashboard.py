import json
import os
from copy import deepcopy

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.agent.config import get_agent_config, load_system_prompt
from src.repo_paths import REPO_ROOT
from src.ui.state_processor import process_state

app = FastAPI()

manual_actions_queue = []

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
LOGS_DIR = os.path.join(str(REPO_ROOT), "logs")
AGENT_CONFIG = get_agent_config()
SYSTEM_PROMPT = load_system_prompt()

ai_runtime = {
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


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    # Starlette >=1.0: TemplateResponse(request, template_name, context?)
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
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/update_state")
async def update_state(request: Request):
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
        await broadcast_event("state", {"vm": vm, "state_id": state_id})
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/runs")
async def get_runs():
    try:
        if not os.path.exists(LOGS_DIR):
            return {"runs": []}
        runs = [d for d in os.listdir(LOGS_DIR) if os.path.isdir(os.path.join(LOGS_DIR, d))]
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
        files = [f for f in os.listdir(run_path) if f.endswith(".json") and not f.endswith(".ai.json")]
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


async def _store_ai_status(payload: dict) -> dict:
    ai_runtime["ai_enabled"] = payload.get("enabled", ai_runtime["ai_enabled"])
    ai_runtime["ai_status"] = payload.get("status", ai_runtime["ai_status"])
    ai_runtime["ai_api_style"] = payload.get("api_style", ai_runtime["ai_api_style"])
    ai_runtime["ai_status_message"] = payload.get("message", ai_runtime["ai_status_message"])
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
    first_chosen = chosen_commands[0] if chosen_commands else parsed_proposal.get("chosen_command", "")
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
    return {"status": "success", **stored}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
