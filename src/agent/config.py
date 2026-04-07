from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


from src.repo_paths import PACKAGE_ROOT, REPO_ROOT

DEFAULT_PROMPT_PATH = PACKAGE_ROOT / "agent" / "prompts" / "system_prompt.md"
DEFAULT_STRATEGY_CORPUS_PATH = REPO_ROOT / "data" / "strategy" / "curated_strategy.md"


def _normalize_llm_slot(raw: str, default: str = "reasoning") -> str:
    v = (raw or default).strip().lower()
    return "fast" if v == "fast" else "reasoning"


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
    reasoning_request_timeout_seconds: float = Field(default=60.0, gt=0)
    fast_request_timeout_seconds: float = Field(default=20.0, gt=0)
    connect_timeout_seconds: float = Field(default=5.0, gt=0)
    probe_timeout_seconds: float = Field(default=6.0, gt=0)
    max_retries: int = Field(default=0, ge=0, le=2)
    proposal_timeout_seconds: float = Field(default=120.0, gt=0)
    proposal_failure_streak_limit: int = Field(default=3, ge=1, le=20)
    history_compact_token_threshold: int = Field(default=50_000, ge=0)
    history_keep_recent: int = Field(default=10, ge=0)
    history_tokenizer_model: str = ""
    history_compaction_transcript_max_chars: int = Field(default=200_000, ge=10_000)
    planner_enabled: bool = False
    combat_plan_max_output_tokens: int = Field(default=2048, ge=256, le=32000)
    combat_plan_max_cards_per_section: int = Field(default=80, ge=10, le=200)
    combat_plan_only_turn_one: bool = True
    prompt_profile: str = "default"
    combat_turn_llm: str = "reasoning"
    non_combat_turn_llm: str = "reasoning"
    combat_plan_llm: str = "reasoning"
    include_strategy_corpus: bool = False
    strategy_corpus_path: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.reasoning_model)

    def resolved_strategy_corpus_path(self) -> Path | None:
        if not self.include_strategy_corpus:
            return None
        raw = (self.strategy_corpus_path or "").strip()
        if raw:
            return Path(raw)
        return DEFAULT_STRATEGY_CORPUS_PATH if DEFAULT_STRATEGY_CORPUS_PATH.exists() else None


@lru_cache(maxsize=1)
def get_agent_config() -> AgentConfig:
    load_dotenv()
    max_tool_roundtrips = int(os.getenv("LLM_MAX_TOOL_ROUNDTRIPS", "3"))
    reasoning_request_timeout_seconds = float(
        os.getenv("LLM_TIMEOUT_SECONDS_REASONING", os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    )
    proposal_timeout_env = os.getenv("LLM_PROPOSAL_TIMEOUT_SECONDS")
    if proposal_timeout_env is not None and str(proposal_timeout_env).strip() != "":
        proposal_timeout_seconds = float(proposal_timeout_env)
    else:
        # One proposal run can include multiple LLM HTTP calls (e.g. native tools: call + continuation).
        proposal_timeout_seconds = max(
            120.0,
            reasoning_request_timeout_seconds * float(max_tool_roundtrips + 1),
        )
    return AgentConfig(
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("LLM_API_KEY", ""),
        reasoning_model=os.getenv("LLM_MODEL_REASONING", "gpt-5.4"),
        reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "medium").strip().lower(),
        fast_model=os.getenv("LLM_MODEL_FAST", "gpt-5.4-mini"),
        fast_reasoning_effort=os.getenv("LLM_FAST_REASONING_EFFORT", "none").strip().lower(),
        system_prompt_path=os.getenv("LLM_SYSTEM_PROMPT_PATH", str(DEFAULT_PROMPT_PATH)),
        default_mode=os.getenv("AGENT_MODE", "propose"),
        max_tool_roundtrips=max_tool_roundtrips,
        request_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
        reasoning_request_timeout_seconds=reasoning_request_timeout_seconds,
        fast_request_timeout_seconds=float(
            os.getenv("LLM_TIMEOUT_SECONDS_FAST", os.getenv("LLM_TIMEOUT_SECONDS", "20"))
        ),
        connect_timeout_seconds=float(os.getenv("LLM_CONNECT_TIMEOUT_SECONDS", "5")),
        probe_timeout_seconds=float(os.getenv("LLM_PROBE_TIMEOUT_SECONDS", "6")),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "0")),
        proposal_timeout_seconds=proposal_timeout_seconds,
        proposal_failure_streak_limit=int(os.getenv("LLM_PROPOSAL_FAILURE_STREAK_LIMIT", "3")),
        history_compact_token_threshold=int(
            os.getenv("LLM_HISTORY_COMPACT_TOKEN_THRESHOLD", "50000")
        ),
        history_keep_recent=int(os.getenv("LLM_HISTORY_KEEP_RECENT", "10")),
        history_tokenizer_model=os.getenv("LLM_HISTORY_TOKENIZER_MODEL", "").strip(),
        history_compaction_transcript_max_chars=int(
            os.getenv("LLM_HISTORY_COMPACTION_TRANSCRIPT_MAX_CHARS", "200000")
        ),
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
        prompt_profile=os.getenv("LLM_PROMPT_PROFILE", "default").strip() or "default",
        combat_turn_llm=_normalize_llm_slot(os.getenv("LLM_COMBAT_TURN_MODEL", "reasoning")),
        non_combat_turn_llm=_normalize_llm_slot(os.getenv("LLM_NON_COMBAT_TURN_MODEL", "reasoning")),
        combat_plan_llm=_normalize_llm_slot(os.getenv("LLM_COMBAT_PLAN_MODEL", "reasoning")),
        include_strategy_corpus=os.getenv("LLM_INCLUDE_STRATEGY_CORPUS", "false").strip().lower() == "true",
        strategy_corpus_path=os.getenv("LLM_STRATEGY_CORPUS_PATH", "").strip(),
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

