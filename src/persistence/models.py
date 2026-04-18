"""SQLAlchemy ORM models for Phase 0 state + observability IDs."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _json_type() -> type[JSON]:
    return JSON().with_variant(SQLITE_JSON(), "sqlite")


_JSON = _json_type()


class Base(DeclarativeBase):
    pass


class ExperimentRow(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_effort: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_weights_json: Mapped[Any | None] = mapped_column(_JSON, nullable=True)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_dir_name: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    seed: Mapped[str | None] = mapped_column(Text, nullable=True)
    character_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    ascension_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    storage_engine: Mapped[str] = mapped_column(String(16), nullable=False, default="sqlite")
    system_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_builder_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reference_data_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    knowledge_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    langfuse_session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("experiments.id"), nullable=True)
    source_log_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    frames: Mapped[list["RunFrameRow"]] = relationship(back_populates="run")
    decisions: Mapped[list["AgentDecisionRow"]] = relationship(back_populates="run")


class RunExperimentRow(Base):
    __tablename__ = "run_experiments"
    __table_args__ = (UniqueConstraint("run_id", "experiment_id", name="uq_run_experiment"),)

    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String(36), ForeignKey("experiments.id"), primary_key=True)
    bucket: Mapped[str | None] = mapped_column(Text, nullable=True)
    variant: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunFrameRow(Base):
    __tablename__ = "run_frames"
    __table_args__ = (UniqueConstraint("run_id", "event_index", name="uq_run_event_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False, index=True)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False)
    state_id: Mapped[str] = mapped_column(String(64), nullable=False)
    screen_type: Mapped[str] = mapped_column(Text, nullable=False, default="NONE")
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    act: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turn_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    ready_for_command: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    agent_mode: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    command_sent: Mapped[str | None] = mapped_column(Text, nullable=True)
    command_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_floor_start: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vm_summary_json: Mapped[Any] = mapped_column(_JSON, nullable=False)
    vm_summary_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    meta_json: Mapped[Any] = mapped_column(_JSON, nullable=False)
    meta_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state_projection_json: Mapped[Any] = mapped_column(_JSON, nullable=False)
    state_projection_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    run: Mapped[RunRow] = relationship(back_populates="frames")
    llm_calls: Mapped[list["LlmCallRow"]] = relationship(back_populates="frame")


class AgentDecisionRow(Base):
    __tablename__ = "agent_decisions"
    __table_args__ = (UniqueConstraint("run_id", "event_index", name="uq_run_decision_event"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False, index=True)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False)
    client_decision_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state_id: Mapped[str] = mapped_column(String(64), nullable=False)
    turn_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="building_prompt")
    approval_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    execution_outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    final_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_decision_sequence_json: Mapped[Any] = mapped_column(_JSON, nullable=False, default=list)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_names_json: Mapped[Any] = mapped_column(_JSON, nullable=False, default=list)
    prompt_profile: Mapped[str] = mapped_column(Text, nullable=False, default="default")
    experiment_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    experiment_tag: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategist_ran: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    planner_ran: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    react_ran: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deck_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_message_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assistant_message_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    run: Mapped[RunRow] = relationship(back_populates="decisions")
    llm_calls: Mapped[list["LlmCallRow"]] = relationship(back_populates="agent_decision")


class LlmCallRow(Base):
    __tablename__ = "llm_call"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False, index=True)
    frame_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("run_frames.id"), nullable=True)
    agent_decision_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_decisions.id"), nullable=True)
    reflection_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_effort: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uncached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    langfuse_trace_id: Mapped[str] = mapped_column(Text, nullable=False)
    langfuse_observation_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    frame: Mapped[RunFrameRow | None] = relationship(back_populates="llm_calls")
    agent_decision: Mapped[AgentDecisionRow | None] = relationship(back_populates="llm_calls")


class RunEndRow(Base):
    __tablename__ = "run_end"

    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), primary_key=True)
    state_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    victory: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screen_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    act: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_hp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_hp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deck_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relic_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    potion_slots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class MutationEventRow(Base):
    __tablename__ = "mutation_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    before_json: Mapped[Any | None] = mapped_column(_JSON, nullable=True)
    after_json: Mapped[Any | None] = mapped_column(_JSON, nullable=True)
    langfuse_trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class BackfillJobRow(Base):
    """Phase 1: one row per ``logs/games/<run_dir>`` import job.

    ``status`` (see ``src.persistence.backfill_constants``): ``pending`` | ``running`` |
    ``succeeded`` | ``failed``.

    ``stage`` while running or on failure: ``runs`` | ``frames`` | ``decisions`` |
    ``llm_calls`` | ``run_end``; on success final ``stage`` is ``done``.
    """

    __tablename__ = "backfill_jobs"
    __table_args__ = (UniqueConstraint("run_dir", name="uq_backfill_jobs_run_dir"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_dir: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    rows_written_json: Mapped[Any | None] = mapped_column(_JSON, nullable=True)
