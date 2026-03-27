"""Process-scoped long-term memory (dev/test: in-process dict; prod would be Postgres/Redis)."""

from __future__ import annotations

import threading
from typing import Any

MemoryNamespace = tuple[str, ...]


class InMemoryMemoryStore:
    """
    Key/value buckets per namespace, e.g. ``(\"strategy\", \"IRONCLAD\")``.

    Writes are shallow copies of ``value`` dicts.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[MemoryNamespace, dict[str, Any]] = {}

    def put(self, namespace: MemoryNamespace, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            bucket = self._data.setdefault(namespace, {})
            bucket[key] = {**value}

    def get(self, namespace: MemoryNamespace, key: str) -> dict[str, Any] | None:
        with self._lock:
            bucket = self._data.get(namespace)
            if not bucket or key not in bucket:
                return None
            return {**bucket[key]}

    def list_keys(self, namespace: MemoryNamespace) -> list[str]:
        with self._lock:
            bucket = self._data.get(namespace)
            return sorted(bucket.keys()) if bucket else []

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
