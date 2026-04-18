"""Langfuse recorder: sampling and failure paths return local IDs without raising."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import langfuse as langfuse_module

from src.observability.langfuse_client import (
    LangfuseClient,
    LangfuseRecorder,
    langfuse_trace_id_for_decision_id,
    sanitize_langfuse_trace_attribute,
)


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


def test_sanitize_langfuse_trace_attribute_truncates_to_200() -> None:
    long_ascii = "a" * 250
    out = sanitize_langfuse_trace_attribute(long_ascii)
    assert out is not None
    assert len(out) == 200


def test_sanitize_langfuse_trace_attribute_coerces_to_ascii() -> None:
    out = sanitize_langfuse_trace_attribute("run_caf\xe9_2026")
    assert out is not None
    assert out.isascii()


def test_log_generation_calls_propagate_when_session_id(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://example.invalid")
    monkeypatch.setenv("LANGFUSE_SAMPLE_RATE", "1.0")
    from src.persistence.settings import get_persistence_settings, reload_persistence_settings

    reload_persistence_settings()
    get_persistence_settings.cache_clear()

    propagate_calls: list[dict] = []

    @contextmanager
    def capture_propagate(**kwargs):
        propagate_calls.append(dict(kwargs))
        yield

    monkeypatch.setattr(langfuse_module, "propagate_attributes", capture_propagate)

    gen = MagicMock()
    gen.id = "obs-prop-test"
    gen.end = MagicMock()
    rec = LangfuseRecorder()
    rec._client = MagicMock()
    rec._client.start_observation = MagicMock(return_value=gen)

    tid, oid = rec.log_generation(
        trace_id="0" * 32,
        name="decision",
        input_text="hi",
        output_text="bye",
        model="m",
        metadata={},
        usage={},
        latency_ms=1,
        session_id="2026-04-17-12-00-00_IRONCLAD_A0_12345678",
        user_id="2026-04-17-12-00-00_IRONCLAD_A0_12345678",
    )
    assert tid == "0" * 32
    assert oid == "obs-prop-test"
    assert len(propagate_calls) == 1
    assert propagate_calls[0]["session_id"] == "2026-04-17-12-00-00_IRONCLAD_A0_12345678"
    assert propagate_calls[0]["user_id"] == "2026-04-17-12-00-00_IRONCLAD_A0_12345678"
    rec._client.start_observation.assert_called_once()


def test_log_generation_skips_propagate_without_session(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://example.invalid")
    monkeypatch.setenv("LANGFUSE_SAMPLE_RATE", "1.0")
    from src.persistence.settings import get_persistence_settings, reload_persistence_settings

    reload_persistence_settings()
    get_persistence_settings.cache_clear()

    propagate_calls: list[dict] = []

    @contextmanager
    def capture_propagate(**kwargs):
        propagate_calls.append(dict(kwargs))
        yield

    monkeypatch.setattr(langfuse_module, "propagate_attributes", capture_propagate)

    gen = MagicMock()
    gen.id = "obs-no-prop"
    gen.end = MagicMock()
    rec = LangfuseRecorder()
    rec._client = MagicMock()
    rec._client.start_observation = MagicMock(return_value=gen)

    rec.log_generation(
        trace_id="1" * 32,
        name="decision",
        input_text="hi",
        output_text="bye",
        model="m",
        metadata={},
        usage={},
        latency_ms=1,
    )
    assert propagate_calls == []
