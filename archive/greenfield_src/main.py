"""
CommunicationMod entrypoint for the greenfield agent.

Protocol (wire-level parity with the game mod): print ``ready``, then for each
JSON line on stdin push state to the control API and, when ``ready_for_command``
is true, emit either a queued manual command from the debug UI, a safe idle
command, or ``state`` as a last resort.

All operator / graph commands are **validated** against the projected legal
action list (``game_adapter`` + ``domain.legal_command``) before ``print``.

Environment:

- ``SLAY_CONTROL_API_URL`` — base URL for ``control_api`` (default
  ``http://127.0.0.1:8000``). If unset/Cannot connect, ingress is skipped and
  manual poll returns empty; idle / ``state`` fallback still runs.
"""

from __future__ import annotations

import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()
from pydantic import ValidationError

from src.domain.contracts import compute_state_id, parse_ingress_envelope
from src.domain.state_projection import project_state
from src.game_adapter.emit import validate_idle_command, validate_operator_command

_last_sent_state_id: str | None = None


def _control_base_url() -> str:
    return os.environ.get("SLAY_CONTROL_API_URL", "http://127.0.0.1:8000").rstrip(
        "/"
    )


def choose_idle_command(state: dict) -> str | None:
    """Prefer ``wait 10``, then ``state``, from CommunicationMod ``available_commands``."""
    commands = state.get("available_commands", []) or []
    if "wait" in commands:
        return "wait 10"
    if "state" in commands:
        return "state"
    return None


def _push_ingress(base: str, state: dict) -> None:
    try:
        r = requests.post(
            f"{base}/api/debug/ingress",
            json=state,
            timeout=3.0,
        )
        if not r.ok:
            sys.stderr.write(
                f"[slay-the-spire-agent] ingress HTTP {r.status_code}: {r.text[:200]}\n"
            )
    except requests.RequestException as e:
        sys.stderr.write(f"[slay-the-spire-agent] ingress failed: {e}\n")


def _push_ingress_unless_duplicate(base: str, state: dict) -> None:
    """Skip HTTP when the normalized payload matches the last push (same state_id)."""
    global _last_sent_state_id
    try:
        ingress = parse_ingress_envelope(state)
        sid = compute_state_id(ingress)
        if sid == _last_sent_state_id:
            return
        _last_sent_state_id = sid
    except (TypeError, ValueError, ValidationError):
        pass
    _push_ingress(base, state)


def _poll_manual_action(base: str) -> str | None:
    try:
        r = requests.get(f"{base}/api/debug/poll_instruction", timeout=2.0)
        if not r.ok:
            return None
        data = r.json()
        manual = data.get("manual_action")
        if manual and isinstance(manual, str) and manual.strip():
            return manual.strip()
    except (requests.RequestException, ValueError, TypeError):
        pass
    return None


def main() -> None:
    base = _control_base_url()
    print("ready", flush=True)

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

        if not isinstance(state, dict):
            print("state", flush=True)
            continue

        _push_ingress_unless_duplicate(base, state)

        ready = bool(state.get("ready_for_command", False))
        if not ready:
            continue

        manual = _poll_manual_action(base)
        if manual:
            try:
                ingress = parse_ingress_envelope(state)
                vm = project_state(ingress).model_dump(mode="json", by_alias=True)
                to_print = validate_operator_command(vm, manual)
            except ValueError as e:
                sys.stderr.write(
                    f"[slay-the-spire-agent] illegal operator command {manual!r}: {e}\n",
                )
                print("state", flush=True)
            else:
                print(to_print, flush=True)
            continue

        idle = choose_idle_command(state)
        if idle:
            try:
                to_print = validate_idle_command(state, idle)
            except ValueError as e:
                sys.stderr.write(
                    f"[slay-the-spire-agent] idle command rejected {idle!r}: {e}\n",
                )
                print("state", flush=True)
            else:
                print(to_print, flush=True)
        else:
            print("state", flush=True)


if __name__ == "__main__":
    main()
