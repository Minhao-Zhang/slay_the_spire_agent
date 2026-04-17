#!/usr/bin/env python3
"""Check Langfuse configuration: settings load, client init, generation smoke test.

Does not require a running game. Uses the same ``LangfuseRecorder`` as the bridge.
Exits 0 if configuration is coherent and a minimal ``log_generation`` round-trip
succeeds or cleanly falls back to ``local-`` IDs (e.g. missing keys / network error).

Run from repo root:

    uv run python scripts/check_langfuse_config.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.observability.langfuse_client import get_langfuse_client
from src.persistence.settings import get_persistence_settings, reload_persistence_settings


def main() -> int:
    reload_persistence_settings()
    s = get_persistence_settings()

    print("--- Langfuse / persistence (from .env) ---")
    print(f"  LANGFUSE_ENABLED:     {s.langfuse_enabled}")
    print(f"  LANGFUSE_HOST:        {s.langfuse_host or '(default cloud)'}")
    print(f"  public_key set:       {bool(s.langfuse_public_key)}")
    print(f"  secret_key set:       {bool(s.langfuse_secret_key)}")
    print(f"  LANGFUSE_SAMPLE_RATE: {s.langfuse_sample_rate}")
    print(f"  LANGFUSE_REDACT:      {s.langfuse_redact_prompts}")
    print()

    lf = get_langfuse_client()
    print(f"  SDK client active:    {lf.enabled}")
    print()

    print("--- log_generation (connectivity / SDK smoke) ---")
    try:
        tid, oid = lf.log_generation(
            trace_id="0" * 32,
            name="check_langfuse_config",
            input_text="ping",
            output_text="pong",
            model="n/a",
            metadata={"kind": "connectivity_check"},
            usage={"input_tokens": 1, "output_tokens": 1},
            latency_ms=1,
        )
        print(f"  trace_id:        {tid[:48]}{'…' if len(tid) > 48 else ''}")
        print(f"  observation_id:  {oid[:48]}{'…' if len(oid) > 48 else ''}")
        if tid.startswith("local-") or oid.startswith("local-"):
            print("  (local- prefix = sampling skip, missing keys, or export failure — still OK for this script)")
        print()
        print("check_langfuse_config: OK")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: {exc!r}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
