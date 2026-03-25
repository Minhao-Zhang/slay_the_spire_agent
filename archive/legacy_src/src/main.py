import concurrent.futures
import datetime
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

import requests

from src.agent.graph import SpireDecisionAgent
from src.agent.policy import resolve_token_play
from src.agent.session_state import is_command_failure_state, mark_trace_command_failed
from src.agent.schemas import AgentTrace
from src.agent.tracing import build_state_id, build_turn_key, create_trace, write_ai_log
from src.repo_paths import REPO_ROOT
from src.ui.state_processor import process_state

BASE_DIR = str(REPO_ROOT)
LOG_DIR = os.path.join(BASE_DIR, "logs")
DASHBOARD_URL = "http://localhost:8000"
MAX_LOG_RUNS = 10


def prune_old_log_runs(log_dir: str, keep: int = MAX_LOG_RUNS) -> None:
    """Keep only the most recent `keep` run directories; remove older ones."""
    if not os.path.isdir(log_dir):
        return
    runs = [
        p
        for p in Path(log_dir).iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    runs.sort(key=lambda p: p.name, reverse=True)
    for old in runs[keep:]:
        try:
            shutil.rmtree(old)
        except OSError:
            pass


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


def choose_combat_reward_gold_command(vm: dict) -> str | None:
    """Auto-pick guaranteed-value gold rewards on combat reward screens."""
    screen = vm.get("screen") or {}
    if screen.get("type") != "COMBAT_REWARD":
        return None
    content = screen.get("content") or {}
    rewards = content.get("rewards") or []
    actions = vm.get("actions") or []
    for reward in rewards:
        if str(reward.get("reward_type", "")).upper() != "GOLD":
            continue
        idx = reward.get("choice_index")
        if not isinstance(idx, int):
            continue
        command = f"choose {idx}"
        if any((a.get("command") or "").strip() == command for a in actions):
            return command
    return None


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
    run_dir = os.path.join(LOG_DIR, timestamp)
    os.makedirs(run_dir, exist_ok=True)
    prune_old_log_runs(LOG_DIR, keep=MAX_LOG_RUNS)
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
    current_agent_mode: str = agent.config.default_mode
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
    proposal_failures: dict[str, int] = {"streak": 0}
    # Queued sequence: remaining token-based commands from an approved multi-command sequence
    queued_sequence: dict[str, object] = {
        "commands": [],   # list[str] of remaining token-based commands
        "trace": None,    # AgentTrace that originated the sequence
        "source": "ai",   # source string to use for execute_action
        "turn_key": "",   # turn key at the time the sequence was approved
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

    def note_proposal_success() -> None:
        if proposal_failures["streak"] <= 0:
            return
        proposal_failures["streak"] = 0
        notify_dashboard("/log", {"message": "AI proposal recovered; failure streak reset."})

    def handle_proposal_failure(*, summary: str, disable_message: str, status: str) -> None:
        proposal_failures["streak"] += 1
        streak = proposal_failures["streak"]
        limit = getattr(agent.config, "proposal_failure_streak_limit", 3)
        notify_dashboard(
            "/log",
            {
                "message": (
                    f"{summary} (failure streak {streak}/{limit}). "
                    "Will keep trying until limit is reached."
                )
            },
        )
        if streak >= limit:
            disable_ai_for_run(status, disable_message)

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
            handle_proposal_failure(
                summary=f"AI proposal timed out for state {timed_out_state_id}",
                status="timed_out",
                disable_message=(
                    "LLM request timed out repeatedly; AI disabled for this run so gameplay, "
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
            handle_proposal_failure(
                summary=f"LLM worker crashed: {exc}",
                status="error",
                disable_message=f"LLM worker crashed repeatedly; AI disabled for this run. Last error: {exc}",
            )
            return

        note_proposal_success()
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

    def clear_queued_sequence(reason: str = ""):
        queued_sequence["commands"] = []
        queued_sequence["trace"] = None
        queued_sequence["source"] = "ai"
        queued_sequence["turn_key"] = ""
        if reason:
            notify_dashboard("/log", {"message": reason})

    def finalize_ai_execution(
        trace,
        state_id: str,
        action: str,
        approval_status: str,
        source: str,
        legal_actions: list[dict] | None = None,
        remaining_commands: list[str] | None = None,
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
        # Enqueue remaining token-based commands from the approved sequence
        if remaining_commands:
            queued_sequence["commands"] = list(remaining_commands)
            queued_sequence["trace"] = trace
            queued_sequence["source"] = source
            queued_sequence["turn_key"] = build_turn_key(vm)
            notify_dashboard(
                "/log",
                {"message": f"Queued {len(remaining_commands)} more command(s) from approved sequence."},
            )
        else:
            clear_queued_sequence()
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
            clear_queued_sequence("Cleared queued sequence due to command failure.")

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
            last_proposed_state_id = None  # Treat previous state as nothing; auto re-call AI for new state

        ready_for_command = state.get("ready_for_command", False)

        # Drain the queued sequence before asking the user or the LLM for anything new.
        # If the turn key changed (new screen), the sequence is stale and must be discarded.
        current_turn_key = build_turn_key(vm)
        if queued_sequence["commands"] and queued_sequence.get("turn_key") and current_turn_key and current_turn_key != queued_sequence["turn_key"]:
            clear_queued_sequence(
                f"Cleared queued sequence: game moved from {queued_sequence['turn_key']!r} to {current_turn_key!r}."
            )
        if ready_for_command and queued_sequence["commands"]:
            next_cmd_token = queued_sequence["commands"][0]
            actions_list_now = vm.get("actions") or []
            canonical_cmd = None
            if next_cmd_token.upper().startswith("PLAY "):
                canonical_cmd = resolve_token_play(next_cmd_token, actions_list_now)
            else:
                # Non-PLAY queued commands (e.g. END): must appear in the current legal actions
                cmd_norm = " ".join(next_cmd_token.strip().split()).lower()
                for a in actions_list_now:
                    if " ".join(str(a.get("command", "")).strip().split()).lower() == cmd_norm:
                        canonical_cmd = a.get("command", next_cmd_token).strip()
                        break
            if canonical_cmd:
                remaining = list(queued_sequence["commands"])[1:]
                seq_trace = queued_sequence["trace"]
                seq_source = str(queued_sequence["source"] or "ai")
                queued_sequence["commands"] = remaining
                if not remaining:
                    queued_sequence["trace"] = None
                notify_dashboard("/log", {"message": f"Executing queued command: {canonical_cmd!r} ({len(remaining)} remaining)."})
                agent.remember_executed_action(seq_trace, canonical_cmd, actions_list_now)
                last_ai_execution["trace"] = seq_trace
                last_ai_execution["state_id"] = state_id
                last_ai_execution["action"] = canonical_cmd
                last_ai_execution["source"] = seq_source
                execute_action(canonical_cmd, seq_source)
                last_state_snapshot = None
                last_log_signature = None
                duplicate_run_length = 0
                continue
            else:
                clear_queued_sequence(
                    f"Could not resolve queued command {next_cmd_token!r} against current state; "
                    "clearing sequence and falling back to normal proposal."
                )

        if ready_for_command:
            auto_gold_command = choose_combat_reward_gold_command(vm)
            if auto_gold_command:
                notify_dashboard(
                    "/log",
                    {"message": f"Auto-selecting combat gold reward via {auto_gold_command!r}."},
                )
                execute_action(auto_gold_command, "auto-reward")
                last_ai_execution = {"trace": None, "state_id": None, "action": None, "source": None}
                last_proposed_state_id = None
                last_state_snapshot = None
                last_log_signature = None
                duplicate_run_length = 0
                continue

        instruction = poll_instruction() if ready_for_command else {}
        manual_action = instruction.get("manual_action")
        approved_action = instruction.get("approved_action")
        if instruction and "agent_mode" in instruction:
            current_agent_mode = instruction.get("agent_mode", current_agent_mode)
        agent_mode = current_agent_mode
        if not agent.ai_enabled:
            agent_mode = "manual"

        pending_trace = trace_cache.get(state_id)
        command_to_send: str | None = None
        command_source = "idle"

        # In propose mode we only execute when the user has approved in the dashboard (approved_action block below).
        # In auto mode we execute the proposal as soon as we have it (block below).

        if manual_action:
            command_to_send = manual_action
            command_source = "manual"
        elif ready_for_command and agent_mode == "auto":
            if pending_trace and pending_trace.status == "awaiting_approval" and pending_trace.final_decision:
                sequence = list(pending_trace.final_decision_sequence)
                remaining = sequence[1:] if len(sequence) > 1 else []
                finalize_ai_execution(
                    pending_trace,
                    state_id,
                    pending_trace.final_decision,
                    "auto_approved",
                    "ai-auto",
                    vm.get("actions", []),
                    remaining_commands=remaining or None,
                )
                last_proposed_state_id = None
                last_state_snapshot = None
                last_log_signature = None
                duplicate_run_length = 0
                continue
        if ready_for_command and not command_to_send and approved_action:
            action = approved_action.get("action", "").strip()
            approved_sid = approved_action.get("state_id")
            actions_list_for_check = vm.get("actions") or []
            action_still_valid = any(
                (a.get("command") or "").strip() == action for a in actions_list_for_check
            )
            if action and (approved_sid == state_id or action_still_valid):
                trace = trace_cache.get(approved_sid) or trace_cache.get(state_id)
                if trace:
                    if approved_action.get("edited"):
                        trace.edited_action = action
                    # Enqueue remaining commands from the sequence (skip the first, which is being executed now)
                    sequence = list(trace.final_decision_sequence)
                    remaining = sequence[1:] if len(sequence) > 1 and not approved_action.get("edited") else []
                    finalize_ai_execution(
                        trace,
                        state_id,
                        action,
                        "edited" if approved_action.get("edited") else "approved",
                        "ai",
                        actions_list_for_check,
                        remaining_commands=remaining or None,
                    )
                else:
                    execute_action(action, "ai")
                last_proposed_state_id = None
                last_state_snapshot = None
                last_log_signature = None
                duplicate_run_length = 0
                continue

        # Single-option short-circuit: when exactly one legal action exists, we skip the LLM.
        # Example: confirm after hand select (choose card to discard) — only CONFIRM is legal.
        # actions_list is vm["actions"] from process_state() / _build_actions() in state_processor.
        # If short-circuit: create trace with that command (no LLM); auto mode executes it,
        # propose mode leaves trace awaiting_approval for the user.
        should_start_proposal = (
            ready_for_command
            and agent.ai_enabled
            and agent_mode != "manual"
            and bool(vm.get("actions"))
            and state_id != last_proposed_state_id
            and proposal_state.get("future") is None
        )
        actions_list = vm.get("actions") or []
        action_commands = {a.get("command", "") for a in actions_list}
        # Exclude always-available system actions (potions, etc.) when checking action set composition.
        non_system_commands = {
            cmd for cmd in action_commands
            if not cmd.startswith("POTION ")
        }
        # Auto-confirm short-circuit: when the only meaningful actions are CONFIRM and/or CANCEL,
        # the LLM already selected a card on the prior turn — just confirm. No re-call needed.
        auto_confirm_short_circuit = (
            should_start_proposal
            and "CONFIRM" in non_system_commands
            and non_system_commands <= {"CONFIRM", "CANCEL"}
        )
        single_action_short_circuit = (
            should_start_proposal
            and not auto_confirm_short_circuit
            and len(actions_list) == 1
        )
        if auto_confirm_short_circuit or single_action_short_circuit:
            auto_cmd = "CONFIRM" if auto_confirm_short_circuit else actions_list[0].get("command", "")
            note = "(Auto-confirm after selection; no LLM call.)" if auto_confirm_short_circuit else "(Single legal action; no LLM call.)"
            trace = create_trace(vm, state_id, agent_mode, "", "")
            trace.status = "awaiting_approval"
            trace.final_decision = auto_cmd
            trace.response_text = note
            trace_cache[state_id] = trace
            notify_dashboard("/agent_trace", trace.model_dump(mode="json"))
            if agent_mode == "auto":
                finalize_ai_execution(
                    trace,
                    state_id,
                    auto_cmd,
                    "auto_approved",
                    "ai-auto",
                    actions_list,
                    remaining_commands=None,
                )
                last_proposed_state_id = None
                last_state_snapshot = None
                last_log_signature = None
                duplicate_run_length = 0
                notify_dashboard("/log", {"message": f"Auto action for state {state_id}: {auto_cmd!r} (no LLM). {note}"})
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

        should_write_log = (state.get("in_game", True)) and (not is_duplicate)
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
        elif ready_for_command:
            # Last-resort fallback: send `state` to re-fetch the full game state.
            # This prevents a deadlock where the game is waiting for a command and we
            # have nothing to send (e.g., after a command failure returns a minimal error state).
            print("state", flush=True)
        else:
            notify_dashboard(
                "/log",
                {"message": f"No safe idle command available for state {state_id}; waiting for the next update."},
            )


if __name__ == "__main__":
    main()
