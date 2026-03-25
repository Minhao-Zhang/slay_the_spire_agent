"""Singleton app store for Stage 9 (tests reset via ``reset_app_memory_store_for_tests``)."""

from __future__ import annotations

import threading

from src.memory.store import InMemoryMemoryStore

_lock = threading.Lock()
_store: InMemoryMemoryStore | None = None


def get_app_memory_store() -> InMemoryMemoryStore:
    global _store
    with _lock:
        if _store is None:
            _store = InMemoryMemoryStore()
        return _store


def reset_app_memory_store_for_tests() -> None:
    global _store
    with _lock:
        if _store is not None:
            _store.clear()
        _store = None
