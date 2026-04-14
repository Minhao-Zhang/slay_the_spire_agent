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

from src.agent.command_narration import describe_execution
from src.agent.graph import SpireDecisionAgent
from src.agent.policy import is_end_turn_command_token, resolve_token_play
from src.agent.session_state import TurnConversation, is_command_failure_state, mark_trace_command_failed
from src.agent.schemas import AgentTrace
from src.agent.tracing import (
    append_run_end_metric,
    append_state_run_metric,
    build_state_id,
    build_turn_key,
    build_vm_summary,
    create_trace,
    write_ai_log,
    write_run_end_snapshot,
)
from src.bridge.game_session import (
    GameLifecycle,
    GameSession,
    build_game_dir_name,
    extract_game_state,
)
from src.repo_paths import REPO_ROOT
from src.ui.state_processor import process_state

BASE_DIR = str(REPO_ROOT)
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_GAMES_ROOT = os.path.join(LOG_DIR, "games")
DASHBOARD_URL = "http://localhost:8000"
MAX_LOG_RUNS = 10
MENU_STATE_INTERVAL_SECONDS = 4.0
MENU_IDLE_SLEEP_SECONDS = 0.05


def prune_old_log_runs(log_dir: str, keep: int = MAX_LOG_RUNS) -> None:
    """Keep the `keep` newest run folders unzipped; zip older runs to ``<name>.zip`` then remove the folder."""
    if not os.path.isdir(log_dir):
        return
    log_path = Path(log_dir)
    runs = [
        p
        for p in log_path.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    runs.sort(key=lambda p: p.name, reverse=True)
    for old_dir in runs[keep:]:
        archive_base = str(log_path / old_dir.name)
        try:
            shutil.make_archive(archive_base, "zip", root_dir=str(log_path), base_dir=old_dir.name)
        except OSError:
            continue
        try:
            shutil.rmtree(old_dir)
        except OSError:
            pass


def _schedule_post_run_consolidation() -> None:
    """Increment run counter; periodically archive low-confidence procedural memory."""

    def job() -> None:
        try:
            from src.agent.config import get_agent_config
            from src.agent.memory import MemoryStore
            from src.agent.reflection.consolidator import consolidate_procedural_memory

            cfg = get_agent_config()
            mem_dir = cfg.resolved_memory_dir()
            mem_dir.mkdir(parents=True, exist_ok=True)
            ctr_path = mem_dir / "consolidation_run_counter.txt"
            n = 0
            if ctr_path.is_file():
                try:
                    n = int(ctr_path.read_text(encoding="utf-8").strip() or "0")
                except ValueError:
                    n = 0
            n += 1
            ctr_path.write_text(str(n), encoding="utf-8")
            every = cfg.consolidation_every_n_runs
            if every <= 0 or n % every != 0:
                return
            store = MemoryStore(
                memory_dir=mem_dir,
                knowledge_dir=cfg.resolved_knowledge_dir(),
            )
            consolidate_procedural_memory(store, cfg)
        except OSError:
            pass

    threading.Thread(target=job, daemon=True).start()


def reflection_stub(game_dir_str: str | None) -> None:
    """Placeholder until the reflection pipeline exists.

    Full flow (Phase A): RunAnalyzer -> LLM Reflector -> ``persist_reflection_to_memory``
    in ``src.agent.reflection`` (Step 3). Do not append fake lessons from this stub.
    """
    notify_dashboard(
        "/log",
        {"message": f"Reflection stub for game_dir={game_dir_str!r} (full pipeline not implemented)."},
    )
    if game_dir_str:
        marker = Path(game_dir_str) / "reflection_pending.json"
        try:
            marker.write_text(
                '{"status":"stub","note":"Full reflection pipeline not implemented."}\n',
                encoding="utf-8",
            )
        except OSError:
            pass


def notify_dashboard(endpoint: str, data: dict):
    """Send JSON data to the dashboard without blocking gameplay."""

    def send():
        try:
            requests.post(f"{DASHBOARD_URL}{endpoint}", json=data, timeout=2.0)
        except requests.exceptions.RequestException:
            pass

    threading.Thread(target=send, daemon=True).start()


def poll_instruction() -> dict:
    try:
        return requests.get(f"{DASHBOARD_URL}/poll_instruction", timeout=0.4).json()
    except requests.exceptions.RequestException:
        return {}


def poll_retry_proposal(state_id: str) -> dict | None:
    """Consume a one-shot Retry AI request from the dashboard for this ``state_id``."""
    try:
        r = requests.get(
            f"{DASHBOARD_URL}/api/ai/retry_poll",
            params={"current_state_id": state_id},
            timeout=0.4,
        )
        if not r.ok:
            return None
        body = r.json()
        rp = body.get("retry_proposal")
        return rp if isinstance(rp, dict) else None
    except requests.exceptions.RequestException:
        return None


def execute_action(action: str, source: str):
    print(action, flush=True)
    notify_dashboard("/action_taken", {"action": action, "source": source})


def choose_idle_command(state: dict) -> str | None:
    commands = state.get("available_commands", []) or []
    # Title / pre-run envelopes only expose start/state (no wait) — never send wait.
    if "wait" in commands:
        return "wait 10"
    if "state" in commands:
        return "state"
    return None


def _vm_event_has_no_listed_choices(vm: dict) -> bool:
    """True on EVENT screens before listed choices exist in the VM.

    CommunicationMod can emit a frame with empty ``options`` (and no ``choice_list`` on
    game_state) while the event UI is still loading. :func:`process_state` then builds
    only potion helper actions. The single-action LLM short-circuit must not treat
    ``POTION DISCARD`` as the sole meaningful choice in that window.
    """
    screen = vm.get("screen") or {}
    if screen.get("type") != "EVENT":
        return False
    content = screen.get("content") or {}
    opts = content.get("options")
    if isinstance(opts, list) and len(opts) > 0:
        return False
    cl = content.get("choice_list")
    if isinstance(cl, list) and len(cl) > 0:
        return False
    return True


def _should_skip_single_action_shortcut(vm: dict, actions_list: list) -> bool:
    """Skip shortcut when the only row is a potion command on a not-ready EVENT."""
    if len(actions_list) != 1:
        return False
    cmd = str(actions_list[0].get("command", "") or "").strip().upper()
    if not cmd.startswith("POTION "):
        return False
    return _vm_event_has_no_listed_choices(vm)


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


def _is_game_over(vm: dict) -> bool:
    screen = vm.get("screen") or {}
    return str(screen.get("type") or "").strip().upper() == "GAME_OVER"


def _game_over_proceed_command(vm: dict) -> str | None:
    for a in vm.get("actions") or []:
        if not isinstance(a, dict):
            continue
        raw = str(a.get("command", "") or "").strip()
        if raw.upper() == "PROCEED":
            return raw
    return None


def combat_reward_proceed_when_empty(vm: dict) -> str | None:
    """When COMBAT_REWARD has no reward rows, only PROCEED is meaningful (potions are optional).

    Same idea as auto-gold: advance without the LLM. Runs even when AI is disabled, unlike
    ``single_action_short_circuit`` (which requires ``agent.ai_enabled``).
    """
    screen = vm.get("screen") or {}
    if screen.get("type") != "COMBAT_REWARD":
        return None
    content = screen.get("content") or {}
    rewards = content.get("rewards")
    if rewards is None:
        rewards = []
    if len(rewards) != 0:
        return None
    for a in vm.get("actions") or []:
        if not isinstance(a, dict):
            continue
        raw = str(a.get("command", "") or "").strip()
        if raw.upper() == "PROCEED":
            return raw
    return None


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(LOG_GAMES_ROOT, exist_ok=True)
    prune_old_log_runs(LOG_GAMES_ROOT, keep=MAX_LOG_RUNS)
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

    lifecycle = GameLifecycle.WAITING_FOR_GAME
    session: GameSession | None = None
    consecutive_out_of_game = 0
    menu_last_emit = 0.0

    last_proposed_state_id = None
    current_agent_mode: str = agent.config.agent_mode
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
        "last_trace": None,
    }
    proposal_failures: dict[str, int] = {"streak": 0}
    # Futures discarded because state_id advanced before refresh consumed them — drain async.
    orphan_proposal_futures: list[tuple[concurrent.futures.Future, str]] = []
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
        proposal_state["last_trace"] = None
        notify_dashboard(
            "/api/ai/proposal_state",
            {"in_flight": False, "state_id": ""},
        )
        if reason:
            notify_dashboard("/log", {"message": reason})

    def enqueue_orphan_proposal_future(fut: concurrent.futures.Future | None, sid: str) -> None:
        if fut is None or not str(sid or "").strip():
            return
        orphan_proposal_futures.append((fut, str(sid)))

    def drain_orphan_proposal_futures() -> None:
        nonlocal orphan_proposal_futures
        kept: list[tuple[concurrent.futures.Future, str]] = []
        for fut, sid in orphan_proposal_futures:
            if not fut.done():
                kept.append((fut, sid))
                continue
            try:
                trace = fut.result()
            except Exception as exc:  # noqa: BLE001
                notify_dashboard(
                    "/log",
                    {"message": f"Orphaned AI worker for state {sid} raised: {exc!r}."},
                )
                continue
            err = str(trace.error or "").strip()
            stale = trace.model_copy(
                update={
                    "status": "stale",
                    "approval_status": "rejected",
                    "execution_outcome": "discarded",
                    "error": err or "Game state changed before this proposal could execute.",
                    "update_seq": trace.update_seq + 1,
                }
            )
            path = session.state_log_paths.get(sid) if session else None
            if path:
                write_ai_log(path, stale)
            notify_dashboard("/agent_trace", stale.model_dump(mode="json"))
            notify_dashboard(
                "/log",
                {"message": f"Persisted stale AI trace for superseded state {sid} (game advanced)."},
            )
        orphan_proposal_futures = kept

    def note_proposal_success() -> None:
        if proposal_failures["streak"] <= 0:
            return
        proposal_failures["streak"] = 0
        notify_dashboard("/log", {"message": "AI proposal recovered; failure streak reset."})

    def handle_proposal_failure(*, summary: str, disable_message: str, status: str) -> None:
        proposal_failures["streak"] += 1
        streak = proposal_failures["streak"]
        from src.agent.config import PROPOSAL_FAILURE_STREAK_LIMIT

        limit = int(PROPOSAL_FAILURE_STREAK_LIMIT)
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
            proposal_state["last_trace"] = item
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
        notify_dashboard(
            "/api/ai/proposal_state",
            {"in_flight": True, "state_id": state_id},
        )
        notify_dashboard("/log", {"message": f"AI proposal started for state {state_id}."})

    def refresh_proposal_state():
        nonlocal last_proposed_state_id
        future = proposal_state.get("future")
        if future is None:
            return

        timeout_seconds = getattr(agent.config, "proposal_timeout_seconds", 20.0)
        elapsed = time.monotonic() - float(proposal_state.get("started_at", 0.0))
        if elapsed >= timeout_seconds:
            timed_out_state_id = str(proposal_state.get("state_id") or "")
            live_trace = proposal_state.get("last_trace")
            clear_active_proposal(
                f"AI proposal for state {timed_out_state_id} timed out after {timeout_seconds:.0f}s."
            )
            if live_trace is not None:
                try:
                    per_round_s = float(agent.config.request_timeout_seconds or 60.0)
                    err = (
                        f"Proposal timed out after {timeout_seconds:.0f}s (limit from proposal_timeout_seconds). "
                        f"After tools the agent runs another model call; allow at least ~{per_round_s:.0f}s per round."
                    )
                    failed = live_trace.model_copy(
                        update={"status": "error", "error": err, "update_seq": live_trace.update_seq + 1}
                    )
                    notify_dashboard("/agent_trace", failed.model_dump(mode="json"))
                except Exception:  # noqa: BLE001
                    pass
            handle_proposal_failure(
                summary=f"AI proposal timed out for state {timed_out_state_id}",
                status="timed_out",
                disable_message=(
                    "LLM request timed out repeatedly; AI disabled for this run so gameplay, "
                    "dashboard updates, and logging can continue."
                ),
            )
            last_proposed_state_id = None
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
            last_proposed_state_id = None
            return

        note_proposal_success()
        if session:
            session.trace_cache[completed_state_id] = trace
        state_log_path = session.state_log_paths.get(completed_state_id) if session else None
        if state_log_path:
            write_ai_log(state_log_path, trace)

        # If the model failed validation for this state, allow another propose() on the next
        # ingress line with the same state_id. Otherwise last_proposed_state_id stays set and
        # main falls through to idle ``wait 10`` despite ready_for_command (stall).
        st = str(trace.status or "")
        if st in {"invalid", "error", "disabled"}:
            last_proposed_state_id = None

    def write_state_log(
        state: dict,
        *,
        vm: dict,
        state_id: str,
        manual_action: str | None,
        agent_mode: str,
        is_duplicate: bool,
        duplicate_run_length: int,
        heartbeat: bool,
        command_sent: str | None,
        command_source: str,
        ready_for_command: bool,
    ) -> Path | None:
        if not session or not session.logging_enabled or not session.game_dir:
            return None
        ei = session.event_index
        vm_summary = build_vm_summary(vm, state, state_id=state_id, event_index=ei)
        path = session.game_dir / f"{ei:04d}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "state": state,
                    "vm_summary": vm_summary,
                    "action": manual_action,
                    "state_id": state_id,
                    "meta": {
                        "event_index": ei,
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
        append_state_run_metric(session.game_dir, vm_summary, event_index=ei, state_id=state_id)
        session.event_index += 1
        session.state_log_paths[state_id] = path
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

    def send_game_command(
        action: str,
        source: str,
        *,
        vm: dict,
        legal_actions: list[dict] | None = None,
        skip_journal: bool = False,
    ) -> None:
        if not skip_journal and agent.session:
            line = describe_execution(vm, action, legal_actions or [])
            if line:
                agent.session.append_run_journal(line)
        execute_action(action, source)

    def finalize_ai_execution(
        trace,
        state_id: str,
        action: str,
        approval_status: str,
        source: str,
        legal_actions: list[dict] | None = None,
        remaining_commands: list[str] | None = None,
        *,
        vm_for_turn: dict | None = None,
    ):
        trace.status = "executed"
        trace.approval_status = approval_status
        trace.final_decision = action
        trace.execution_outcome = "executed"
        trace.update_seq += 1
        notify_dashboard("/agent_trace", trace.model_dump(mode="json"))
        state_log_path = session.state_log_paths.get(state_id) if session else None
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
            vm_t = vm_for_turn if vm_for_turn is not None else vm
            queued_sequence["turn_key"] = build_turn_key(vm_t)
            notify_dashboard(
                "/log",
                {"message": f"Queued {len(remaining_commands)} more command(s) from approved sequence."},
            )
        else:
            clear_queued_sequence()
        vm_exec = vm_for_turn if vm_for_turn is not None else vm
        send_game_command(action, source, vm=vm_exec, legal_actions=legal_actions or [])

    def _run_reflection_background(game_dir: Path | None) -> None:
        try:
            from src.agent.config import get_agent_config
            from src.agent.reflection.runner import run_reflection_pipeline

            cfg = get_agent_config()
            if not game_dir or not game_dir.is_dir():
                reflection_stub(str(game_dir) if game_dir else None)
                return
            if not agent.llm:
                notify_dashboard(
                    "/log",
                    {"message": "Reflection skipped: LLM unavailable."},
                )
                return
            run_reflection_pipeline(game_dir, agent.memory_store, agent.llm, cfg)
        except Exception as exc:  # noqa: BLE001
            notify_dashboard(
                "/log",
                {"message": f"Reflection pipeline failed: {exc!r}"},
            )

    def _finish_game_session(reason: str) -> None:
        nonlocal session, lifecycle, consecutive_out_of_game, last_proposed_state_id
        nonlocal last_state_snapshot, last_log_signature, duplicate_run_length
        gd_path = session.game_dir.resolve() if session and session.game_dir else None
        lifecycle = GameLifecycle.REFLECTING
        notify_dashboard(
            "/log",
            {"message": f"{reason} Starting background reflection."},
        )
        threading.Thread(target=_run_reflection_background, args=(gd_path,), daemon=True).start()
        if proposal_state.get("future"):
            old_fut = proposal_state.get("future")
            old_sid = str(proposal_state.get("state_id") or "")
            clear_active_proposal(reason)
            enqueue_orphan_proposal_future(old_fut, old_sid)
        else:
            clear_active_proposal(reason)
        session = None
        lifecycle = GameLifecycle.WAITING_FOR_GAME
        consecutive_out_of_game = 0
        last_proposed_state_id = None
        last_state_snapshot = None
        last_log_signature = None
        duplicate_run_length = 0
        clear_queued_sequence(reason)
        proposal_failures["streak"] = 0

    def _scan_retry_pending_reflection() -> None:
        """Retry runs with run_report.json but no reflection_output.json (startup)."""
        try:
            from src.agent.reflection.runner import pending_reflection_dirs

            if not agent.llm:
                return
            root = Path(LOG_GAMES_ROOT)
            for d in pending_reflection_dirs(root, limit=3):
                threading.Thread(
                    target=_run_reflection_background,
                    args=(d,),
                    daemon=True,
                ).start()
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_scan_retry_pending_reflection, daemon=True).start()

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
            failed_state_log_path = session.state_log_paths.get(failed_state_id) if session else None
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
            if session:
                session.trace_cache[failed_state_id] = failed_trace
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

        in_game = bool(state.get("in_game", True))

        if session is not None and lifecycle in (
            GameLifecycle.GAME_ACTIVE,
            GameLifecycle.GAME_ENDING,
        ):
            if in_game:
                consecutive_out_of_game = 0
                if lifecycle == GameLifecycle.GAME_ACTIVE and _is_game_over(vm):
                    session.saw_game_over = True
                    lifecycle = GameLifecycle.GAME_ENDING
            else:
                consecutive_out_of_game += 1
                should_end = (consecutive_out_of_game >= 2) or (
                    consecutive_out_of_game >= 1 and session.saw_game_over
                )
                if should_end:
                    _finish_game_session("Game session ended.")

        if lifecycle == GameLifecycle.WAITING_FOR_GAME and in_game:
            session = GameSession()
            gs = extract_game_state(state)
            dirname = build_game_dir_name(gs)
            if dirname:
                session.game_dir = Path(LOG_GAMES_ROOT) / dirname
                session.game_dir.mkdir(parents=True, exist_ok=True)
                session.logging_enabled = True
                session.identity = {
                    "seed": gs.get("seed"),
                    "class": gs.get("class"),
                    "ascension_level": gs.get("ascension_level"),
                }
            else:
                session.logging_enabled = False
                notify_dashboard(
                    "/log",
                    {
                        "message": (
                            "No seed in game_state; disk logging disabled for this run "
                            "(per bridge policy)."
                        ),
                    },
                )
            agent.session = TurnConversation()
            if proposal_state.get("future"):
                old_fut = proposal_state.get("future")
                old_sid = str(proposal_state.get("state_id") or "")
                clear_active_proposal("New game: cancelled in-flight proposal from prior session.")
                enqueue_orphan_proposal_future(old_fut, old_sid)
            lifecycle = GameLifecycle.GAME_ACTIVE
            consecutive_out_of_game = 0
            last_proposed_state_id = None
            last_state_snapshot = None
            last_log_signature = None
            duplicate_run_length = 0
            clear_queued_sequence()
            proposal_failures["streak"] = 0

        if lifecycle == GameLifecycle.WAITING_FOR_GAME and not in_game:
            instruction_menu = poll_instruction()
            if instruction_menu and "agent_mode" in instruction_menu:
                current_agent_mode = instruction_menu.get("agent_mode", current_agent_mode)
            commands_menu = state.get("available_commands", []) or []
            auto_on = bool(instruction_menu.get("auto_start_next_game"))
            if auto_on and "start" in commands_menu and state.get("ready_for_command", False):
                execute_action("start", "auto-start")
                menu_last_emit = time.monotonic()
                continue
            now_m = time.monotonic()
            if now_m - menu_last_emit >= MENU_STATE_INTERVAL_SECONDS:
                print("state", flush=True)
                menu_last_emit = now_m
            else:
                time.sleep(MENU_IDLE_SLEEP_SECONDS)
            continue

        refresh_proposal_state()
        drain_orphan_proposal_futures()
        if proposal_state.get("future") is not None and proposal_state.get("state_id") != state_id:
            old_fut = proposal_state.get("future")
            old_sid = str(proposal_state.get("state_id") or "")
            clear_active_proposal(
                f"Discarded in-flight AI proposal for state {old_sid} after the game advanced."
            )
            enqueue_orphan_proposal_future(old_fut, old_sid)
            last_proposed_state_id = None  # Treat previous state as nothing; auto re-call AI for new state

        retry_req = poll_retry_proposal(state_id)
        if retry_req:
            old_fut = proposal_state.get("future")
            old_sid = str(proposal_state.get("state_id") or "")
            clear_active_proposal("Retry AI: cancelled in-flight proposal for this state.")
            enqueue_orphan_proposal_future(old_fut, old_sid)
            if session:
                session.trace_cache.pop(state_id, None)
            last_proposed_state_id = None
            notify_dashboard(
                "/log",
                {
                    "message": (
                        "Retry AI: cleared in-flight work and cache for this state; "
                        "will re-propose when the loop is eligible."
                    )
                },
            )

        ready_for_command = state.get("ready_for_command", False)

        # Drain the queued sequence before asking the user or the LLM for anything new.
        # If the turn key changed (new screen), the sequence is stale and must be discarded.
        current_turn_key = build_turn_key(vm)
        if queued_sequence["commands"] and queued_sequence.get("turn_key") and current_turn_key and current_turn_key != queued_sequence["turn_key"]:
            clear_queued_sequence(
                f"Cleared queued sequence: game moved from {queued_sequence['turn_key']!r} to {current_turn_key!r}."
            )
        if ready_for_command and queued_sequence["commands"]:
            q_cmds = queued_sequence["commands"]
            next_cmd_token = q_cmds[0]
            if is_end_turn_command_token(next_cmd_token) and len(q_cmds) > 1:
                clear_queued_sequence(
                    "Refusing queued END: END must be the only command in the sequence; "
                    "clearing invalid queue."
                )
                continue
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
                send_game_command(canonical_cmd, seq_source, vm=vm, legal_actions=actions_list_now)
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
                send_game_command(
                    auto_gold_command,
                    "auto-reward",
                    vm=vm,
                    legal_actions=vm.get("actions") or [],
                )
                last_ai_execution = {"trace": None, "state_id": None, "action": None, "source": None}
                last_proposed_state_id = None
                last_state_snapshot = None
                last_log_signature = None
                duplicate_run_length = 0
                continue
            auto_cr_proceed = combat_reward_proceed_when_empty(vm)
            if auto_cr_proceed:
                notify_dashboard(
                    "/log",
                    {"message": f"Combat reward cleared (no rows); auto-advancing with {auto_cr_proceed!r}."},
                )
                send_game_command(
                    auto_cr_proceed,
                    "auto-reward",
                    vm=vm,
                    legal_actions=vm.get("actions") or [],
                )
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

        if (
            session
            and session.logging_enabled
            and ready_for_command
            and state.get("in_game", True)
            and _is_game_over(vm)
            and not session.run_end_persisted
        ):
            _, der = write_run_end_snapshot(session.game_dir, state, state_id=state_id)
            append_run_end_metric(session.game_dir, state_id=state_id, derived=der)
            session.run_end_persisted = True
            _schedule_post_run_consolidation()

        pending_trace = session.trace_cache.get(state_id) if session else None
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
                    vm_for_turn=vm,
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
                trace = (session.trace_cache.get(approved_sid) if session else None) or (
                    session.trace_cache.get(state_id) if session else None
                )
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
                        vm_for_turn=vm,
                    )
                else:
                    send_game_command(action, "ai", vm=vm, legal_actions=actions_list_for_check)
                last_proposed_state_id = None
                last_state_snapshot = None
                last_log_signature = None
                duplicate_run_length = 0
                continue

        # Single-option short-circuit: when exactly one legal action exists, we skip the LLM.
        # Example: confirm after hand select (choose card to discard) — only CONFIRM is legal.
        # Another: EVENT with one [Leave] plus optional POTION DISCARD rows — still one real choice.
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
            and not _is_game_over(vm)
        )
        actions_list = vm.get("actions") or []
        non_potion_actions = [
            a
            for a in actions_list
            if isinstance(a, dict) and not str(a.get("command", "") or "").startswith("POTION ")
        ]
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
            and len(non_potion_actions) == 1
            and not _should_skip_single_action_shortcut(vm, actions_list)
        )
        if auto_confirm_short_circuit or single_action_short_circuit:
            auto_cmd = (
                "CONFIRM"
                if auto_confirm_short_circuit
                else str(non_potion_actions[0].get("command", "") or "")
            )
            note = "(Auto-confirm after selection; no LLM call.)" if auto_confirm_short_circuit else "(Single legal action; no LLM call.)"
            trace = create_trace(vm, state_id, agent_mode, "", "")
            trace.status = "awaiting_approval"
            trace.final_decision = auto_cmd
            trace.response_text = note
            if session:
                session.trace_cache[state_id] = trace
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
                    vm_for_turn=vm,
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

        go_proceed = None
        if (
            ready_for_command
            and _is_game_over(vm)
            and state.get("in_game", True)
            and agent.ai_enabled
            and agent_mode != "manual"
            and not manual_action
        ):
            go_proceed = _game_over_proceed_command(vm)

        if go_proceed:
            command_for_sig = go_proceed
            log_signature_go = (
                state_id,
                ready_for_command,
                agent_mode,
                agent.ai_enabled,
                command_for_sig,
                "run-end",
                proposal_state.get("future") is not None,
                manual_action,
            )
            is_dup_go = state == last_state_snapshot and log_signature_go == last_log_signature
            if is_dup_go:
                duplicate_run_length += 1
            else:
                duplicate_run_length = 0
            should_write_log_go = (
                session
                and session.logging_enabled
                and state.get("in_game", True)
                and (not is_dup_go)
            )
            if should_write_log_go:
                write_state_log(
                    state,
                    vm=vm,
                    state_id=state_id,
                    manual_action=manual_action,
                    agent_mode=agent_mode,
                    is_duplicate=is_dup_go,
                    duplicate_run_length=duplicate_run_length,
                    heartbeat=is_dup_go,
                    command_sent=command_for_sig,
                    command_source="run-end",
                    ready_for_command=ready_for_command,
                )
            last_state_snapshot = state
            last_log_signature = log_signature_go

            if agent_mode == "auto":
                if not is_dup_go:
                    trace_go = create_trace(vm, state_id, agent_mode, "", "")
                    trace_go.status = "awaiting_approval"
                    trace_go.final_decision = go_proceed
                    trace_go.response_text = "(Game over screen; proceed.)"
                    if session:
                        session.trace_cache[state_id] = trace_go
                    notify_dashboard("/agent_trace", trace_go.model_dump(mode="json"))
                    finalize_ai_execution(
                        trace_go,
                        state_id,
                        go_proceed,
                        "auto_approved",
                        "run-end",
                        vm.get("actions", []),
                        remaining_commands=None,
                        vm_for_turn=vm,
                    )
                    last_proposed_state_id = None
                    last_state_snapshot = None
                    last_log_signature = None
                    duplicate_run_length = 0
                    notify_dashboard(
                        "/log",
                        {"message": f"Run end: auto {go_proceed!r} for state {state_id}."},
                    )
                    continue
            if state_id != last_proposed_state_id and proposal_state.get("future") is None:
                trace_go = create_trace(vm, state_id, agent_mode, "", "")
                trace_go.status = "awaiting_approval"
                trace_go.final_decision = go_proceed
                trace_go.response_text = "(Game over screen; approve PROCEED.)"
                if session:
                    session.trace_cache[state_id] = trace_go
                notify_dashboard("/agent_trace", trace_go.model_dump(mode="json"))
                last_proposed_state_id = state_id
            idle_go = choose_idle_command(state) or "state"
            print(idle_go, flush=True)
            continue

        if not command_to_send:
            command_to_send = choose_idle_command(state)
            command_source = "poll" if command_to_send else "none"
        if ready_for_command and not command_to_send:
            command_to_send = "state"
            command_source = "fallback"

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

        should_write_log = (
            session
            and session.logging_enabled
            and state.get("in_game", True)
            and (not is_duplicate)
        )
        if should_write_log:
            write_state_log(
                state,
                vm=vm,
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
            send_game_command(manual_action, "manual", vm=vm)
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
