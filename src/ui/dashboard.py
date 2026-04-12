import asyncio
import json
import logging
import os
import time
import zipfile
from copy import deepcopy
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.agent.config import get_agent_config, load_system_prompt
from src.agent.policy import parse_agent_output
from src.agent.prompt_builder import build_user_prompt
from src.agent.tracing import RUN_END_SNAPSHOT_FILENAME, build_state_id
from src.bridge.game_session import parse_game_dir_basename
from src.repo_paths import REPO_ROOT
from src.ui.state_processor import process_state

app = FastAPI()

log = logging.getLogger(__name__)

manual_actions_queue: list[str] = []

LOGS_DIR = os.path.join(str(REPO_ROOT), "logs")
LOG_GAMES_DIR = os.path.join(LOGS_DIR, "games")
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
    "proposal_in_flight": False,
    "proposal_for_state_id": "",
    # One-shot from POST /api/agent/retry; main.py consumes via GET /api/ai/retry_poll.
    "retry_proposal_request": None,
    "auto_start_next_game": bool(getattr(AGENT_CONFIG, "auto_start_next_game", False)),
}

# Last envelope or raw ingress (CommunicationMod JSON) for React monitor / debug paste.
_last_ingress_body: dict[str, Any] | None = None
# Monotonic clock when `_last_ingress_body` was last set (game or debug paste).
_last_ingress_monotonic: float | None = None


def _touch_ingress_received() -> None:
    global _last_ingress_monotonic
    _last_ingress_monotonic = time.monotonic()


def _ingress_max_age_seconds() -> float:
    raw = os.environ.get("DASHBOARD_INGRESS_MAX_AGE_SECONDS", "90")
    try:
        v = float(raw)
    except ValueError:
        v = 90.0
    return max(10.0, v)


def _ingress_is_live() -> bool:
    """True while CommunicationMod (or debug paste) has sent data recently."""
    if _last_ingress_body is None:
        return False
    if _last_ingress_monotonic is None:
        return True
    return (time.monotonic() - _last_ingress_monotonic) <= _ingress_max_age_seconds()


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


def _state_id_seed_from_ingress(data: dict[str, Any] | None) -> str:
    """Prefer persisted ``state_id`` from log files; else live ``meta.state_id``."""
    if not isinstance(data, dict):
        return ""
    sid = str(data.get("state_id") or "").strip()
    if sid:
        return sid
    meta = data.get("meta")
    if isinstance(meta, dict):
        sid = str(meta.get("state_id") or "").strip()
        if sid:
            return sid
    return ""


def _run_seed_from_ingress(data: dict[str, Any] | None) -> str | None:
    """Run seed from CommunicationMod ``game_state.seed`` (same field as logged frames)."""
    if not isinstance(data, dict):
        return None
    inner = _inner_game_payload(data)
    gs = inner.get("game_state")
    if not isinstance(gs, dict):
        return None
    raw = gs.get("seed")
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        try:
            s = str(int(raw))
        except (ValueError, OverflowError):
            s = str(raw).strip()
        return s or None
    s = str(raw).strip()
    return s or None


def _stringify_game_seed_for_json_wire(data: dict[str, Any]) -> None:
    """Mutate envelope so ``game_state.seed`` is a JSON string (JS safe; ints > 2^53)."""
    inner = _inner_game_payload(data)
    gs = inner.get("game_state")
    if not isinstance(gs, dict):
        return
    raw = gs.get("seed")
    if raw is None or isinstance(raw, bool) or isinstance(raw, str):
        return
    if isinstance(raw, int):
        gs["seed"] = str(raw)
        return
    if isinstance(raw, float):
        try:
            gs["seed"] = str(int(raw))
        except (ValueError, OverflowError):
            s = str(raw).strip()
            if s:
                gs["seed"] = s


def _trace_as_dict(trace: Any) -> dict[str, Any] | None:
    if trace is None:
        return None
    if isinstance(trace, dict):
        return trace
    if hasattr(trace, "model_dump"):
        return trace.model_dump(mode="json")
    return None


def _first_playable_command_from_final(fd: Any) -> str | None:
    if fd is None:
        return None
    cmds = getattr(fd, "chosen_commands", None)
    if cmds:
        first = str(cmds[0]).strip()
        return first or None
    ch = getattr(fd, "chosen_command", "") or ""
    return str(ch).strip() or None


def _trace_user_prompt_field(trace: dict[str, Any]) -> str:
    u = trace.get("user_prompt") or trace.get("user_message") or ""
    return str(u).strip() if u else ""


def _merge_llm_user_prompt_for_monitor(
    vm: dict[str, Any] | None,
    state_id: str,
    trace: dict[str, Any] | None,
) -> str:
    """Text shown as the LLM user message on the React monitor.

    Prefer the trace copy when it matches the current ingress ``state_id`` (exact
    string sent to the model, including strategy memory and planner prefix).
    Otherwise rebuild with :func:`build_user_prompt` (no session history extras).
    """
    sid = str(state_id or "").strip()
    if trace and sid:
        tsid = str(trace.get("state_id") or "").strip()
        if tsid == sid:
            u = _trace_user_prompt_field(trace)
            if u:
                return u
    if not vm or not vm.get("actions"):
        return ""
    try:
        cfg = get_agent_config()
        return build_user_prompt(
            vm,
            sid,
            [],
            strategy_memory=None,
            combat_plan_guide=None,
            prompt_profile=cfg.prompt_profile,
        )
    except Exception:
        return ""


def _trace_to_proposal(trace: dict[str, Any] | None) -> dict[str, Any] | None:
    """Shape AgentTrace into the React ``proposal`` object.

    Always surface a **best-effort parsed action** for the monitor: validated
    command, interim ``<final_decision>`` from the stream, ``[tool] …`` intent,
    or ``[tool used] …`` while the model continues after a tool round.
    """
    if not trace:
        return None
    if trace.get("status") == "stale" or trace.get("approval_status") == "stale":
        return {
            "llm_raw": None,
            "parsed_model": None,
            "command": None,
            "rationale": None,
            "status": "stale",
            "error_reason": None,
            "resolve_tag": "agent:stale",
            "for_state_id": trace.get("state_id"),
            "user_prompt": None,
        }
    val = trace.get("validation")
    err = None
    if isinstance(val, dict):
        err = val.get("error") or None
    if not err:
        err_raw = trace.get("error")
        err = err_raw if err_raw else None

    raw_stream = (trace.get("raw_output") or trace.get("response_text") or "").strip()
    if not raw_stream:
        rt = (trace.get("reasoning_text") or "").strip()
        rs = (trace.get("response_text") or "").strip()
        chunks = [x for x in (rt, rs) if x]
        raw_stream = "\n\n".join(chunks).strip()

    llm_raw = raw_stream or None
    rationale = (trace.get("reasoning_text") or None) or None

    st = str(trace.get("status") or "")
    final_cmd = trace.get("final_decision")
    parsed_prop = trace.get("parsed_proposal")

    live = parse_agent_output(raw_stream) if raw_stream else None

    command: str | None = final_cmd if final_cmd else None
    parsed_model: Any = parsed_prop
    resolve_tag = "agent:trace"

    if st == "awaiting_approval" and command:
        resolve_tag = "agent:awaiting_approval"
    elif st == "invalid":
        resolve_tag = "agent:invalid"
        if not command and isinstance(parsed_prop, dict):
            cmds = parsed_prop.get("chosen_commands") or []
            if cmds:
                command = str(cmds[0]).strip()
            elif parsed_prop.get("chosen_command"):
                command = str(parsed_prop["chosen_command"]).strip()
        if not command and live and live.final_decision:
            command = _first_playable_command_from_final(live.final_decision)
            if parsed_model is None:
                parsed_model = live.final_decision.model_dump(mode="json")
    elif st == "error":
        resolve_tag = "agent:error"

    # In-flight: no validated canonical command on the trace yet
    if not command and live:
        if live.final_decision:
            command = _first_playable_command_from_final(live.final_decision)
            if parsed_model is None:
                parsed_model = live.final_decision.model_dump(mode="json")
            if st in {"running", "building_prompt"}:
                resolve_tag = "agent:interim_parse"
        elif live.tool_request:
            command = f"[tool] {live.tool_request.tool_name}"
            parsed_model = {
                "tool_request": live.tool_request.model_dump(mode="json"),
                "interim": True,
            }
            if st in {"running", "building_prompt"}:
                resolve_tag = "agent:tool_request"

    # Model continued after native/API tool execution (trace append markers)
    if not command and trace.get("tool_names"):
        names = trace.get("tool_names")
        if isinstance(names, list) and names:
            last = str(names[-1])
            command = f"[tool used] {last}"
            parsed_model = {
                "last_tool": last,
                "interim": True,
                "note": "Waiting for model after tool; check model output below.",
            }
            if st in {"running", "building_prompt"}:
                resolve_tag = "agent:post_tool"

    if st == "building_prompt" and not command:
        command = "(preparing prompt)"
        parsed_model = parsed_model or {"interim": True}
        resolve_tag = "agent:building_prompt"

    if isinstance(parsed_prop, dict) and parsed_prop:
        parsed_model = parsed_prop
    if final_cmd:
        command = str(final_cmd)

    up = _trace_user_prompt_field(trace)
    return {
        "llm_raw": llm_raw,
        "parsed_model": parsed_model,
        "command": command,
        "rationale": rationale,
        "status": str(trace.get("status") or trace.get("approval_status") or ""),
        "error_reason": str(err) if err else None,
        "resolve_tag": resolve_tag,
        "for_state_id": trace.get("state_id"),
        "user_prompt": up or None,
    }


def _normalize_persisted_ai_log_to_trace(persisted: dict[str, Any]) -> dict[str, Any]:
    """Map ``PersistedAiLog`` JSON (``*.ai.json``) to a trace-like dict for
    :func:`_trace_to_proposal` / :func:`_pending_approval_from_trace`."""
    out = dict(persisted)
    am = persisted.get("assistant_message")
    if am is not None and str(am).strip():
        out.setdefault("response_text", str(am))
    um = persisted.get("user_message")
    if um is not None and str(um).strip():
        out.setdefault("user_prompt", str(um))
    ve = persisted.get("validation_error")
    if ve is not None and str(ve).strip():
        out.setdefault("validation", {"error": str(ve)})
    return out


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

    run_seed = _run_seed_from_ingress(_last_ingress_body)

    snap = {
        "pending_approval": pending,
        "command_queue": queue,
        "emitted_command": None,
        "proposal": _trace_to_proposal(t),
        "failure_streak": 0,
        "decision_trace": [],
        "awaiting_interrupt": bool(pending),
        "agent_mode": ai_runtime.get("mode"),
        "thread_id": None,
        "run_seed": run_seed,
        "ingress_derived_thread_id": None,
        "pending_graph_thread_id": None,
        "proposer": "graph",
        "llm_backend": llm_backend,
        "agent_error": agent_err,
        "ai_enabled": bool(ai_runtime.get("ai_enabled")),
        "ai_system_status": str(ai_runtime.get("ai_status") or ""),
        "ai_system_message": str(ai_runtime.get("ai_status_message") or ""),
        "proposal_in_flight": bool(ai_runtime.get("proposal_in_flight")),
        "proposal_for_state_id": ai_runtime.get("proposal_for_state_id") or None,
        "llm_user_prompt": None,
        "auto_start_next_game": bool(ai_runtime.get("auto_start_next_game")),
    }
    return snap


def _ingress_ready_for_command(data: dict[str, Any] | None) -> bool | None:
    inner = _inner_game_payload(data or {})
    if not inner or "ready_for_command" not in inner:
        return None
    return bool(inner.get("ready_for_command"))


def _build_react_snapshot_payload() -> dict[str, Any]:
    live = _ingress_is_live()
    vm: dict[str, Any] | None = None
    err_msg: str | None = None
    seed = _state_id_seed_from_ingress(_last_ingress_body) if live else ""
    state_id = seed or str(ai_runtime.get("latest_state_id") or "")
    age_s: float | None = None
    if _last_ingress_monotonic is not None:
        age_s = max(0.0, time.monotonic() - _last_ingress_monotonic)

    if live and _last_ingress_body is not None:
        try:
            vm = process_state(_last_ingress_body)
        except Exception as e:
            vm = None
            err_msg = str(e)
        state_id = _react_snapshot_state_id(_last_ingress_body, state_id)
    else:
        # Game stopped or no feed: do not show a frozen board as if live.
        state_id = ""

    ingress_wire: dict[str, Any] | None = None
    if live and _last_ingress_body is not None:
        ingress_wire = deepcopy(_last_ingress_body)
        _stringify_game_seed_for_json_wire(ingress_wire)

    agent_snap = _build_agent_snapshot()
    trace_d = _trace_as_dict(ai_runtime.get("latest_trace"))
    agent_snap["llm_user_prompt"] = _merge_llm_user_prompt_for_monitor(
        vm,
        state_id or "",
        trace_d,
    )

    return {
        "view_model": vm,
        "state_id": state_id or None,
        "ingress": ingress_wire,
        "ingress_ready_for_command": _ingress_ready_for_command(_last_ingress_body)
        if live
        else None,
        "error": err_msg,
        "agent": agent_snap,
        "live_ingress": live,
        "ingress_age_seconds": round(age_s, 1) if age_s is not None else None,
    }


async def _broadcast_react_snapshot() -> None:
    payload = _build_react_snapshot_payload()
    await manager.broadcast(
        json.dumps({"type": "snapshot", "payload": payload}, default=str),
    )


@app.on_event("startup")
async def _startup_ingress_stale_refresher() -> None:
    """Re-broadcast snapshots so WebSocket clients clear stale UI after the game stops."""

    async def _loop() -> None:
        await asyncio.sleep(2)
        while True:
            await asyncio.sleep(12)
            try:
                await _broadcast_react_snapshot()
            except Exception:
                pass

    asyncio.create_task(_loop())


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


def _mark_trace_stale(incoming_state_id: str = "") -> dict | None:
    """When the game advances to a new ``state_id``, supersede traces that are
    still tied to the previous state (in-flight, failed validation, etc.).

    Without this, ``invalid`` / ``error`` traces stay ``latest_trace`` while
    ``latest_state_id`` updates—so the monitor shows a new room's legal actions
    with the last model failure from the prior room.
    """
    trace = ai_runtime.get("latest_trace")
    if not trace:
        return None
    if trace.get("approval_status") in {"approved", "edited"}:
        return None
    incoming = str(incoming_state_id or "").strip()
    trace_sid = str(trace.get("state_id") or "").strip()
    state_mismatch = bool(incoming and trace_sid and trace_sid != incoming)
    in_flight = trace.get("status") in {
        "awaiting_approval",
        "running",
        "building_prompt",
    }
    dead_end = trace.get("status") in {
        "invalid",
        "error",
        "rejected",
        "stale",
    }
    if not (in_flight or (state_mismatch and dead_end)):
        return None
    stale = deepcopy(trace)
    stale["update_seq"] = int(stale.get("update_seq", 0)) + 1
    stale["status"] = "stale"
    stale["approval_status"] = "stale"
    _replace_trace(stale)
    return stale


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


_ROOT_INFO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Slay the Spire agent — API</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem;
           line-height: 1.5; color: #e2e8f0; background: #0f172a; }
    code { background: #1e293b; padding: 0.15rem 0.35rem; border-radius: 4px; }
    a { color: #7dd3fc; }
  </style>
</head>
<body>
  <h1>Dashboard API</h1>
  <p>This process serves WebSocket and REST endpoints for the operator UI. There is no HTML debugger here.</p>
  <p>Run the Vite app from <code>apps/web</code> (e.g. <code>npm run dev:web</code>) and open the URL it prints
     (typically <code>http://localhost:5173</code>), with the dashboard running on port 8000 for proxy/API.</p>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def get_root():
    return HTMLResponse(_ROOT_INFO_HTML)


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
        "auto_start_next_game": bool(ai_runtime.get("auto_start_next_game")),
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
            stale_trace = _mark_trace_stale(state_id)
            ai_runtime["latest_state_id"] = state_id
            ai_runtime["approved_action"] = None
            if stale_trace:
                await broadcast_event("agent_trace", stale_trace)

        vm = process_state(data)
        _last_ingress_body = data
        _touch_ingress_received()
        await broadcast_event("state", {"vm": vm, "state_id": state_id})
        await _broadcast_react_snapshot()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _parse_run_metrics_ndjson_text(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            errors.append(f"line {i}: {e}")
            continue
        if isinstance(obj, dict):
            records.append(obj)
        else:
            errors.append(f"line {i}: expected object, got {type(obj).__name__}")
    return records, errors


def _zip_path_for_run(run_name: str) -> str | None:
    """Resolve ``*.zip`` under ``logs/games``."""
    if not run_name or "/" in run_name or "\\" in run_name or ".." in run_name:
        return None
    if not run_name.lower().endswith(".zip"):
        return None
    base = os.path.abspath(LOG_GAMES_DIR)
    zip_path = os.path.abspath(os.path.join(LOG_GAMES_DIR, run_name))
    if zip_path.startswith(base + os.sep) and os.path.isfile(zip_path):
        return zip_path
    return None


def _read_run_end_snapshot_derived(run_name: str) -> dict[str, Any] | None:
    """Load ``derived`` from ``run_end_snapshot.json`` (directory or zip under ``logs/games``)."""
    if not run_name or "/" in run_name or "\\" in run_name or ".." in run_name:
        return None
    if run_name.lower().endswith(".zip"):
        zip_path = _zip_path_for_run(run_name)
        if not zip_path:
            return None
        stem = os.path.splitext(os.path.basename(run_name))[0]
        inner = f"{stem}/{RUN_END_SNAPSHOT_FILENAME}".replace("\\", "/")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                raw = zf.read(inner)
        except (KeyError, OSError, zipfile.BadZipFile):
            return None
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    else:
        run_dir = _safe_run_dir(run_name)
        if not run_dir:
            return None
        path = os.path.join(run_dir, RUN_END_SNAPSHOT_FILENAME)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    der = obj.get("derived")
    return der if isinstance(der, dict) else None


def _player_class_asc_from_derived(d: dict[str, Any]) -> tuple[str | None, int]:
    """``class`` + ``ascension_level`` from ``run_end`` / snapshot ``derived``."""
    raw_cls = d.get("class")
    if not isinstance(raw_cls, str):
        return None, 0
    s = raw_cls.strip()
    if not s or s in ("Main Menu", "?", "-"):
        return None, 0
    ra = d.get("ascension_level")
    asc = 0
    if isinstance(ra, (int, float)) and not isinstance(ra, bool):
        try:
            asc = max(0, int(ra))
        except (TypeError, ValueError, OverflowError):
            asc = 0
    return s, asc


def _run_outcome_from_derived(d: dict[str, Any]) -> dict[str, Any]:
    v = d.get("victory")
    victory = v if isinstance(v, bool) else None
    sc = d.get("score")
    score: int | None
    if isinstance(sc, bool):
        score = None
    elif isinstance(sc, (int, float)):
        score = int(sc)
    else:
        score = None
    sn = d.get("screen_name")
    screen_name = str(sn) if sn is not None else None
    ra = d.get("recorded_at")
    recorded_at = str(ra) if ra is not None else None
    return {
        "victory": victory,
        "score": score,
        "screen_name": screen_name,
        "recorded_at": recorded_at,
    }


def _summarize_run_metrics(
    records: list[dict[str, Any]], *, run_name: str | None = None
) -> dict[str, Any]:
    states = [r for r in records if r.get("type") == "state"]
    ais = [r for r in records if r.get("type") == "ai_decision"]
    executed = [r for r in ais if r.get("status") == "executed"]
    status_counts: dict[str, int] = {}
    for r in ais:
        k = str(r.get("status") or "unknown")
        status_counts[k] = status_counts.get(k, 0) + 1
    total_tokens = 0
    input_tokens = 0
    output_tokens = 0
    cached_input_tokens = 0
    uncached_input_tokens = 0
    for r in executed:
        t = r.get("total_tokens")
        if isinstance(t, (int, float)):
            total_tokens += int(t)
        ti = r.get("input_tokens")
        if isinstance(ti, (int, float)):
            input_tokens += int(ti)
        to = r.get("output_tokens")
        if isinstance(to, (int, float)):
            output_tokens += int(to)
        cti = r.get("cached_input_tokens")
        if isinstance(cti, (int, float)):
            cached_input_tokens += int(cti)
        uti = r.get("uncached_input_tokens")
        if isinstance(uti, (int, float)):
            uncached_input_tokens += int(uti)
        elif isinstance(ti, (int, float)):
            if isinstance(cti, (int, float)):
                uncached_input_tokens += max(0, int(ti) - int(cti))
            else:
                uncached_input_tokens += int(ti)
    latencies = [
        float(r["latency_ms"])
        for r in executed
        if isinstance(r.get("latency_ms"), (int, float))
    ]
    latencies.sort()
    n_lat = len(latencies)
    median_lat = latencies[n_lat // 2] if n_lat else None
    mean_lat = sum(latencies) / n_lat if n_lat else None

    event_indices: list[int] = []
    for r in records:
        ei = r.get("event_index")
        if isinstance(ei, int):
            event_indices.append(ei)
    floors: list[int] = []
    acts: list[int] = []
    player_class: str | None = None
    player_ascension: int = 0
    for r in states:
        vm = r.get("vm_summary")
        if isinstance(vm, dict):
            fl = vm.get("floor")
            if isinstance(fl, (int, float)):
                floors.append(int(fl))
            ac = vm.get("act")
            if isinstance(ac, (int, float)):
                acts.append(int(ac))
            raw_cls = vm.get("class")
            if isinstance(raw_cls, str):
                s = raw_cls.strip()
                # Last state row in file order wins (latest snapshot).
                if s and s not in ("Main Menu", "?", "-"):
                    player_class = s
                    ra = vm.get("ascension_level")
                    if isinstance(ra, (int, float)) and not isinstance(ra, bool):
                        try:
                            player_ascension = max(0, int(ra))
                        except (TypeError, ValueError, OverflowError):
                            player_ascension = 0
                    else:
                        player_ascension = 0
    run_ends = [r for r in records if r.get("type") == "run_end"]
    if player_class is None and run_ends:
        last_re = max(run_ends, key=lambda r: str(r.get("timestamp") or ""))
        der0 = last_re.get("derived")
        if isinstance(der0, dict):
            pc, pa = _player_class_asc_from_derived(der0)
            if pc:
                player_class = pc
                player_ascension = pa
    run_outcome: dict[str, Any] | None = None
    if run_ends:
        last_re = max(run_ends, key=lambda r: str(r.get("timestamp") or ""))
        der = last_re.get("derived")
        if isinstance(der, dict):
            run_outcome = _run_outcome_from_derived(der)
    if run_outcome is None:
        for r in reversed(states):
            vm = r.get("vm_summary")
            if not isinstance(vm, dict):
                continue
            if str(vm.get("screen_type", "")).upper() != "GAME_OVER":
                continue
            if "victory" not in vm and "score" not in vm:
                continue
            vv = vm.get("victory")
            victory = vv if isinstance(vv, bool) else None
            sc = vm.get("score")
            score = int(sc) if isinstance(sc, (int, float)) else None
            sn = vm.get("screen_name")
            run_outcome = {
                "victory": victory,
                "score": score,
                "screen_name": str(sn) if sn is not None else None,
                "recorded_at": str(r.get("timestamp") or "") or None,
            }
            break
    snapshot_derived: dict[str, Any] | None = None
    if run_name:
        snapshot_derived = _read_run_end_snapshot_derived(run_name)
    if player_class is None and isinstance(snapshot_derived, dict):
        pc, pa = _player_class_asc_from_derived(snapshot_derived)
        if pc:
            player_class = pc
            player_ascension = pa
    if run_name and player_class is None:
        pc, pa = parse_game_dir_basename(run_name)
        if pc:
            player_class = pc
            player_ascension = pa
    if run_outcome is None and isinstance(snapshot_derived, dict):
        run_outcome = _run_outcome_from_derived(snapshot_derived)
    has_run_end_snapshot = bool(snapshot_derived)
    return {
        "state_row_count": len(states),
        "ai_row_count": len(ais),
        "ai_executed_row_count": len(executed),
        "status_counts": status_counts,
        "total_tokens_executed": total_tokens,
        "input_tokens_executed": input_tokens,
        "output_tokens_executed": output_tokens,
        "cached_input_tokens_executed": cached_input_tokens,
        "uncached_input_tokens_executed": uncached_input_tokens,
        "latency_ms_mean": mean_lat,
        "latency_ms_median": median_lat,
        "event_index_min": min(event_indices) if event_indices else None,
        "event_index_max": max(event_indices) if event_indices else None,
        "max_floor_reached": max(floors) if floors else None,
        "max_act_reached": max(acts) if acts else None,
        "player_class": player_class,
        "player_ascension": player_ascension if player_class else None,
        "player_run_label": (
            f"{player_class} · A{player_ascension}" if player_class else None
        ),
        "run_outcome": run_outcome,
        "has_run_end_snapshot": has_run_end_snapshot,
    }


def _load_run_metrics_ndjson_bytes(raw: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return [], [str(e)]
    return _parse_run_metrics_ndjson_text(text)


def _load_run_metrics_records(run_name: str) -> tuple[list[dict[str, Any]] | None, str | None, list[str]]:
    """Returns (records, error_reason, parse_errors). records None if unreadable."""
    if not run_name or "/" in run_name or "\\" in run_name or ".." in run_name:
        return None, "invalid_run", []
    if run_name.endswith(".zip"):
        zip_path = _zip_path_for_run(run_name)
        if not zip_path:
            return None, "run_not_found", []
        stem = os.path.splitext(os.path.basename(run_name))[0]
        inner = f"{stem}/run_metrics.ndjson".replace("\\", "/")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                try:
                    data = zf.read(inner)
                except KeyError:
                    return None, "no_metrics_file", []
        except (zipfile.BadZipFile, OSError):
            return None, "zip_read_error", []
        recs, errs = _load_run_metrics_ndjson_bytes(data)
        return recs, None, errs
    run_dir = _safe_run_dir(run_name)
    if run_dir is None:
        return None, "run_not_found", []
    path = os.path.join(run_dir, "run_metrics.ndjson")
    if not os.path.isfile(path):
        return None, "no_metrics_file", []
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return None, "read_error", [str(e)]
    recs, errs = _parse_run_metrics_ndjson_text(text)
    return recs, None, errs


@app.get("/api/runs")
async def get_runs():
    """List replay/metrics run **directories** under ``logs/games``."""
    try:
        runs_set: set[str] = set()
        if os.path.isdir(LOG_GAMES_DIR):
            for entry in os.listdir(LOG_GAMES_DIR):
                if entry.startswith("."):
                    continue
                p = os.path.join(LOG_GAMES_DIR, entry)
                if os.path.isdir(p):
                    runs_set.add(entry)
        runs = sorted(runs_set, reverse=True)
        return {"runs": runs, "archived": {}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _safe_run_dir(run_name: str) -> str | None:
    if not run_name or "/" in run_name or "\\" in run_name or ".." in run_name:
        return None
    if not os.path.isdir(LOG_GAMES_DIR):
        return None
    base = os.path.abspath(LOG_GAMES_DIR)
    full = os.path.abspath(os.path.join(LOG_GAMES_DIR, run_name))
    if full.startswith(base + os.sep) and os.path.isdir(full):
        return full
    return None


@app.get("/api/runs/{run_name}/metrics")
async def get_run_metrics(
    run_name: str, summary: int = 0
) -> dict[str, Any]:
    """Parse ``run_metrics.ndjson`` for a log run directory or ``*.zip`` archive under ``logs/games``."""
    try:
        records, reason, parse_errors = _load_run_metrics_records(run_name)
        if reason == "invalid_run":
            raise HTTPException(status_code=400, detail="Invalid run name")
        if reason == "run_not_found":
            raise HTTPException(status_code=404, detail="Run not found")
        if reason == "zip_read_error":
            return {
                "ok": False,
                "run": run_name,
                "reason": "zip_read_error",
                "records": [],
            }
        if reason == "read_error":
            return {
                "ok": False,
                "run": run_name,
                "reason": "read_error",
                "records": [],
                "parse_errors": parse_errors,
            }
        if reason == "no_metrics_file" or records is None:
            return {
                "ok": False,
                "run": run_name,
                "reason": reason or "no_metrics_file",
                "records": [],
            }
        out: dict[str, Any] = {
            "ok": True,
            "run": run_name,
            "records": records,
            "parse_errors": parse_errors,
        }
        if summary:
            out["summary"] = _summarize_run_metrics(records, run_name=run_name)
        return out
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("get_run_metrics failed run_name=%s", run_name)
        return {
            "ok": False,
            "run": run_name,
            "reason": "internal_error",
            "records": [],
            "parse_errors": [str(exc)],
        }


def _game_state_from_frame_envelope(envelope: dict[str, Any]) -> dict[str, Any] | None:
    st = envelope.get("state")
    if isinstance(st, dict):
        gs = st.get("game_state")
        if isinstance(gs, dict):
            return gs
    return None


def _build_map_history_for_run_dir(run_dir: str) -> dict[str, Any]:
    """Derive per-act map layout and MAP-screen visited path from state frame JSON."""
    try:
        files = sorted(
            f
            for f in os.listdir(run_dir)
            if f.endswith(".json") and not f.endswith(".ai.json")
        )
    except OSError:
        return {"ok": False, "reason": "read_error", "acts": []}

    per_act: dict[int, dict[str, Any]] = {}
    for fname in files:
        path = os.path.join(run_dir, fname)
        try:
            with open(path, encoding="utf-8") as fp:
                envelope = json.load(fp)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(envelope, dict):
            continue
        game = _game_state_from_frame_envelope(envelope)
        if not game:
            continue
        act_raw = game.get("act")
        if isinstance(act_raw, float) and act_raw.is_integer():
            act_raw = int(act_raw)
        if not isinstance(act_raw, int):
            continue
        act = int(act_raw)
        entry = per_act.setdefault(
            act,
            {"nodes": None, "boss_name": None, "visited_path": []},
        )
        boss = game.get("act_boss")
        if isinstance(boss, str) and boss.strip():
            entry["boss_name"] = boss.strip()
        m = game.get("map")
        if isinstance(m, list) and len(m) > 0:
            entry["nodes"] = m
        stype = game.get("screen_type")
        if stype == "MAP":
            ss = game.get("screen_state")
            if isinstance(ss, dict):
                cn = ss.get("current_node")
                if isinstance(cn, dict):
                    x, y = cn.get("x"), cn.get("y")
                    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                        xi, yi = int(x), int(y)
                        sym = cn.get("symbol")
                        vpath: list[dict[str, Any]] = entry["visited_path"]
                        if not vpath or vpath[-1]["x"] != xi or vpath[-1]["y"] != yi:
                            pt: dict[str, Any] = {"x": xi, "y": yi}
                            if isinstance(sym, str):
                                pt["symbol"] = sym
                            vpath.append(pt)

    acts_out: list[dict[str, Any]] = []
    for act_key in sorted(per_act.keys()):
        e = per_act[act_key]
        nodes = e.get("nodes")
        if not isinstance(nodes, list) or len(nodes) == 0:
            continue
        acts_out.append(
            {
                "act": act_key,
                "nodes": nodes,
                "visited_path": e.get("visited_path") or [],
                "boss_name": e.get("boss_name"),
            }
        )
    return {"ok": True, "acts": acts_out}


@app.get("/api/runs/{run_name}/map_history")
async def get_run_map_history(run_name: str) -> dict[str, Any]:
    """Per-act Spire map nodes + visited path on MAP screens (from frame JSON)."""
    if run_name.lower().endswith(".zip"):
        return {"ok": False, "run": run_name, "reason": "zip_archive", "acts": []}
    run_dir = _safe_run_dir(run_name)
    if run_dir is None:
        raise HTTPException(status_code=404, detail="Run not found")
    data = _build_map_history_for_run_dir(run_dir)
    data["run"] = run_name
    if not data.get("ok"):
        data.setdefault("acts", [])
    return data


@app.get("/api/runs/{run_name}/frames")
async def get_run_frame_list(run_name: str) -> dict[str, Any]:
    """Sorted state JSON filenames (excludes ``*.ai.json``) for React replay."""
    run_dir = _safe_run_dir(run_name)
    if run_dir is None:
        raise HTTPException(status_code=404, detail="Run not found")
    files = sorted(
        f
        for f in os.listdir(run_dir)
        if f.endswith(".json") and not f.endswith(".ai.json")
    )
    return {"run": run_name, "files": files, "count": len(files)}


@app.get("/api/runs/{run_name}/frames/{file_name}")
async def get_run_frame_json(run_name: str, file_name: str) -> dict[str, Any]:
    """Raw log envelope: ``state``, ``state_id``, ``meta``, ``action``, …"""
    if file_name != os.path.basename(file_name) or ".." in file_name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    if not file_name.endswith(".json") or file_name.endswith(".ai.json"):
        raise HTTPException(status_code=400, detail="Invalid file name")
    run_dir = _safe_run_dir(run_name)
    if run_dir is None:
        raise HTTPException(status_code=404, detail="Run not found")
    path = os.path.join(run_dir, file_name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Frame not found")
    with open(path, encoding="utf-8") as f:
        body = json.load(f)
    if isinstance(body, dict):
        _stringify_game_seed_for_json_wire(body)
    return body


@app.get("/api/runs/{run_name}/frames/{file_name}/ai_sidecar")
async def get_run_frame_ai_sidecar(run_name: str, file_name: str) -> dict[str, Any]:
    """``NNNN.ai.json`` next to state ``NNNN.json``: proposal shape for React replay."""
    if file_name != os.path.basename(file_name) or ".." in file_name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    if not file_name.endswith(".json") or file_name.endswith(".ai.json"):
        raise HTTPException(status_code=400, detail="Invalid file name")
    run_dir = _safe_run_dir(run_name)
    if run_dir is None:
        raise HTTPException(status_code=404, detail="Run not found")
    frame_path = os.path.join(run_dir, file_name)
    if not os.path.isfile(frame_path):
        raise HTTPException(status_code=404, detail="Frame not found")
    stem, _ext = os.path.splitext(file_name)
    sidecar_path = os.path.join(run_dir, f"{stem}.ai.json")
    if not os.path.isfile(sidecar_path):
        return {
            "ok": False,
            "reason": "missing",
            "run": run_name,
            "frame": file_name,
        }
    with open(sidecar_path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise HTTPException(status_code=500, detail="Invalid ai sidecar")
    norm = _normalize_persisted_ai_log_to_trace(raw)
    return {
        "ok": True,
        "run": run_name,
        "frame": file_name,
        "proposal": _trace_to_proposal(norm),
        "pending_approval": _pending_approval_from_trace(norm),
    }


@app.get("/api/runs/{run_name}")
async def get_run_states(run_name: str):
    try:
        run_path = _safe_run_dir(run_name)
        if not run_path:
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
        "auto_start_next_game": bool(ai_runtime.get("auto_start_next_game")),
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


class AutoStartBody(BaseModel):
    enabled: bool = False


@app.post("/api/ai/auto_start")
async def set_auto_start_next_game(body: AutoStartBody):
    ai_runtime["auto_start_next_game"] = bool(body.enabled)
    await broadcast_event(
        "agent_settings",
        {"auto_start_next_game": ai_runtime["auto_start_next_game"]},
    )
    await _broadcast_react_snapshot()
    return {
        "status": "success",
        "auto_start_next_game": ai_runtime["auto_start_next_game"],
    }


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


@app.post("/api/ai/proposal_state")
async def post_proposal_state(request: Request):
    """Set by ``main.py`` when an LLM proposal starts or clears (foreground game loop)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    ai_runtime["proposal_in_flight"] = bool(body.get("in_flight"))
    ai_runtime["proposal_for_state_id"] = str(body.get("state_id") or "")
    await _broadcast_react_snapshot()
    return {"status": "success"}


# ---------------------------------------------------------------------------
# React monitor compatibility (operator control plane API)
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
    _touch_ingress_received()
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


@app.get("/api/ai/retry_poll")
def get_retry_poll(current_state_id: str = "") -> dict[str, Any]:
    """Game loop: pop retry request only when ``current_state_id`` matches the request.

    If the game has moved to another state, the request is discarded without action.
    """
    req = ai_runtime.get("retry_proposal_request")
    ai_runtime["retry_proposal_request"] = None
    if not isinstance(req, dict):
        return {"retry_proposal": None}
    req_sid = str(req.get("state_id") or "").strip()
    cur = (current_state_id or "").strip()
    if not cur or cur != req_sid:
        return {"retry_proposal": None}
    return {"retry_proposal": req}


@app.post("/api/agent/retry")
async def post_agent_retry() -> dict[str, Any]:
    """Clear stuck monitor trace; queue a one-shot re-proposal for the current state.

    In **manual** mode this is a no-op (does not clear trace or queue retry).
    Otherwise: same as reject-in-history when a trace exists, clear ``latest_trace``
    and ``approved_action``, set ``retry_proposal_request`` for ``latest_state_id``.
    The game process picks this up via ``GET /api/ai/retry_poll``, cancels any
    in-flight ``propose`` future, drops ``trace_cache`` for that state, and resets
    ``last_proposed_state_id`` so ``start_proposal`` can run again. This route does
    not invoke the LLM itself.
    """
    mode = str(ai_runtime.get("mode") or "").strip().lower()
    if mode == "manual":
        await _broadcast_react_snapshot()
        return _build_react_snapshot_payload()

    if ai_runtime.get("latest_trace"):
        await reject_ai_action()
    ai_runtime["latest_trace"] = None
    ai_runtime["approved_action"] = None
    sid = str(ai_runtime.get("latest_state_id") or "").strip()
    ai_runtime["retry_proposal_request"] = {"state_id": sid} if sid else None
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
