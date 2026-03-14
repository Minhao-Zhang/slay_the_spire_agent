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
    tool_name: Literal["inspect_draw_pile", "inspect_discard_pile", "inspect_exhaust_pile"]
    question: str = ""


class InspectDrawPileTool(BaseModel):
    question: str = ""


class InspectDiscardPileTool(BaseModel):
    question: str = ""


class InspectExhaustPileTool(BaseModel):
    question: str = ""


class FinalDecision(BaseModel):
    chosen_command: str
    why: str = ""


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


class TraceTokenUsage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class PersistedAiLog(BaseModel):
    user_message: str = ""
    assistant_message: str = ""
    status: str = ""
    final_decision: Optional[str] = None
    approval_status: str = ""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    error: str = ""


class AgentTrace(BaseModel):
    decision_id: str
    state_id: str
    turn_key: str
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
    approval_status: str = "pending"
    edited_action: Optional[str] = None
    execution_outcome: str = ""
    latency_ms: Optional[int] = None
    token_usage: TraceTokenUsage = Field(default_factory=TraceTokenUsage)
    error: str = ""

