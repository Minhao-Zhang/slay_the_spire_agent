from __future__ import annotations

from src.application.dto.command_request import CommandRequest


class TurnEngine:
    """Application-level orchestration entrypoint for the future v2 runtime."""

    def __init__(
        self,
        state_normalizer,
        legal_action_builder,
        proposal_manager,
        execution_manager,
        approval_manager,
        projection_service,
        event_bus,
    ):
        self.state_normalizer = state_normalizer
        self.legal_action_builder = legal_action_builder
        self.proposal_manager = proposal_manager
        self.execution_manager = execution_manager
        self.approval_manager = approval_manager
        self.projection_service = projection_service
        self.event_bus = event_bus

    def handle_raw_state(self, raw_payload: dict) -> CommandRequest | None:
        raise NotImplementedError("TurnEngine.handle_raw_state() is part of the v2 rewrite scaffold.")
