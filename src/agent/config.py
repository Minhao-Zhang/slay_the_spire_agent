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
    fast_model: str = "gpt-5-mini"
    system_prompt_path: str = str(DEFAULT_PROMPT_PATH)
    default_mode: str = "propose"
    max_tool_roundtrips: int = Field(default=3, ge=0, le=5)

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
        fast_model=os.getenv("LLM_MODEL_FAST", "gpt-5-mini"),
        system_prompt_path=os.getenv("LLM_SYSTEM_PROMPT_PATH", str(DEFAULT_PROMPT_PATH)),
        default_mode=os.getenv("AGENT_MODE", "propose"),
        max_tool_roundtrips=int(os.getenv("LLM_MAX_TOOL_ROUNDTRIPS", "3")),
    )


def load_system_prompt() -> str:
    cfg = get_agent_config()
    try:
        return Path(cfg.system_prompt_path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return (
            "You are a Slay the Spire assistant. "
            "Write a normal visible reply, then return a <final_decision> block."
        )

