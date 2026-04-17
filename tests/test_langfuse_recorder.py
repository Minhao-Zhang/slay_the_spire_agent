"""Langfuse recorder: sampling and failure paths return local IDs without raising."""

from __future__ import annotations

from src.observability.langfuse_client import LangfuseClient, LangfuseRecorder, langfuse_trace_id_for_decision_id


def test_sampling_returns_local_ids(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://example.invalid")
    monkeypatch.setenv("LANGFUSE_SAMPLE_RATE", "0.0")
    from src.persistence.settings import get_persistence_settings, reload_persistence_settings

    reload_persistence_settings()
    get_persistence_settings.cache_clear()
    rec = LangfuseRecorder()
    tid, oid = rec.log_generation(
        trace_id="0" * 32,
        name="decision",
        input_text="hi",
        output_text="bye",
        model="m",
        metadata={},
        usage={"input_tokens": 1},
        latency_ms=1,
    )
    assert tid.startswith("local-")
    assert oid.startswith("local-")


def test_sdk_failure_falls_back(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://example.invalid")
    monkeypatch.setenv("LANGFUSE_SAMPLE_RATE", "1.0")
    from src.persistence.settings import get_persistence_settings, reload_persistence_settings

    reload_persistence_settings()
    get_persistence_settings.cache_clear()
    rec = LangfuseRecorder()

    def boom(*_a, **_k):
        raise RuntimeError("network down")

    monkeypatch.setattr(rec, "_client", type("C", (), {"start_observation": staticmethod(boom)})())
    tid, oid = rec.log_generation(
        trace_id="0" * 32,
        name="decision",
        input_text="hi",
        output_text="bye",
        model="m",
        metadata={},
        usage={},
        latency_ms=1,
    )
    assert tid.startswith("local-")
    assert oid.startswith("local-")


def test_langfuse_client_is_recorder_alias() -> None:
    assert LangfuseClient is LangfuseRecorder


def test_trace_id_for_decision_id_is_stable_hex() -> None:
    d = "decision-abc-123"
    a = langfuse_trace_id_for_decision_id(d)
    b = langfuse_trace_id_for_decision_id(d)
    assert a == b
    assert len(a) == 32
    assert a == a.lower()
    assert all(c in "0123456789abcdef" for c in a)
