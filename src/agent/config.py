from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.repo_paths import PACKAGE_ROOT, REPO_ROOT

DEFAULT_PROMPT_PATH = PACKAGE_ROOT / "agent" / "prompts" / "system_prompt.md"

# Module-level constants (formerly env-driven)
CONNECT_TIMEOUT_SECONDS = 5.0
PROBE_TIMEOUT_SECONDS = 6.0
PROPOSAL_FAILURE_STREAK_LIMIT = 3
COMBAT_PLAN_MAX_OUTPUT_TOKENS = 2048
COMBAT_PLAN_MAX_CARDS_PER_SECTION = 80
MAX_MEMORY_HITS = 8
MEMORY_CHAR_BUDGET = 6000
MIN_PROCEDURAL_CONFIDENCE = 0.35
REFLECTION_MAX_LESSONS_PER_RUN = 10
CONSOLIDATION_ARCHIVE_THRESHOLD = 0.2
HISTORY_COMPACTION_MAX_CHARS = 200_000


class AgentConfig(BaseModel):
    api_base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    decision_model: str = "gpt-5.4"
    decision_reasoning_effort: str = "medium"
    support_model: str = "gpt-5.4-mini"
    support_reasoning_effort: str = "low"
    system_prompt_path: str = str(DEFAULT_PROMPT_PATH)
    agent_mode: str = "propose"
    auto_start_next_game: bool = False
    knowledge_dir: str = "data/knowledge"
    memory_dir: str = "data/memory"
    prompt_profile: str = "default"
    experiment_tag: str = ""
    max_tool_roundtrips: int = Field(default=3, ge=0, le=5)
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=0, ge=0, le=2)
    history_compact_token_threshold: int = Field(default=50_000, ge=0)
    history_keep_recent: int = Field(default=10, ge=0)
    consolidation_every_n_runs: int = Field(default=5, ge=1, le=10_000)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.decision_model)

    @property
    def support_timeout_seconds(self) -> float:
        return max(10.0, self.request_timeout_seconds / 3)

    @property
    def proposal_timeout_seconds(self) -> float:
        return max(120.0, self.request_timeout_seconds * float(self.max_tool_roundtrips + 1))

    @property
    def experiment_id(self) -> str:
        key_fields = (
            self.decision_model,
            self.decision_reasoning_effort,
            self.support_model,
            self.support_reasoning_effort,
            self.prompt_profile,
        )
        return hashlib.sha256("|".join(key_fields).encode()).hexdigest()[:12]

    def resolved_memory_dir(self) -> Path:
        p = Path(self.memory_dir.strip() or "data/memory")
        return p if p.is_absolute() else REPO_ROOT / p

    def resolved_knowledge_dir(self) -> Path:
        p = Path(self.knowledge_dir.strip() or "data/knowledge")
        return p if p.is_absolute() else REPO_ROOT / p


@lru_cache(maxsize=1)
def get_agent_config() -> AgentConfig:
    load_dotenv()
    return AgentConfig(
        api_base_url=os.getenv("API_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("API_KEY", ""),
        decision_model=os.getenv("DECISION_MODEL", "gpt-5.4"),
        decision_reasoning_effort=os.getenv("DECISION_REASONING_EFFORT", "medium").strip().lower(),
        support_model=os.getenv("SUPPORT_MODEL", "gpt-5.4-mini"),
        support_reasoning_effort=os.getenv("SUPPORT_REASONING_EFFORT", "low").strip().lower(),
        system_prompt_path=os.getenv("LLM_SYSTEM_PROMPT_PATH", str(DEFAULT_PROMPT_PATH)),
        agent_mode=os.getenv("AGENT_MODE", "propose"),
        auto_start_next_game=os.getenv("AUTO_START_NEXT_GAME", "false").strip().lower() == "true",
        knowledge_dir=os.getenv("KNOWLEDGE_DIR", "data/knowledge").strip() or "data/knowledge",
        memory_dir=os.getenv("MEMORY_DIR", "data/memory").strip() or "data/memory",
        prompt_profile=os.getenv("PROMPT_PROFILE", "default").strip() or "default",
        experiment_tag=os.getenv("EXPERIMENT_TAG", "").strip(),
        max_tool_roundtrips=int(os.getenv("MAX_TOOL_ROUNDTRIPS", "3")),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
        max_retries=int(os.getenv("MAX_RETRIES", "0")),
        history_compact_token_threshold=int(os.getenv("HISTORY_COMPACT_TOKEN_THRESHOLD", "50000")),
        history_keep_recent=int(os.getenv("HISTORY_KEEP_RECENT", "10")),
        consolidation_every_n_runs=int(os.getenv("CONSOLIDATION_EVERY_N_RUNS", "5")),
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
