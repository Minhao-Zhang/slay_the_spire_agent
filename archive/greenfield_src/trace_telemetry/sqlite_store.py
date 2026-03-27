"""SQLite-backed trace store (shared DB file with LangGraph checkpoints)."""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from src.control_api.checkpoint_factory import default_sqlite_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT UNIQUE,
    thread_id TEXT NOT NULL,
    step_seq INTEGER NOT NULL,
    ts_logical REAL NOT NULL,
    event_type TEXT NOT NULL,
    step_kind TEXT,
    state_id TEXT,
    schema_version INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trace_events_thread_id ON trace_events(thread_id);
CREATE INDEX IF NOT EXISTS idx_trace_events_state_id ON trace_events(state_id);
CREATE INDEX IF NOT EXISTS idx_trace_events_thread_step ON trace_events(thread_id, step_seq);
"""


class SqliteTraceStore:
    def __init__(self, *, db_path: str | None = None) -> None:
        self._path = db_path or default_sqlite_path()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    def next_step_seq(self, thread_id: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(MAX(step_seq), 0) + 1 FROM trace_events WHERE thread_id = ?",
                (thread_id,),
            )
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 1

    def append(self, event: dict[str, Any]) -> bool:
        payload = dict(event)
        key = payload.get("idempotency_key")
        if isinstance(key, str) and key:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT 1 FROM trace_events WHERE idempotency_key = ?",
                    (key,),
                )
                if cur.fetchone() is not None:
                    return False

        thread_id = str(payload.get("thread_id") or "")
        step_seq = int(payload.get("step_seq") or 0)
        ts_logical = float(payload.get("ts_logical") or 0.0)
        event_type = str(payload.get("event_type") or "agent_step")
        step_kind = payload.get("step_kind")
        step_kind_s = str(step_kind) if step_kind is not None else None
        state_id = payload.get("state_id")
        state_id_s = str(state_id) if state_id is not None else None
        schema_version = int(payload.get("schema_version") or 1)
        blob = json.dumps(payload, ensure_ascii=False)

        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO trace_events (
                        idempotency_key, thread_id, step_seq, ts_logical,
                        event_type, step_kind, state_id, schema_version, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key if isinstance(key, str) and key else None,
                        thread_id,
                        step_seq,
                        ts_logical,
                        event_type,
                        step_kind_s,
                        state_id_s,
                        schema_version,
                        blob,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.rollback()
                return False
        return True

    def list_events(
        self,
        *,
        thread_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        off = max(0, int(offset))
        clauses: list[str] = []
        params: list[Any] = []
        if thread_id is not None:
            clauses.append("thread_id = ?")
            params.append(thread_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        base = f"SELECT payload_json FROM trace_events {where} ORDER BY id ASC"

        with self._lock:
            if limit is not None and limit >= 0:
                cur = self._conn.execute(
                    base + " LIMIT ? OFFSET ?",
                    (*params, int(limit), off),
                )
            else:
                cur = self._conn.execute(
                    base + " LIMIT -1 OFFSET ?",
                    (*params, off),
                )
            rows = cur.fetchall()
        out: list[dict[str, Any]] = []
        for (blob,) in rows:
            try:
                out.append(json.loads(blob))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    def list_thread_summaries(self) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT thread_id, COUNT(*) AS event_count, MAX(step_seq) AS last_step_seq
                FROM trace_events
                GROUP BY thread_id
                ORDER BY MAX(id) DESC
                """
            )
            rows = cur.fetchall()
        return [
            {
                "thread_id": str(r[0]),
                "event_count": int(r[1]),
                "last_step_seq": int(r[2] or 0),
            }
            for r in rows
        ]
