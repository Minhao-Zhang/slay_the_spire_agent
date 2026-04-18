"""SQLAlchemy implementation of :class:`StateRepository`."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from src.persistence.models import (
    AgentDecisionRow,
    BackfillJobRow,
    ExperimentRow,
    LlmCallRow,
    MutationEventRow,
    RunEndRow,
    RunExperimentRow,
    RunFrameRow,
    RunRow,
)
from src.persistence.repository import StateRepository


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def agent_decision_id_for_slot(run_id: str, event_index: int) -> str:
    return str(uuid.uuid5(uuid.UUID(run_id), f"agent_decision:{event_index}"))


def append_mutation_event_to_session(
    s: Session,
    *,
    actor: str,
    target_kind: str,
    target_id: str,
    action: str,
    before: Any | None,
    after: Any | None,
    langfuse_trace_id: str | None = None,
) -> None:
    """Queue a mutation row on ``s`` (caller commits)."""
    s.add(
        MutationEventRow(
            id=str(uuid.uuid4()),
            occurred_at=_utcnow(),
            actor=actor,
            target_kind=target_kind,
            target_id=target_id,
            action=action,
            before_json=before,
            after_json=after,
            langfuse_trace_id=langfuse_trace_id,
        )
    )


class SqlRepository(StateRepository):
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @property
    def session_factory(self):
        """Sessionmaker for transactional batch imports (e.g. backfill)."""
        return self._session_factory

    def _session(self) -> Session:
        return self._session_factory()

    def record_mutation_event(
        self,
        *,
        actor: str,
        target_kind: str,
        target_id: str,
        action: str,
        before: Any | None,
        after: Any | None,
        langfuse_trace_id: str | None = None,
    ) -> None:
        with self._session() as s:
            append_mutation_event_to_session(
                s,
                actor=actor,
                target_kind=target_kind,
                target_id=target_id,
                action=action,
                before=before,
                after=after,
                langfuse_trace_id=langfuse_trace_id,
            )
            s.commit()

    def create_run_in_session(self, s: Session, payload: dict[str, Any]) -> None:
        """Persist run + experiment rows on ``s`` (no commit, no mutation event)."""
        exp = payload.get("experiment")
        run_id = str(payload["run_id"])
        run_dir = str(payload["run_dir_name"])
        if isinstance(exp, dict) and exp.get("id"):
            eid = str(exp["id"])
            existing = s.get(ExperimentRow, eid)
            if not existing:
                s.add(
                    ExperimentRow(
                        id=eid,
                        name=str(exp.get("name") or "default"),
                        description=exp.get("description"),
                        started_at=_utcnow(),
                        ended_at=None,
                        config_hash=exp.get("config_hash"),
                        decision_model=exp.get("decision_model"),
                        reasoning_effort=exp.get("reasoning_effort"),
                        prompt_profile=exp.get("prompt_profile"),
                        memory_weights_json=exp.get("memory_weights_json"),
                    )
                )
        row = RunRow(
            id=run_id,
            run_dir_name=run_dir,
            seed=payload.get("seed"),
            character_class=payload.get("character_class"),
            ascension_level=payload.get("ascension_level"),
            started_at=payload.get("started_at") or _utcnow(),
            ended_at=payload.get("ended_at"),
            status=str(payload.get("status") or "active"),
            storage_engine=str(payload.get("storage_engine") or "sqlite"),
            system_prompt_hash=payload.get("system_prompt_hash"),
            prompt_builder_version=payload.get("prompt_builder_version"),
            reference_data_hash=payload.get("reference_data_hash"),
            config_hash=payload.get("config_hash"),
            knowledge_version_id=payload.get("knowledge_version_id"),
            langfuse_session_id=payload.get("langfuse_session_id") or run_id,
            experiment_id=(str(payload["experiment_id"]) if payload.get("experiment_id") else None),
            source_log_path=payload.get("source_log_path"),
            reflection_status=str(payload.get("reflection_status") or "pending"),
        )
        s.merge(row)
        if payload.get("experiment_id") and isinstance(exp, dict):
            s.merge(
                RunExperimentRow(
                    run_id=run_id,
                    experiment_id=str(payload["experiment_id"]),
                    bucket=exp.get("bucket"),
                    variant=exp.get("variant"),
                )
            )

    def create_run(self, payload: dict[str, Any]) -> None:
        run_id = str(payload["run_id"])
        run_dir = str(payload["run_dir_name"])
        audit = str(payload.get("audit_actor") or "bridge")
        with self._session() as s:
            self.create_run_in_session(s, payload)
            s.commit()
        self.record_mutation_event(
            actor=audit,
            target_kind="run",
            target_id=run_id,
            action="create_run",
            before=None,
            after={"run_dir_name": run_dir},
        )

    def insert_frame_in_session(self, s: Session, payload: dict[str, Any]) -> str:
        frame_id = str(payload.get("frame_id") or uuid.uuid4())
        run_id = str(payload["run_id"])
        event_index = int(payload["event_index"])
        row = RunFrameRow(
            id=frame_id,
            run_id=run_id,
            event_index=event_index,
            state_id=str(payload["state_id"]),
            screen_type=str(payload.get("screen_type") or "NONE"),
            floor=payload.get("floor"),
            act=payload.get("act"),
            turn_key=payload.get("turn_key"),
            ready_for_command=bool(payload.get("ready_for_command")),
            agent_mode=str(payload.get("agent_mode") or "manual"),
            ai_enabled=bool(payload.get("ai_enabled")),
            command_sent=payload.get("command_sent"),
            command_source=payload.get("command_source"),
            action=payload.get("action"),
            is_floor_start=bool(payload.get("is_floor_start")),
            vm_summary_json=payload.get("vm_summary") or {},
            vm_summary_schema_version=int(payload.get("vm_summary_schema_version") or 1),
            meta_json=payload.get("meta") or {},
            meta_schema_version=int(payload.get("meta_schema_version") or 1),
            state_projection_json=payload.get("state_projection") or payload.get("vm_summary") or {},
            state_projection_schema_version=int(payload.get("state_projection_schema_version") or 1),
        )
        s.merge(row)
        return frame_id

    def insert_frame(self, payload: dict[str, Any]) -> str:
        frame_id = str(payload.get("frame_id") or uuid.uuid4())
        run_id = str(payload["run_id"])
        event_index = int(payload["event_index"])
        audit = str(payload.get("audit_actor") or "bridge")
        pl = {**payload, "frame_id": frame_id}
        with self._session() as s:
            self.insert_frame_in_session(s, pl)
            s.commit()
        self.record_mutation_event(
            actor=audit,
            target_kind="run_frame",
            target_id=frame_id,
            action="insert_frame",
            before=None,
            after={"run_id": run_id, "event_index": event_index},
        )
        return frame_id

    def _ensure_decision_row(
        self,
        s: Session,
        *,
        run_id: str,
        event_index: int,
        state_id: str,
        client_decision_id: str,
        turn_key: str | None,
    ) -> str:
        did = agent_decision_id_for_slot(run_id, event_index)
        existing = s.get(AgentDecisionRow, did)
        if existing:
            if client_decision_id and existing.client_decision_id != client_decision_id:
                existing.client_decision_id = client_decision_id
            return did
        s.add(
            AgentDecisionRow(
                id=did,
                run_id=run_id,
                event_index=event_index,
                client_decision_id=client_decision_id or "",
                state_id=state_id,
                turn_key=turn_key,
                status="building_prompt",
                approval_status="pending",
                execution_outcome="",
                final_decision_sequence_json=[],
                tool_names_json=[],
                prompt_profile="default",
                strategist_ran=False,
                planner_ran=False,
                react_ran=False,
            )
        )
        return did

    def upsert_decision_final_in_session(self, s: Session, payload: dict[str, Any]) -> str:
        run_id = str(payload["run_id"])
        event_index = int(payload["event_index"])
        decision_pk = agent_decision_id_for_slot(run_id, event_index)
        self._ensure_decision_row(
            s,
            run_id=run_id,
            event_index=event_index,
            state_id=str(payload["state_id"]),
            client_decision_id=str(payload.get("client_decision_id") or ""),
            turn_key=payload.get("turn_key"),
        )
        stmt = (
            update(AgentDecisionRow)
            .where(AgentDecisionRow.id == decision_pk)
            .values(
                client_decision_id=str(payload.get("client_decision_id") or ""),
                state_id=str(payload["state_id"]),
                turn_key=payload.get("turn_key"),
                status=str(payload.get("status") or "executed"),
                approval_status=str(payload.get("approval_status") or "pending"),
                execution_outcome=str(payload.get("execution_outcome") or ""),
                final_decision=payload.get("final_decision"),
                final_decision_sequence_json=payload.get("final_decision_sequence") or [],
                validation_error=payload.get("validation_error"),
                error=payload.get("error"),
                tool_names_json=payload.get("tool_names") or [],
                prompt_profile=str(payload.get("prompt_profile") or "default"),
                experiment_id=payload.get("experiment_id"),
                experiment_tag=payload.get("experiment_tag"),
                strategist_ran=bool(payload.get("strategist_ran")),
                planner_ran=bool(payload.get("planner_ran", False)),
                react_ran=bool(payload.get("react_ran", False)),
                deck_size=payload.get("deck_size"),
                user_message_sha256=payload.get("user_message_sha256"),
                assistant_message_sha256=payload.get("assistant_message_sha256"),
            )
        )
        s.execute(stmt)
        return decision_pk

    def upsert_decision_final(self, payload: dict[str, Any]) -> None:
        run_id = str(payload["run_id"])
        event_index = int(payload["event_index"])
        decision_pk = agent_decision_id_for_slot(run_id, event_index)
        audit = str(payload.get("audit_actor") or "bridge")
        with self._session() as s:
            self.upsert_decision_final_in_session(s, payload)
            s.commit()
        self.record_mutation_event(
            actor=audit,
            target_kind="agent_decision",
            target_id=decision_pk,
            action="upsert_decision_final",
            before=None,
            after={"run_id": run_id, "event_index": event_index},
        )

    def upsert_run_end_in_session(self, s: Session, payload: dict[str, Any]) -> None:
        run_id = str(payload["run_id"])
        s.merge(
            RunEndRow(
                run_id=run_id,
                state_id=payload.get("state_id"),
                victory=payload.get("victory"),
                score=payload.get("score"),
                screen_name=payload.get("screen_name"),
                floor=payload.get("floor"),
                act=payload.get("act"),
                gold=payload.get("gold"),
                current_hp=payload.get("current_hp"),
                max_hp=payload.get("max_hp"),
                deck_size=payload.get("deck_size"),
                relic_count=payload.get("relic_count"),
                potion_slots=payload.get("potion_slots"),
                recorded_at=payload.get("recorded_at"),
            )
        )
        s.execute(update(RunRow).where(RunRow.id == run_id).values(status="ended", ended_at=_utcnow()))

    def upsert_run_end(self, payload: dict[str, Any]) -> None:
        run_id = str(payload["run_id"])
        audit = str(payload.get("audit_actor") or "bridge")
        with self._session() as s:
            self.upsert_run_end_in_session(s, payload)
            s.commit()
        self.record_mutation_event(
            actor=audit,
            target_kind="run_end",
            target_id=run_id,
            action="upsert_run_end",
            before=None,
            after={"run_id": run_id},
        )

    def record_llm_call_in_session(self, s: Session, payload: dict[str, Any]) -> str:
        call_id = str(payload.get("id") or uuid.uuid4())
        run_id = str(payload["run_id"])
        event_index = payload.get("event_index")
        agent_decision_id: str | None = None
        if event_index is not None:
            ei = int(event_index)
            agent_decision_id = self._ensure_decision_row(
                s,
                run_id=run_id,
                event_index=ei,
                state_id=str(payload.get("state_id") or ""),
                client_decision_id=str(payload.get("client_decision_id") or ""),
                turn_key=payload.get("turn_key"),
            )
        row = LlmCallRow(
            id=call_id,
            run_id=run_id,
            frame_id=payload.get("frame_id"),
            agent_decision_id=agent_decision_id,
            reflection_run_id=payload.get("reflection_run_id"),
            stage=str(payload["stage"]),
            round_index=int(payload.get("round_index") or 1),
            model=payload.get("model"),
            reasoning_effort=payload.get("reasoning_effort"),
            input_tokens=payload.get("input_tokens"),
            cached_input_tokens=payload.get("cached_input_tokens"),
            uncached_input_tokens=payload.get("uncached_input_tokens"),
            output_tokens=payload.get("output_tokens"),
            reasoning_tokens=payload.get("reasoning_tokens"),
            total_tokens=payload.get("total_tokens"),
            latency_ms=payload.get("latency_ms"),
            status=str(payload.get("status") or "ok"),
            error_code=payload.get("error_code"),
            langfuse_trace_id=str(payload["langfuse_trace_id"]),
            langfuse_observation_id=str(payload["langfuse_observation_id"]),
            prompt_profile=payload.get("prompt_profile"),
            knowledge_version_id=payload.get("knowledge_version_id"),
            created_at=payload.get("created_at") or _utcnow(),
        )
        s.add(row)
        return call_id

    def record_llm_call(self, payload: dict[str, Any]) -> str:
        call_id = str(payload.get("id") or uuid.uuid4())
        run_id = str(payload["run_id"])
        audit = str(payload.get("audit_actor") or "bridge")
        pl = {**payload, "id": call_id}
        with self._session() as s:
            self.record_llm_call_in_session(s, pl)
            s.commit()
        self.record_mutation_event(
            actor=audit,
            target_kind="llm_call",
            target_id=call_id,
            action="record_llm_call",
            before=None,
            after={"stage": payload.get("stage"), "run_id": run_id},
            langfuse_trace_id=payload.get("langfuse_trace_id"),
        )
        return call_id

    def mark_run_ended(self, run_id: str, *, ended_at: dt.datetime | None = None) -> None:
        when = ended_at or _utcnow()
        with self._session() as s:
            s.execute(update(RunRow).where(RunRow.id == run_id).values(ended_at=when, status="ended"))
            s.commit()

    def get_run_row_by_dir_name(self, run_dir_name: str) -> RunRow | None:
        with self._session() as s:
            return s.query(RunRow).filter(RunRow.run_dir_name == run_dir_name).first()

    def get_run_row(self, run_id: str) -> RunRow | None:
        with self._session() as s:
            return s.get(RunRow, run_id)

    def list_run_dir_names_desc(self) -> list[str]:
        """Basenames for dashboard ``GET /api/runs`` when reading from SQL.

        Order matches the file-backed listing: ``sorted(names, reverse=True)``.
        """
        with self._session() as s:
            rows = s.query(RunRow.run_dir_name).order_by(RunRow.run_dir_name.desc()).all()
        return [str(r[0]) for r in rows if r[0]]

    def get_backfill_job_by_run_dir(self, run_dir: str) -> BackfillJobRow | None:
        with self._session() as s:
            return s.query(BackfillJobRow).filter(BackfillJobRow.run_dir == run_dir).first()

    def save_backfill_job(self, job: BackfillJobRow) -> None:
        with self._session() as s:
            s.merge(job)
            s.commit()

    def delete_backfill_job(self, job_id: str) -> None:
        with self._session() as s:
            row = s.get(BackfillJobRow, job_id)
            if row:
                s.delete(row)
            s.commit()

    def delete_backfill_job_by_run_dir(self, run_dir: str) -> None:
        with self._session() as s:
            j = s.query(BackfillJobRow).filter(BackfillJobRow.run_dir == run_dir).first()
            if j:
                s.delete(j)
            s.commit()

    def list_run_frames_ordered(self, run_id: str) -> list[RunFrameRow]:
        with self._session() as s:
            return (
                s.query(RunFrameRow)
                .filter(RunFrameRow.run_id == run_id)
                .order_by(RunFrameRow.event_index.asc())
                .all()
            )

    def list_agent_decisions_ordered(self, run_id: str) -> list[AgentDecisionRow]:
        with self._session() as s:
            return (
                s.query(AgentDecisionRow)
                .filter(AgentDecisionRow.run_id == run_id)
                .order_by(AgentDecisionRow.event_index.asc())
                .all()
            )

    def get_run_end_for_run(self, run_id: str) -> RunEndRow | None:
        with self._session() as s:
            return s.get(RunEndRow, run_id)

    def list_llm_calls_for_run(self, run_id: str) -> list[LlmCallRow]:
        with self._session() as s:
            return s.query(LlmCallRow).filter(LlmCallRow.run_id == run_id).order_by(LlmCallRow.created_at.asc()).all()

    def delete_run_cascade(self, run_id: str) -> None:
        """Remove a run and dependent rows (used to retry failed backfill)."""
        with self._session() as s:
            s.execute(delete(LlmCallRow).where(LlmCallRow.run_id == run_id))
            s.execute(delete(AgentDecisionRow).where(AgentDecisionRow.run_id == run_id))
            s.execute(delete(RunFrameRow).where(RunFrameRow.run_id == run_id))
            s.execute(delete(RunEndRow).where(RunEndRow.run_id == run_id))
            s.execute(delete(RunExperimentRow).where(RunExperimentRow.run_id == run_id))
            row = s.get(RunRow, run_id)
            if row:
                s.delete(row)
            s.commit()


def get_sql_repository() -> SqlRepository | None:
    from src.persistence.engine import get_engine, get_session_factory
    from src.persistence.models import Base
    from src.persistence.settings import get_persistence_settings

    if not get_persistence_settings().sql_shadow_or_primary:
        return None
    eng = get_engine()
    if eng.dialect.name == "sqlite":
        Base.metadata.create_all(eng)
    return SqlRepository(get_session_factory())
