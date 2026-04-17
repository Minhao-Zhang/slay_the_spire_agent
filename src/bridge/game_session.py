from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class GameLifecycle(Enum):
    WAITING_FOR_GAME = "waiting_for_game"
    GAME_ACTIVE = "game_active"
    GAME_ENDING = "game_ending"
    REFLECTING = "reflecting"


def unwrap_inner_state(raw_envelope: dict[str, Any]) -> dict[str, Any]:
    """Same unwrap as process_state: top-level may be ``{\"state\": ...}``."""
    if not isinstance(raw_envelope, dict):
        return {}
    inner = raw_envelope.get("state", raw_envelope)
    return inner if isinstance(inner, dict) else {}


def extract_game_state(raw_envelope: dict[str, Any]) -> dict[str, Any]:
    inner = unwrap_inner_state(raw_envelope)
    g = inner.get("game_state")
    return g if isinstance(g, dict) else {}


def normalize_seed(game_state: dict[str, Any]) -> str | None:
    seed = game_state.get("seed")
    if seed is None:
        return None
    s = str(seed).strip()
    return s if s else None


def sanitize_class_slug(raw: Any) -> str:
    s = str(raw or "UNKNOWN").strip() or "UNKNOWN"
    slug = re.sub(r"[^0-9A-Za-z]+", "_", s).upper().strip("_")
    return slug[:32] if slug else "UNKNOWN"


def _normalize_ascension(game_state: dict[str, Any]) -> int:
    asc = game_state.get("ascension_level")
    if isinstance(asc, int):
        return asc
    if asc is None:
        return 0
    try:
        return int(str(asc).strip())
    except (TypeError, ValueError):
        return 0


def build_game_dir_name(
    game_state: dict[str, Any],
    *,
    now: datetime.datetime | None = None,
) -> str | None:
    """Directory basename: ``<YYYY-MM-DD-HH-MM-SS>_<CLASS>_A<asc>_<seed8>``.

    Returns ``None`` if seed is missing or empty — caller must not create a log directory.
    """
    seed = normalize_seed(game_state)
    if not seed:
        return None
    ts = (now or datetime.datetime.now()).strftime("%Y-%m-%d-%H-%M-%S")
    cls = sanitize_class_slug(game_state.get("class"))
    asc = _normalize_ascension(game_state)
    seed8 = str(seed)[:8]
    return f"{ts}_{cls}_A{asc}_{seed8}"


# Inverse of :func:`build_game_dir_name` (timestamp uses ``-``; class slug may contain ``_``).
_GAME_DIR_BASENAME_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})_(.+)_A(\d+)_(.+)$"
)


def parse_game_dir_basename(basename: str) -> tuple[str | None, int]:
    """Parse a log run directory name produced by :func:`build_game_dir_name`.

    Returns ``(class_slug, ascension)`` where ``class_slug`` matches
    :func:`sanitize_class_slug` (e.g. ``THE_SILENT``), or ``(None, 0)`` if the
    string does not match the expected shape.
    """
    m = _GAME_DIR_BASENAME_RE.match((basename or "").strip())
    if not m:
        return None, 0
    cls_slug = m.group(2)
    try:
        asc = max(0, int(m.group(3)))
    except ValueError:
        asc = 0
    return cls_slug, asc


@dataclass
class GameSession:
    """Per-run state: logging paths, indices, and caches scoped to one in-game session."""

    game_dir: Path | None = None
    logging_enabled: bool = False
    event_index: int = 0
    run_end_persisted: bool = False
    trace_cache: dict[str, Any] = field(default_factory=dict)
    state_log_paths: dict[str, Path] = field(default_factory=dict)
    saw_game_over: bool = False
    identity: dict[str, Any] = field(default_factory=dict)
    warned_no_seed: bool = False
    sql_run_id: str | None = None
    sql_frame_by_state_id: dict[str, str] = field(default_factory=dict)
    sql_event_index_by_state_id: dict[str, int] = field(default_factory=dict)
    prev_frame_floor: int | None = None

    def reset_for_new_game(self) -> None:
        self.game_dir = None
        self.logging_enabled = False
        self.event_index = 0
        self.run_end_persisted = False
        self.trace_cache.clear()
        self.state_log_paths.clear()
        self.saw_game_over = False
        self.identity.clear()
        self.warned_no_seed = False
        self.sql_run_id = None
        self.sql_frame_by_state_id.clear()
        self.sql_event_index_by_state_id.clear()
        self.prev_frame_floor = None
