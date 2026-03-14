import concurrent.futures
import datetime
import json
import os
import sys
import threading
import time
from pathlib import Path

import requests

from src.agent.graph import SpireDecisionAgent
from src.agent.session_state import is_command_failure_state, mark_trace_command_failed
from src.agent.schemas import AgentTrace
from src.agent.tracing import build_state_id, create_trace, write_ai_log
from src.ui.state_processor import process_state

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DASHBOARD_URL = "http://localhost:8000"
DUPLICATE_LOG_HEARTBEAT = 10


def notify_dashboard(endpoint: str, data: dict):
    """Send JSON data to the dashboard without blocking gameplay."""

    def send():
        try:
            requests.post(f"{DASHBOARD_URL}{endpoint}", json=data, timeout=0.5)
        except requests.exceptions.RequestException:
            pass

    threading.Thread(target=send, daemon=True).start()


def poll_instruction() -> dict:
    try:
        return requests.get(f"{DASHBOARD_URL}/poll_instruction", timeout=0.4).json()
    except requests.exceptions.RequestException:
        return {}


def execute_action(action: str, source: str):
    print(action, flush=True)
    notify_dashboard("/action_taken", {"action": action, "source": source})


def choose_idle_command(state: dict) -> str | None:
    commands = state.get("available_commands", []) or []
    if "wait" in commands:
        return "wait 10"
    if "state" in commands:
        return "state"
    return None


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
    run_dir = os.path.join(LOG_DIR, timestamp)
    os.makedirs(run_dir, exist_ok=True)
    agent = SpireDecisionAgent()
    print("ready", flush=True)

    notify_dashboard(
        "/api/ai/status",
        {
            "enabled": False,
            "status": "checking" if agent.llm else "disabled",
            "api_style": "",
            "message": agent.ai_disabled_reason,
        },
    )

    def initialize_ai_status():
        result = agent.initialize_ai_runtime()
        notify_dashboard("/api/ai/status", result)
        if not result.get("enabled"):
            notify_dashboard("/log", {"message": f"{result.get('message')} AI disabled; continuing dashboard/logging."})

    threading.Thread(target=initialize_ai_status, daemon=True).start()

    event_index = 0
    last_proposed_state_id = None
    trace_cache: dict[str, AgentTrace] = {}
    state_log_paths: dict[str, Path] = {}
    last_ai_execution: dict[str, object | None] = {
        "trace": None,
        "state_id": None,
        "action": None,
        "source": None,
    }
    proposal_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="spire-ai")
    proposal_state: dict[str, object] = {
        "token": 0,
        "future": None,
        "state_id": "",
        "started_at": 0.0,
    }

    def publish_ai_status(status: str, message: str, *, enabled: bool | None = None):
        notify_dashboard(
            "/api/ai/status",
            {
                "enabled": agent.ai_enabled if enabled is None else enabled,
                "status": status,
                "api_style": agent.ai_api_style,
                "message": message,
            },
        )

    def disable_ai_for_run(status: str, message: str):
        agent.set_ai_unavailable(status, message)
        publish_ai_status(status, message, enabled=False)
        notify_dashboard("/log", {"message": message})

    def clear_active_proposal(reason: str = ""):
        future = proposal_state.get("future")
        if future is None:
            return
        proposal_state["token"] = int(proposal_state["token"]) + 1
        proposal_state["future"] = None
        proposal_state["state_id"] = ""
        proposal_state["started_at"] = 0.0
        if reason:
            notify_dashboard("/log", {"message": reason})

    def start_proposal(vm: dict, state_id: str, agent_mode: str):
        proposal_state["token"] = int(proposal_state["token"]) + 1
        token = int(proposal_state["token"])

        def forward_trace(item):
            if proposal_state.get("future") is None:
                return
            if int(proposal_state["token"]) != token:
                return
            notify_dashboard("/agent_trace", item.model_dump(mode="json"))

        future = proposal_executor.submit(
            agent.propose,
            vm,
            state_id,
            agent_mode,
            forward_trace,
        )
        proposal_state["future"] = future
        proposal_state["state_id"] = state_id
        proposal_state["started_at"] = time.monotonic()
        notify_dashboard("/log", {"message": f"AI proposal started for state {state_id}."})

    def refresh_proposal_state():
        future = proposal_state.get("future")
        if future is None:
            return

        timeout_seconds = getattr(agent.config, "proposal_timeout_seconds", 20.0)
        elapsed = time.monotonic() - float(proposal_state.get("started_at", 0.0))
        if elapsed >= timeout_seconds:
            timed_out_state_id = str(proposal_state.get("state_id") or "")
            clear_active_proposal(
                f"AI proposal for state {timed_out_state_id} timed out after {timeout_seconds:.0f}s."
            )
            disable_ai_for_run(
                "timed_out",
                (
                    "LLM request timed out; AI disabled for this run so gameplay, "
                    "dashboard updates, and logging can continue."
                ),
            )
            return

        if not future.done():
            return

        completed_state_id = str(proposal_state.get("state_id") or "")
        clear_active_proposal()
        try:
            trace = future.result()
        except Exception as exc:  # noqa: BLE001
            disable_ai_for_run("error", f"LLM worker crashed: {exc}")
            return

        trace_cache[completed_state_id] = trace
        state_log_path = state_log_paths.get(completed_state_id)
        if state_log_path:
            write_ai_log(state_log_path, trace)

    def write_state_log(
        state: dict,
        *,
        state_id: str,
        manual_action: str | None,
        agent_mode: str,
        is_duplicate: bool,
        duplicate_run_length: int,
        heartbeat: bool,
        command_sent: str | None,
        command_source: str,
        ready_for_command: bool,
    ) -> Path:
        nonlocal event_index
        path = Path(run_dir) / f"{event_index:04d}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "state": state,
                    "action": manual_action,
                    "state_id": state_id,
                    "meta": {
                        "event_index": event_index,
                        "ready_for_command": ready_for_command,
                        "is_duplicate": is_duplicate,
                        "duplicate_run_length": duplicate_run_length,
                        "heartbeat": heartbeat,
                        "agent_mode": agent_mode,
                        "ai_enabled": agent.ai_enabled,
                        "command_sent": command_sent,
                        "command_source": command_source,
                        "proposal_in_flight": proposal_state.get("future") is not None,
                    },
                },
                f,
                indent=2,
            )
        event_index += 1
        state_log_paths[state_id] = path
        return path

    last_state_snapshot = None
    last_log_signature = None
    duplicate_run_length = 0

    def finalize_ai_execution(
        trace,
        state_id: str,
        action: str,
        approval_status: str,
        source: str,
        legal_actions: list[dict] | None = None,
    ):
        trace.status = "executed"
        trace.approval_status = approval_status
        trace.final_decision = action
        trace.execution_outcome = "executed"
        trace.update_seq += 1
        notify_dashboard("/agent_trace", trace.model_dump(mode="json"))
        state_log_path = state_log_paths.get(state_id)
        if state_log_path:
            write_ai_log(state_log_path, trace)
        agent.remember_executed_action(trace, action, legal_actions)
        last_ai_execution["trace"] = trace
        last_ai_execution["state_id"] = state_id
        last_ai_execution["action"] = action
        last_ai_execution["source"] = source
        execute_action(action, source)

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            state = json.loads(line)
        except json.JSONDecodeError:
            print("state", flush=True)
            continue

        command_failure = is_command_failure_state(state)
        if command_failure and last_ai_execution.get("trace") and str(last_ai_execution.get("source", "")).startswith("ai"):
            failed_trace = mark_trace_command_failed(
                last_ai_execution["trace"],
                command_failure,
                str(last_ai_execution.get("action") or ""),
            )
            notify_dashboard("/agent_trace", failed_trace.model_dump(mode="json"))
            failed_state_id = str(last_ai_execution.get("state_id") or "")
            failed_state_log_path = state_log_paths.get(failed_state_id)
            if failed_state_log_path:
                write_ai_log(failed_state_log_path, failed_trace)
            notify_dashboard(
                "/log",
                {
                    "message": (
                        f"AI command failed and can be retried on the next valid state: "
                        f"{last_ai_execution.get('action')} ({command_failure})"
                    )
                },
            )
            trace_cache[failed_state_id] = failed_trace
            last_proposed_state_id = None
            last_ai_execution = {"trace": None, "state_id": None, "action": None, "source": None}

        state_id = build_state_id(state)
        if (
            not command_failure
            and last_ai_execution.get("trace")
            and str(last_ai_execution.get("source", "")).startswith("ai")
            and state_id != str(last_ai_execution.get("state_id") or "")
        ):
            last_ai_execution = {"trace": None, "state_id": None, "action": None, "source": None}
        vm = process_state(state)
        notify_dashboard("/update_state", {"state": state, "meta": {"state_id": state_id}})

        refresh_proposal_state()
        if proposal_state.get("future") is not None and proposal_state.get("state_id") != state_id:
            clear_active_proposal(
                f"Discarded in-flight AI proposal for state {proposal_state.get('state_id')} after the game advanced."
            )

        ready_for_command = state.get("ready_for_command", False)
        instruction = poll_instruction() if ready_for_command else {}
        manual_action = instruction.get("manual_action")
        approved_action = instruction.get("approved_action")
        agent_mode = instruction.get("agent_mode", agent.config.default_mode)
        if not agent.ai_enabled:
            agent_mode = "manual"

        pending_trace = trace_cache.get(state_id)
        command_to_send: str | None = None
        command_source = "idle"

        if manual_action:
            command_to_send = manual_action
            command_source = "manual"
        elif ready_for_command and agent_mode == "auto":
            if pending_trace and pending_trace.status == "awaiting_approval" and pending_trace.final_decision:
                finalize_ai_execution(
                    pending_trace,
                    state_id,
                    pending_trace.final_decision,
                    "auto_approved",
                    "ai-auto",
                    vm.get("actions", []),
                )
                last_proposed_state_id = None
                last_state_snapshot = None
                last_log_signature = None
                duplicate_run_length = 0
                continue
        if ready_for_command and not command_to_send and approved_action and approved_action.get("state_id") == state_id:
            action = approved_action.get("action", "").strip()
            if action:
                trace = trace_cache.get(state_id)
                if trace:
                    if approved_action.get("edited"):
                        trace.edited_action = action
                    finalize_ai_execution(
                        trace,
                        state_id,
                        action,
                        "edited" if approved_action.get("edited") else "approved",
                        "ai",
                        vm.get("actions", []),
                    )
                else:
                    execute_action(action, "ai")
                last_proposed_state_id = None
                last_state_snapshot = None
                last_log_signature = None
                duplicate_run_length = 0
                continue

        should_start_proposal = (
            ready_for_command
            and agent.ai_enabled
            and agent_mode != "manual"
            and bool(vm.get("actions"))
            and state_id != last_proposed_state_id
            and proposal_state.get("future") is None
        )
        actions_list = vm.get("actions") or []
        single_action_short_circuit = (
            should_start_proposal
            and len(actions_list) == 1
        )
        if single_action_short_circuit:
            only_command = actions_list[0].get("command", "")
            trace = create_trace(vm, state_id, agent_mode, "", "")
            trace.status = "awaiting_approval"
            trace.final_decision = only_command
            trace.response_text = "(Single legal action; no LLM call.)"
            trace_cache[state_id] = trace
            notify_dashboard("/agent_trace", trace.model_dump(mode="json"))
            if agent_mode == "auto":
                finalize_ai_execution(
                    trace,
                    state_id,
                    only_command,
                    "auto_approved",
                    "ai-auto",
                    actions_list,
                )
                last_proposed_state_id = None
                last_state_snapshot = None
                last_log_signature = None
                duplicate_run_length = 0
                notify_dashboard("/log", {"message": f"Single action for state {state_id}: {only_command!r} (no LLM)."})
                continue
            last_proposed_state_id = state_id
        elif should_start_proposal:
            start_proposal(vm, state_id, agent_mode)
            last_proposed_state_id = state_id

        if not command_to_send:
            command_to_send = choose_idle_command(state)
            command_source = "poll" if command_to_send else "none"

        log_signature = (
            state_id,
            ready_for_command,
            agent_mode,
            agent.ai_enabled,
            command_to_send,
            command_source,
            proposal_state.get("future") is not None,
            manual_action,
        )
        is_duplicate = state == last_state_snapshot and log_signature == last_log_signature
        if is_duplicate:
            duplicate_run_length += 1
        else:
            duplicate_run_length = 0

        should_write_log = (not is_duplicate) or (duplicate_run_length % DUPLICATE_LOG_HEARTBEAT == 0)
        if should_write_log:
            write_state_log(
                state,
                state_id=state_id,
                manual_action=manual_action,
                agent_mode=agent_mode,
                is_duplicate=is_duplicate,
                duplicate_run_length=duplicate_run_length,
                heartbeat=is_duplicate,
                command_sent=command_to_send,
                command_source=command_source,
                ready_for_command=ready_for_command,
            )

        last_state_snapshot = state
        last_log_signature = log_signature

        if manual_action:
            execute_action(manual_action, "manual")
            last_ai_execution = {"trace": None, "state_id": None, "action": None, "source": None}
            last_proposed_state_id = None
            last_state_snapshot = None
            last_log_signature = None
            duplicate_run_length = 0
            continue

        if command_to_send:
            print(command_to_send, flush=True)
        else:
            notify_dashboard(
                "/log",
                {"message": f"No safe idle command available for state {state_id}; waiting for the next update."},
            )


if __name__ == "__main__":
    main()
