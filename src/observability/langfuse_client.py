"""Langfuse SDK wrapper: sampling, redaction, local IDs on failure (Phase 0)."""

from __future__ import annotations

import hashlib
import logging
import os
import random
import secrets
import threading
import uuid
from contextlib import nullcontext
from functools import lru_cache
from typing import Any

from src.persistence.settings import get_persistence_settings

logger = logging.getLogger(__name__)

# Stable namespace so trace ids derived from ``decision_id`` are deterministic across processes.
_LANGFUSE_TRACE_NS = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://github.com/slay-the-spire-agent/langfuse-trace-v1"
)

_flush_daemon_lock = threading.Lock()
_flush_daemon_started = False
_flush_stop = threading.Event()


def langfuse_trace_id_for_decision_id(decision_id: str) -> str:
    """32-char lowercase hex Langfuse trace id, one per client ``decision_id`` (§5.1)."""
    d = (decision_id or "").strip()
    if not d:
        return _hex_trace_id()
    return uuid.uuid5(_LANGFUSE_TRACE_NS, d).hex


def shutdown_langfuse_background_flush() -> None:
    """Signal the background flush loop to stop (e.g. at process exit)."""
    _flush_stop.set()


def _ensure_langfuse_flush_daemon() -> None:
    global _flush_daemon_started
    with _flush_daemon_lock:
        if _flush_daemon_started:
            return
        settings = get_persistence_settings()
        if not settings.langfuse_enabled:
            return
        _flush_daemon_started = True

        def _loop() -> None:
            raw = os.getenv("LANGFUSE_FLUSH_INTERVAL_SEC", "25") or "25"
            try:
                interval = max(5.0, float(raw))
            except ValueError:
                interval = 25.0
            while not _flush_stop.wait(interval):
                try:
                    get_langfuse_recorder().flush()
                except Exception:  # noqa: BLE001
                    pass

        threading.Thread(target=_loop, daemon=True, name="langfuse-flush").start()


def _local_pair() -> tuple[str, str]:
    return f"local-{uuid.uuid4()}", f"local-{uuid.uuid4()}"


def _hex_trace_id() -> str:
    return secrets.token_hex(16)


def sanitize_langfuse_trace_attribute(value: str | None, *, max_len: int = 200) -> str | None:
    """Langfuse requires US-ASCII session/user ids and drops values longer than ``max_len``."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    ascii_s = s.encode("ascii", errors="replace").decode("ascii").strip()
    if not ascii_s:
        return None
    if len(ascii_s) > max_len:
        ascii_s = ascii_s[:max_len]
    return ascii_s


def _maybe_redact(text: str, *, enabled: bool) -> str:
    if not text:
        return ""
    if not enabled:
        return text if len(text) <= 120_000 else text[:120_000] + "\n…(truncated)…"
    h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    return f"<redacted sha256={h} len={len(text)}>"


@lru_cache(maxsize=1)
def get_langfuse_recorder() -> "LangfuseRecorder":
    rec = LangfuseRecorder()
    _ensure_langfuse_flush_daemon()
    return rec


def get_langfuse_client() -> "LangfuseClient":
    """Preferred name (DESIGN); returns the process-wide recorder singleton."""
    return get_langfuse_recorder()


class LangfuseRecorder:
    """Thin recorder around Langfuse v4 client; never raises to callers."""

    def __init__(self) -> None:
        self._settings = get_persistence_settings()
        self._client: Any = None
        if self._settings.langfuse_enabled:
            pk = self._settings.langfuse_public_key or ""
            sk = self._settings.langfuse_secret_key or ""
            if pk and sk:
                try:
                    from langfuse import Langfuse

                    host = self._settings.langfuse_host or "https://cloud.langfuse.com"
                    self._client = Langfuse(public_key=pk, secret_key=sk, host=host)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Langfuse init failed: %s", exc)
                    self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def new_trace_id(self) -> str:
        if self._client is not None:
            try:
                return str(self._client.create_trace_id())
            except Exception as exc:  # noqa: BLE001
                logger.debug("create_trace_id failed: %s", exc)
        return _hex_trace_id()

    def flush(self) -> None:
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception as exc:  # noqa: BLE001
            logger.debug("langfuse flush: %s", exc)

    def log_generation(
        self,
        *,
        trace_id: str,
        name: str,
        input_text: str,
        output_text: str,
        model: str | None,
        metadata: dict[str, Any] | None,
        usage: dict[str, int | None],
        latency_ms: int | None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[str, str]:
        """Return ``(trace_id, observation_id)`` for SQL (``local-`` prefix on failure/skip)."""
        if random.random() > self._settings.langfuse_sample_rate:
            return _local_pair()

        inp = _maybe_redact(input_text, enabled=self._settings.langfuse_redact_prompts)
        out = _maybe_redact(output_text, enabled=self._settings.langfuse_redact_prompts)

        if self._client is None:
            return _local_pair()

        tid = (
            trace_id
            if trace_id and len(trace_id) == 32 and all(c in "0123456789abcdef" for c in trace_id)
            else None
        )
        if tid is None:
            tid = self.new_trace_id()

        observation_id = f"local-{uuid.uuid4()}"
        try:
            from langfuse import propagate_attributes
            from langfuse.types import TraceContext

            sess = sanitize_langfuse_trace_attribute(session_id)
            usr_in = sanitize_langfuse_trace_attribute(user_id)
            if sess is None and usr_in is not None:
                sess = usr_in
            usr = usr_in or sess
            prop_ctx = (
                propagate_attributes(session_id=sess, user_id=usr)
                if sess is not None and usr is not None
                else nullcontext()
            )
            with prop_ctx:
                gen = self._client.start_observation(
                    trace_context=TraceContext(trace_id=tid),
                    name=name,
                    as_type="generation",
                    input=inp,
                    output=out,
                    model=model or "",
                    metadata=metadata or {},
                )
                usage_details: dict[str, int] = {}
                for k, v in usage.items():
                    if v is None:
                        continue
                    try:
                        usage_details[k] = int(v)
                    except (TypeError, ValueError):
                        continue
                if usage_details:
                    try:
                        gen.update(usage_details=usage_details)
                    except TypeError:
                        try:
                            gen.update(usage=usage_details)
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("langfuse usage update: %s", exc)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("langfuse usage update: %s", exc)
                try:
                    gen.end()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("langfuse gen.end: %s", exc)
            oid = getattr(gen, "id", None) or getattr(gen, "trace_id", None)
            if oid:
                observation_id = str(oid)
            return tid, observation_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("Langfuse log_generation failed: %s", exc)
            return f"local-{uuid.uuid4()}", f"local-{uuid.uuid4()}"


LangfuseClient = LangfuseRecorder
