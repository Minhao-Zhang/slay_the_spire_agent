"""Structured outputs at the agent boundary."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StructuredCommandProposal(BaseModel):
    """What we ask the model to emit (JSON)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    command: str | None = None
    rationale: str = Field(default="")
