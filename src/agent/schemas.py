from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


AgentMode = Literal["manual", "propose", "auto"]
TraceStatus = Literal[
    "idle",
    "building_prompt",
    "running",
    "awaiting_approval",
    "approved",
    "rejected",
    "invalid",
    "stale",
    "executed",
    "error",
    "disabled",
]


class ToolRequest(BaseModel):
    tool_name: Literal[
        "inspect_draw_pile",
        "inspect_discard_pile",
        "inspect_exhaust_pile",
        "inspect_deck_summary",
        "inspect_full_deck",
    ]
    question: str = ""


class InspectDrawPileTool(BaseModel):
    question: str = ""


class InspectDiscardPileTool(BaseModel):
    question: str = ""


class InspectExhaustPileTool(BaseModel):
    question: str = ""


class InspectDeckSummaryTool(BaseModel):
    question: str = ""


class InspectFullDeckTool(BaseModel):
    question: str = ""


class FinalDecision(BaseModel):
    chosen_commands: list[str] = Field(default_factory=list)
    # Backward compatibility: if only chosen_command is provided, wrap it
    chosen_command: str = ""
    chosen_label: str = ""
    action_type: str = ""
    choice_index: Optional[int] = None
    target_name: str = ""

    def model_post_init(self, __context: Any) -> None:
        # Normalize: if chosen_commands is empty but chosen_command is set, wrap it
        if not self.chosen_commands and self.chosen_command:
            self.chosen_commands = [self.chosen_command]
        # Keep chosen_command in sync with the first item for backward compat
        if self.chosen_commands and not self.chosen_command:
            self.chosen_command = self.chosen_commands[0]


class ParsedAgentTurn(BaseModel):
    reasoning: str = ""
    response: str = ""
    tool_request: Optional[ToolRequest] = None
    final_decision: Optional[FinalDecision] = None


class ValidationResult(BaseModel):
    valid: bool = False
    error: str = ""
    matched_command: Optional[str] = None
    matched_label: Optional[str] = None


def compute_uncached_input_tokens(
    input_tokens: Optional[int], cached_input_tokens: Optional[int]
) -> Optional[int]:
    """Tokens read from prompt that were not served from cache (input_total − cached_subset)."""
    if input_tokens is None:
        return None
    inn = int(input_tokens)
    if cached_input_tokens is None:
        return inn
    return max(0, inn - int(cached_input_tokens))


class TraceTokenUsage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    # OpenAI-style: usage.prompt_tokens_details.cached_tokens (also tries input_tokens_details).
    cached_input_tokens: Optional[int] = None
    uncached_input_tokens: Optional[int] = None


class TraceLlmCall(BaseModel):
    round_index: int
    stage: str = ""
    previous_response_id: Optional[str] = None
    input_messages: list[dict[str, Any]] = Field(default_factory=list)


class PersistedAiLog(BaseModel):
    decision_id: str = ""
    state_id: str = ""
    turn_key: str = ""
    user_message: str = ""
    assistant_message: str = ""
    status: str = ""
    final_decision: Optional[str] = None
    final_decision_sequence: list[str] = Field(default_factory=list)
    approval_status: str = ""
    execution_outcome: str = ""
    latency_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    uncached_input_tokens: Optional[int] = None
    tool_names: list[str] = Field(default_factory=list)
    planner_summary: str = ""
    combat_plan_generated: bool = False
    combat_plan_text_preview: str = ""
    combat_plan_error: str = ""
    combat_plan_latency_ms: Optional[int] = None
    combat_plan_model_used: str = ""
    validation_error: str = ""
    error: str = ""
    prompt_profile: str = "default"
    llm_model_used: str = ""
    reasoning_effort_used: str = ""
    lessons_retrieved: int = 0
    experiment_tag: str = ""
    experiment_id: str = ""
    strategist_ran: bool = False
    deck_size: Optional[int] = None
    retrieved_lesson_ids: list[str] = Field(default_factory=list)


class AgentTrace(BaseModel):
    decision_id: str
    state_id: str
    turn_key: str
    langfuse_trace_id: str = Field(
        default="",
        description="32-char hex Langfuse trace id; groups model calls for this decision.",
    )
    timestamp: str
    update_seq: int = 0
    status: TraceStatus
    agent_mode: AgentMode
    floor: Optional[int] = None
    turn: Optional[int] = None
    screen_type: str = "NONE"
    system_prompt: str = ""
    user_prompt: str = ""
    reasoning_text: str = ""
    reasoning_summary_text: str = ""
    response_text: str = ""
    raw_output: str = ""
    parsed_proposal: Optional[dict[str, Any]] = None
    validation: ValidationResult = Field(default_factory=ValidationResult)
    final_decision: Optional[str] = None
    final_decision_sequence: list[str] = Field(default_factory=list)
    approval_status: str = "pending"
    edited_action: Optional[str] = None
    execution_outcome: str = ""
    latency_ms: Optional[int] = None
    token_usage: TraceTokenUsage = Field(default_factory=TraceTokenUsage)
    tool_names: list[str] = Field(default_factory=list)
    planner_summary: str = ""
    combat_plan_generated: bool = False
    combat_plan_text_preview: str = ""
    combat_plan_error: str = ""
    combat_plan_latency_ms: Optional[int] = None
    combat_plan_model_used: str = ""
    llm_calls: list[TraceLlmCall] = Field(default_factory=list)
    error: str = ""
    prompt_profile: str = "default"
    llm_model_used: str = ""
    reasoning_effort_used: str = ""
    lessons_retrieved: int = 0
    experiment_tag: str = ""
    experiment_id: str = ""
    strategist_ran: bool = False
    deck_size: Optional[int] = None
    retrieved_lesson_ids: list[str] = Field(default_factory=list)

