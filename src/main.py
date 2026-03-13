import copy
import datetime
import json
import os
import sys
import threading
from pathlib import Path

import requests

from src.agent.graph import SpireDecisionAgent
from src.agent.tracing import build_state_id, write_ai_log
from src.ui.state_processor import process_state

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DASHBOARD_URL = "http://localhost:8000"


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


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
    run_dir = os.path.join(LOG_DIR, timestamp)
    os.makedirs(run_dir, exist_ok=True)
    agent = SpireDecisionAgent()

    print("ready", flush=True)

    event_index = 0
    last_logged_state = None
    last_proposed_state_id = None
    trace_cache = {}
    state_log_paths = {}

    def finalize_ai_execution(trace, state_id: str, action: str, approval_status: str, source: str):
        trace.status = "executed"
        trace.approval_status = approval_status
        trace.final_decision = action
        trace.execution_outcome = "executed"
        trace.update_seq += 1
        notify_dashboard("/agent_trace", trace.model_dump(mode="json"))
        state_log_path = state_log_paths.get(state_id)
        if state_log_path:
            write_ai_log(state_log_path, trace)
        agent.remember_executed_action(trace, action)
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
            print("wait 10", flush=True)
            continue

        state_id = build_state_id(state)
        vm = process_state(state)
        notify_dashboard("/update_state", {"state": state, "meta": {"state_id": state_id}})

        if not state.get("ready_for_command", False):
            print("wait 10", flush=True)
            continue

        instruction = poll_instruction()
        manual_action = instruction.get("manual_action")
        approved_action = instruction.get("approved_action")
        agent_mode = instruction.get("agent_mode", agent.config.default_mode)

        is_duplicate = state == last_logged_state
        if not is_duplicate:
            path = Path(run_dir) / f"{event_index:04d}.json"
            with path.open("w", encoding="utf-8") as f:
                json.dump({"state": state, "action": manual_action, "state_id": state_id}, f, indent=2)
            state_log_paths[state_id] = path
            event_index += 1
            last_logged_state = copy.deepcopy(state)

        if manual_action:
            execute_action(manual_action, "manual")
            last_logged_state = None
            last_proposed_state_id = None
            continue

        if agent_mode == "auto":
            pending_trace = trace_cache.get(state_id)
            if pending_trace and pending_trace.status == "awaiting_approval" and pending_trace.final_decision:
                finalize_ai_execution(
                    pending_trace,
                    state_id,
                    pending_trace.final_decision,
                    "auto_approved",
                    "ai-auto",
                )
                last_logged_state = None
                last_proposed_state_id = None
                continue

        if approved_action and approved_action.get("state_id") == state_id:
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
                    )
                else:
                    execute_action(action, "ai")
                last_logged_state = None
                last_proposed_state_id = None
                continue

        if agent_mode != "manual" and vm.get("actions") and state_id != last_proposed_state_id:
            trace = agent.propose(
                vm,
                state_id,
                agent_mode,
                trace_callback=lambda item: notify_dashboard("/agent_trace", item.model_dump(mode="json")),
            )
            trace_cache[state_id] = trace
            last_proposed_state_id = state_id
            if trace.status in {"invalid", "error", "disabled"}:
                state_log_path = state_log_paths.get(state_id)
                if state_log_path:
                    write_ai_log(state_log_path, trace)
            elif agent_mode == "auto" and trace.status == "awaiting_approval" and trace.final_decision:
                finalize_ai_execution(
                    trace,
                    state_id,
                    trace.final_decision,
                    "auto_approved",
                    "ai-auto",
                )
                last_logged_state = None
                last_proposed_state_id = None
                continue

        print("wait 10", flush=True)


if __name__ == "__main__":
    main()
