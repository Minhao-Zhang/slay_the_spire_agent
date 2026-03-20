from __future__ import annotations

from pydantic import BaseModel


class CommandRequest(BaseModel):
    command: str
    source: str
    state_id: str
    decision_id: str | None = None
