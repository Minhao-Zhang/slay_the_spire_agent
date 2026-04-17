from __future__ import annotations

from pathlib import Path

from src.agent.tracing import append_run_metric_line, legacy_file_logs_enabled
from src.persistence.settings import reload_persistence_settings


def test_legacy_file_logs_false_skips_ndjson(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WRITE_LEGACY_FILE_LOGS", "false")
    reload_persistence_settings()
    assert legacy_file_logs_enabled() is False
    append_run_metric_line(tmp_path, {"type": "state", "state_id": "x"})
    assert not (tmp_path / "run_metrics.ndjson").exists()
