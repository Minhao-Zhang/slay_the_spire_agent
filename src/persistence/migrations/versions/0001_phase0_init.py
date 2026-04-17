"""Phase 0: runs, frames, decisions, llm_call, run_end, experiments, mutation_events.

Revision ID: 0001_phase0
Revises:
Create Date: 2026-04-16

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase0"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_t = sa.JSON()

    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_hash", sa.String(length=64), nullable=True),
        sa.Column("decision_model", sa.Text(), nullable=True),
        sa.Column("reasoning_effort", sa.Text(), nullable=True),
        sa.Column("prompt_profile", sa.Text(), nullable=True),
        sa.Column("memory_weights_json", json_t, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_dir_name", sa.String(length=512), nullable=False),
        sa.Column("seed", sa.Text(), nullable=True),
        sa.Column("character_class", sa.Text(), nullable=True),
        sa.Column("ascension_level", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("storage_engine", sa.String(length=16), nullable=False),
        sa.Column("system_prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("prompt_builder_version", sa.String(length=128), nullable=True),
        sa.Column("reference_data_hash", sa.String(length=64), nullable=True),
        sa.Column("config_hash", sa.String(length=64), nullable=True),
        sa.Column("knowledge_version_id", sa.String(length=36), nullable=True),
        sa.Column("langfuse_session_id", sa.Text(), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("source_log_path", sa.Text(), nullable=True),
        sa.Column("reflection_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_dir_name"),
    )

    op.create_table(
        "run_experiments",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("experiment_id", sa.String(length=36), nullable=False),
        sa.Column("bucket", sa.Text(), nullable=True),
        sa.Column("variant", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("run_id", "experiment_id"),
        sa.UniqueConstraint("run_id", "experiment_id", name="uq_run_experiment"),
    )

    op.create_table(
        "run_frames",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("event_index", sa.Integer(), nullable=False),
        sa.Column("state_id", sa.String(length=64), nullable=False),
        sa.Column("screen_type", sa.Text(), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("act", sa.Integer(), nullable=True),
        sa.Column("turn_key", sa.Text(), nullable=True),
        sa.Column("ready_for_command", sa.Boolean(), nullable=False),
        sa.Column("agent_mode", sa.Text(), nullable=False),
        sa.Column("ai_enabled", sa.Boolean(), nullable=False),
        sa.Column("command_sent", sa.Text(), nullable=True),
        sa.Column("command_source", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("is_floor_start", sa.Boolean(), nullable=False),
        sa.Column("vm_summary_json", json_t, nullable=False),
        sa.Column("vm_summary_schema_version", sa.Integer(), nullable=False),
        sa.Column("meta_json", json_t, nullable=False),
        sa.Column("meta_schema_version", sa.Integer(), nullable=False),
        sa.Column("state_projection_json", json_t, nullable=False),
        sa.Column("state_projection_schema_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "event_index", name="uq_run_event_index"),
    )

    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("event_index", sa.Integer(), nullable=False),
        sa.Column("client_decision_id", sa.Text(), nullable=False),
        sa.Column("state_id", sa.String(length=64), nullable=False),
        sa.Column("turn_key", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("approval_status", sa.Text(), nullable=False),
        sa.Column("execution_outcome", sa.Text(), nullable=False),
        sa.Column("final_decision", sa.Text(), nullable=True),
        sa.Column("final_decision_sequence_json", json_t, nullable=False),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("tool_names_json", json_t, nullable=False),
        sa.Column("prompt_profile", sa.Text(), nullable=False),
        sa.Column("experiment_id", sa.Text(), nullable=True),
        sa.Column("experiment_tag", sa.Text(), nullable=True),
        sa.Column("strategist_ran", sa.Boolean(), nullable=False),
        sa.Column("planner_ran", sa.Boolean(), nullable=False),
        sa.Column("react_ran", sa.Boolean(), nullable=False),
        sa.Column("deck_size", sa.Integer(), nullable=True),
        sa.Column("user_message_sha256", sa.String(length=64), nullable=True),
        sa.Column("assistant_message_sha256", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "event_index", name="uq_run_decision_event"),
    )

    op.create_table(
        "llm_call",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("frame_id", sa.String(length=36), nullable=True),
        sa.Column("agent_decision_id", sa.String(length=36), nullable=True),
        sa.Column("reflection_run_id", sa.String(length=36), nullable=True),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("round_index", sa.Integer(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("reasoning_effort", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("uncached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("langfuse_trace_id", sa.Text(), nullable=False),
        sa.Column("langfuse_observation_id", sa.Text(), nullable=False),
        sa.Column("prompt_profile", sa.Text(), nullable=True),
        sa.Column("knowledge_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_decision_id"], ["agent_decisions.id"]),
        sa.ForeignKeyConstraint(["frame_id"], ["run_frames.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "run_end",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("state_id", sa.String(length=64), nullable=True),
        sa.Column("victory", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("screen_name", sa.Text(), nullable=True),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("act", sa.Integer(), nullable=True),
        sa.Column("gold", sa.Integer(), nullable=True),
        sa.Column("current_hp", sa.Integer(), nullable=True),
        sa.Column("max_hp", sa.Integer(), nullable=True),
        sa.Column("deck_size", sa.Integer(), nullable=True),
        sa.Column("relic_count", sa.Integer(), nullable=True),
        sa.Column("potion_slots", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )

    op.create_table(
        "mutation_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("before_json", json_t, nullable=True),
        sa.Column("after_json", json_t, nullable=True),
        sa.Column("langfuse_trace_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("mutation_events")
    op.drop_table("run_end")
    op.drop_table("llm_call")
    op.drop_table("agent_decisions")
    op.drop_table("run_frames")
    op.drop_table("run_experiments")
    op.drop_table("runs")
    op.drop_table("experiments")
