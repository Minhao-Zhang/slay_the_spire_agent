from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _iter_run_dirs(logs_dir: Path, run_name: str | None) -> list[Path]:
    if run_name:
        target = logs_dir / run_name
        return [target] if target.is_dir() else []
    return sorted([p for p in logs_dir.iterdir() if p.is_dir()])


def _extract_tool_counts(ai_message: str) -> Counter:
    counter: Counter = Counter()
    if not ai_message:
        return counter
    for line in ai_message.splitlines():
        marker = "[Tool used:"
        idx = line.find(marker)
        if idx < 0:
            continue
        end = line.find("]", idx)
        if end < 0:
            continue
        name = line[idx + len(marker):end].strip()
        if name:
            counter[name] += 1
    return counter


@dataclass
class ReplayMetrics:
    runs_scanned: int = 0
    state_logs: int = 0
    ai_logs: int = 0
    ready_for_command_states: int = 0
    ai_command_executions: int = 0
    ai_command_failures: int = 0
    legal_decisions: int = 0
    invalid_decisions: int = 0
    error_decisions: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    tool_usage: dict[str, int] | None = None
    status_counts: dict[str, int] | None = None

    @property
    def legal_action_rate(self) -> float:
        total = self.legal_decisions + self.invalid_decisions + self.error_decisions
        return (self.legal_decisions / total) if total else 0.0

    @property
    def invalid_output_rate(self) -> float:
        total = self.legal_decisions + self.invalid_decisions + self.error_decisions
        return (self.invalid_decisions / total) if total else 0.0

    @property
    def ai_execution_success_rate(self) -> float:
        if self.ai_command_executions == 0:
            return 0.0
        return (self.ai_command_executions - self.ai_command_failures) / self.ai_command_executions


def analyze_logs(logs_dir: Path, run_name: str | None = None) -> ReplayMetrics:
    metrics = ReplayMetrics(tool_usage={}, status_counts={})
    latencies: list[int] = []
    tool_counts: Counter = Counter()
    status_counts: Counter = Counter()

    if not logs_dir.exists() or not logs_dir.is_dir():
        return metrics

    for run_dir in _iter_run_dirs(logs_dir, run_name):
        metrics.runs_scanned += 1
        state_files = sorted(run_dir.glob("*.json"))
        for state_path in state_files:
            if state_path.name.endswith(".ai.json"):
                continue
            state_payload = _read_json(state_path)
            if not state_payload:
                continue
            metrics.state_logs += 1
            meta = state_payload.get("meta", {}) or {}
            if bool(meta.get("ready_for_command")):
                metrics.ready_for_command_states += 1
            source = str(meta.get("command_source", ""))
            if source.startswith("ai"):
                metrics.ai_command_executions += 1
            state_error = str((state_payload.get("state") or {}).get("error", "")).strip()
            if source.startswith("ai") and state_error:
                metrics.ai_command_failures += 1

            ai_sidecar = state_path.with_suffix(".ai.json")
            if not ai_sidecar.exists():
                continue
            ai_payload = _read_json(ai_sidecar)
            if not ai_payload:
                continue
            metrics.ai_logs += 1

            status = str(ai_payload.get("status", "")).strip()
            if status:
                status_counts[status] += 1
            if status in {"awaiting_approval", "approved", "executed"}:
                metrics.legal_decisions += 1
            elif status == "invalid":
                metrics.invalid_decisions += 1
            elif status in {"error", "disabled"}:
                metrics.error_decisions += 1

            input_tokens = ai_payload.get("input_tokens")
            output_tokens = ai_payload.get("output_tokens")
            total_tokens = ai_payload.get("total_tokens")
            if isinstance(input_tokens, int):
                metrics.total_input_tokens += input_tokens
            if isinstance(output_tokens, int):
                metrics.total_output_tokens += output_tokens
            if isinstance(total_tokens, int):
                metrics.total_tokens += total_tokens

            latency_ms = ai_payload.get("latency_ms")
            if isinstance(latency_ms, int):
                latencies.append(latency_ms)

            tool_names = ai_payload.get("tool_names")
            if isinstance(tool_names, list):
                tool_counts.update([str(name) for name in tool_names if str(name).strip()])
            else:
                tool_counts.update(_extract_tool_counts(str(ai_payload.get("assistant_message", ""))))

    if latencies:
        ordered = sorted(latencies)
        metrics.avg_latency_ms = round(mean(ordered), 2)
        p95_index = max(0, min(len(ordered) - 1, int(0.95 * (len(ordered) - 1))))
        metrics.p95_latency_ms = float(ordered[p95_index])

    metrics.tool_usage = dict(tool_counts)
    metrics.status_counts = dict(status_counts)
    return metrics


def _as_dict(metrics: ReplayMetrics) -> dict[str, Any]:
    return {
        "runs_scanned": metrics.runs_scanned,
        "state_logs": metrics.state_logs,
        "ai_logs": metrics.ai_logs,
        "ready_for_command_states": metrics.ready_for_command_states,
        "ai_command_executions": metrics.ai_command_executions,
        "ai_command_failures": metrics.ai_command_failures,
        "ai_execution_success_rate": round(metrics.ai_execution_success_rate, 4),
        "legal_decisions": metrics.legal_decisions,
        "invalid_decisions": metrics.invalid_decisions,
        "error_decisions": metrics.error_decisions,
        "legal_action_rate": round(metrics.legal_action_rate, 4),
        "invalid_output_rate": round(metrics.invalid_output_rate, 4),
        "avg_latency_ms": metrics.avg_latency_ms,
        "p95_latency_ms": metrics.p95_latency_ms,
        "total_input_tokens": metrics.total_input_tokens,
        "total_output_tokens": metrics.total_output_tokens,
        "total_tokens": metrics.total_tokens,
        "status_counts": metrics.status_counts or {},
        "tool_usage": metrics.tool_usage or {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay evaluator for Slay the Spire agent logs.",
    )
    parser.add_argument(
        "--logs-dir",
        default="logs",
        help="Path to logs root directory (default: logs).",
    )
    parser.add_argument(
        "--run",
        default="",
        help="Optional single run directory name under logs.",
    )
    args = parser.parse_args()

    logs_dir = Path(args.logs_dir).resolve()
    metrics = analyze_logs(logs_dir=logs_dir, run_name=args.run or None)
    print(json.dumps(_as_dict(metrics), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
