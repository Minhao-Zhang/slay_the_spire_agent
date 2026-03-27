"""CLI: normalize trace exports (JSONL) and optional replay metrics (Stage 10+)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.evaluation.replay import compute_replay_metrics


def _load_events(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict) and isinstance(data.get("events"), list):
        return list(data["events"])
    raise SystemExit("Expected a JSON array or an object with an 'events' array")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description="Convert a trace JSON / JSONL-friendly export to JSON lines on stdout.",
    )
    p.add_argument(
        "trace_file",
        type=Path,
        help="Path to JSON file (array of events or debug/trace response shape)",
    )
    p.add_argument(
        "--metrics",
        action="store_true",
        help="Print aggregate ReplayMetrics as JSON after JSONL body",
    )
    args = p.parse_args(argv)
    events = _load_events(args.trace_file)
    for e in events:
        sys.stdout.write(json.dumps(e, ensure_ascii=False) + "\n")
    if args.metrics:
        m = compute_replay_metrics(events)
        blob: dict[str, Any] = {
            "steps": m.steps,
            "ingress_steps": m.ingress_steps,
            "resume_steps": m.resume_steps,
            "emitted_commands": m.emitted_commands,
            "awaiting_interrupt_hits": m.awaiting_interrupt_hits,
            "event_types": m.event_types,
            "proposal_terminal_idle": m.proposal_terminal_idle,
            "proposal_terminal_executed": m.proposal_terminal_executed,
            "proposal_terminal_error": m.proposal_terminal_error,
        }
        sys.stdout.write(json.dumps(blob, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
