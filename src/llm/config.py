import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file (if present)
load_dotenv()

@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model_reasoning: str
    model_fast: str

def get_config() -> LLMConfig:
    """Reads environment variables and returns a configuration object."""
    return LLMConfig(
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("LLM_API_KEY", ""),
        model_reasoning=os.getenv("LLM_MODEL_REASONING", "gpt-5-mini"),
        model_fast=os.getenv("LLM_MODEL_FAST", "gpt-5.4"),
    )

# Global configuration instance
config = get_config()
