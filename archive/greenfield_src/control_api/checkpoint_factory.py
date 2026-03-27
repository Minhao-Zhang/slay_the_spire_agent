"""LangGraph checkpointer: in-memory (default) or SQLite (durable)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Tuple

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from src.repo_paths import REPO_ROOT


def default_sqlite_path() -> str:
    """Database path for checkpoints + trace (one file)."""
    raw = os.environ.get("SLAY_SQLITE_PATH")
    if raw and raw.strip():
        path = Path(raw.strip()).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
    log_dir = REPO_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir / "slay_agent.sqlite")


def checkpointer_mode() -> str:
    m = os.environ.get("SLAY_CHECKPOINTER", "memory").strip().lower()
    return m if m in ("memory", "sqlite") else "memory"


def create_checkpointer() -> tuple[BaseCheckpointSaver, sqlite3.Connection | None]:
    """
    Return ``(checkpointer, sqlite_connection_or_none)``.

    When SQLite is selected, the caller owns the connection and must ``close()``
    on shutdown (see ``agent_runtime.shutdown_checkpoint_resources``).
    """
    if checkpointer_mode() == "memory":
        return InMemorySaver(), None

    path = default_sqlite_path()
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    saver = SqliteSaver(conn)
    saver.setup()
    return saver, conn
