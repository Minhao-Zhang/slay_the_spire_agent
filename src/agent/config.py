from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


from src.repo_paths import PACKAGE_ROOT, REPO_ROOT

DEFAULT_PROMPT_PATH = PACKAGE_ROOT / "agent" / "prompts" / "system_prompt.md"
# Optional full-text corpus when ``include_strategy_corpus`` is True (directory uses many small files).
DEFAULT_STRATEGY_CORPUS_PATH = REPO_ROOT / "data" / "strategy" / "general_principles.md"


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
    # When True: LLM combat encounter plans (see planning.resolve_planning) plus a short
    # heuristic "## TURN PLAN" block prepended on non-combat turns (MAP etc.).
    planner_enabled: bool = False
    combat_plan_max_output_tokens: int = Field(default=2048, ge=256, le=32000)
    combat_plan_max_cards_per_section: int = Field(default=80, ge=10, le=200)
    combat_plan_only_turn_one: bool = True
    prompt_profile: str = "default"
    combat_turn_llm: str = "reasoning"
    non_combat_turn_llm: str = "reasoning"
    combat_plan_llm: str = "reasoning"
    # When True: ReasoningBudgetRouter picks model_key + per-turn reasoning_effort from VM context.
    # When False: same routing as legacy (combat_turn_llm vs non_combat_turn_llm only).
    reasoning_budget_enabled: bool = False
    include_strategy_corpus: bool = False
    strategy_corpus_path: str = ""
    auto_start_next_game: bool = False
    memory_dir: str = "data/memory"
    strategy_dir: str = "data/strategy"
    expert_guides_dir: str = "data/expert_guides"
    memory_retrieval_enabled: bool = True
    max_memory_hits: int = Field(default=8, ge=1, le=64)
    memory_char_budget: int = Field(default=6000, ge=500, le=200_000)
    min_procedural_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    reflection_max_lessons_per_run: int = Field(default=10, ge=1, le=100)
    reflection_enabled: bool = False
    consolidation_every_n_runs: int = Field(default=5, ge=1, le=10_000)
    consolidation_confidence_archive_threshold: float = Field(default=0.2, ge=0.0, le=1.0)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.reasoning_model)

    def resolved_memory_dir(self) -> Path:
        p = Path(self.memory_dir.strip() or "data/memory")
        return p if p.is_absolute() else REPO_ROOT / p

    def resolved_strategy_dir(self) -> Path:
        p = Path(self.strategy_dir.strip() or "data/strategy")
        return p if p.is_absolute() else REPO_ROOT / p

    def resolved_expert_guides_dir(self) -> Path:
        p = Path((self.expert_guides_dir or "").strip() or "data/expert_guides")
        return p if p.is_absolute() else REPO_ROOT / p

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
        auto_start_next_game=os.getenv("AUTO_START_NEXT_GAME", "false").strip().lower() == "true",
        memory_dir=os.getenv("AGENT_MEMORY_DIR", "data/memory").strip() or "data/memory",
        strategy_dir=os.getenv("AGENT_STRATEGY_DIR", "data/strategy").strip() or "data/strategy",
        expert_guides_dir=os.getenv("AGENT_EXPERT_GUIDES_DIR", "data/expert_guides").strip()
        or "data/expert_guides",
        memory_retrieval_enabled=os.getenv("MEMORY_RETRIEVAL_ENABLED", "true").strip().lower()
        == "true",
        max_memory_hits=int(os.getenv("MEMORY_MAX_HITS", "8")),
        memory_char_budget=int(os.getenv("MEMORY_CHAR_BUDGET", "6000")),
        min_procedural_confidence=float(os.getenv("MEMORY_MIN_PROCEDURAL_CONFIDENCE", "0.35")),
        reflection_max_lessons_per_run=int(os.getenv("REFLECTION_MAX_LESSONS_PER_RUN", "10")),
        reasoning_budget_enabled=os.getenv("REASONING_BUDGET_ENABLED", "false").strip().lower() == "true",
        reflection_enabled=os.getenv("REFLECTION_ENABLED", "false").strip().lower() == "true",
        consolidation_every_n_runs=int(os.getenv("CONSOLIDATION_EVERY_N_RUNS", "5")),
        consolidation_confidence_archive_threshold=float(
            os.getenv("CONSOLIDATION_CONFIDENCE_ARCHIVE_THRESHOLD", "0.2")
        ),
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

