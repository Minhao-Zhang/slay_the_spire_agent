from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROMPT_PATH = BASE_DIR / "src" / "agent" / "prompts" / "system_prompt.md"


class AgentConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    reasoning_model: str = "gpt-5.4"
    reasoning_effort: str = "medium"  # low, medium, high (Responses API / Chat reasoning)
    fast_model: str = "gpt-5.4-mini"
    fast_reasoning_effort: str = "none"  # low, medium, high, or none (Chat reasoning)
    system_prompt_path: str = str(DEFAULT_PROMPT_PATH)
    default_mode: str = "propose"
    max_tool_roundtrips: int = Field(default=3, ge=0, le=5)
    request_timeout_seconds: float = Field(default=20.0, gt=0)
    connect_timeout_seconds: float = Field(default=5.0, gt=0)
    probe_timeout_seconds: float = Field(default=6.0, gt=0)
    max_retries: int = Field(default=0, ge=0, le=2)
    proposal_timeout_seconds: float = Field(default=20.0, gt=0)
    proposal_failure_streak_limit: int = Field(default=3, ge=1, le=20)
    history_compact_token_threshold: int = Field(default=100_000, ge=0)
    history_keep_recent: int = Field(default=6, ge=0)
    planner_enabled: bool = False
    combat_plan_max_output_tokens: int = Field(default=2048, ge=256, le=32000)
    combat_plan_max_cards_per_section: int = Field(default=80, ge=10, le=200)
    combat_plan_only_turn_one: bool = True

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.reasoning_model)


@lru_cache(maxsize=1)
def get_agent_config() -> AgentConfig:
    load_dotenv()
    return AgentConfig(
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("LLM_API_KEY", ""),
        reasoning_model=os.getenv("LLM_MODEL_REASONING", "gpt-5.4"),
        reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "medium").strip().lower(),
        fast_model=os.getenv("LLM_MODEL_FAST", "gpt-5.4-mini"),
        fast_reasoning_effort=os.getenv("LLM_FAST_REASONING_EFFORT", "none").strip().lower(),
        system_prompt_path=os.getenv("LLM_SYSTEM_PROMPT_PATH", str(DEFAULT_PROMPT_PATH)),
        default_mode=os.getenv("AGENT_MODE", "propose"),
        max_tool_roundtrips=int(os.getenv("LLM_MAX_TOOL_ROUNDTRIPS", "3")),
        request_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
        connect_timeout_seconds=float(os.getenv("LLM_CONNECT_TIMEOUT_SECONDS", "5")),
        probe_timeout_seconds=float(os.getenv("LLM_PROBE_TIMEOUT_SECONDS", "6")),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "0")),
        proposal_timeout_seconds=float(os.getenv("LLM_PROPOSAL_TIMEOUT_SECONDS", "20")),
        proposal_failure_streak_limit=int(os.getenv("LLM_PROPOSAL_FAILURE_STREAK_LIMIT", "3")),
        history_compact_token_threshold=int(
            os.getenv("LLM_HISTORY_COMPACT_TOKEN_THRESHOLD", "100000")
        ),
        history_keep_recent=int(os.getenv("LLM_HISTORY_KEEP_RECENT", "6")),
        planner_enabled=os.getenv("LLM_ENABLE_PLANNER", "false").strip().lower() == "true",
        combat_plan_max_output_tokens=int(
            os.getenv(
                "LLM_PLANNER_COMBAT_MAX_OUTPUT_TOKENS",
                os.getenv("LLM_COMBAT_PLAN_MAX_OUTPUT_TOKENS", "2048"),
            )
        ),
        combat_plan_max_cards_per_section=int(
            os.getenv(
                "LLM_PLANNER_COMBAT_MAX_CARDS_PER_SECTION",
                os.getenv("LLM_COMBAT_PLAN_MAX_CARDS_PER_SECTION", "80"),
            )
        ),
        combat_plan_only_turn_one=os.getenv(
            "LLM_PLANNER_COMBAT_ONLY_TURN_ONE",
            os.getenv("LLM_COMBAT_PLAN_ONLY_TURN_ONE", "true"),
        )
        .strip()
        .lower()
        == "true",
    )


def reload_agent_config() -> AgentConfig:
    get_agent_config.cache_clear()
    return get_agent_config()


def load_system_prompt() -> str:
    cfg = get_agent_config()
    try:
        return Path(cfg.system_prompt_path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return (
            "You are a Slay the Spire assistant. "
            "Write a normal visible reply, then return a <final_decision> block."
        )

