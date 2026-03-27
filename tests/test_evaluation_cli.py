from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.cli import main


def test_cli_emits_jsonl(tmp_path: Path, capsys) -> None:
    events = [{"a": 1}, {"b": 2}]
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"events": events}), encoding="utf-8")
    main([str(p)])
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2
    assert json.loads(out[0]) == {"a": 1}


def test_cli_accepts_raw_array(tmp_path: Path, capsys) -> None:
    p = tmp_path / "a.json"
    p.write_text(json.dumps([{"x": True}]), encoding="utf-8")
    main([str(p)])
    assert json.loads(capsys.readouterr().out.strip()) == {"x": True}
