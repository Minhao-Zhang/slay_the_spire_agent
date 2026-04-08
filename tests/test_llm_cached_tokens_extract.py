"""Unit tests for OpenAI-style cached prompt token extraction from usage objects."""

from types import SimpleNamespace

from src.agent.llm_client import extract_cached_prompt_tokens_from_usage


def test_extract_from_prompt_tokens_details_object() -> None:
    usage = SimpleNamespace(
        prompt_tokens=10_000,
        prompt_tokens_details=SimpleNamespace(cached_tokens=9000),
    )
    assert extract_cached_prompt_tokens_from_usage(usage) == 9000


def test_extract_from_prompt_tokens_details_dict() -> None:
    usage = {"prompt_tokens_details": {"cached_tokens": 42}}
    assert extract_cached_prompt_tokens_from_usage(usage) == 42


def test_extract_from_input_tokens_details_fallback() -> None:
    usage = SimpleNamespace(
        input_tokens_details=SimpleNamespace(cached_tokens=512),
    )
    assert extract_cached_prompt_tokens_from_usage(usage) == 512


def test_extract_missing_returns_none() -> None:
    assert extract_cached_prompt_tokens_from_usage(None) is None
    assert extract_cached_prompt_tokens_from_usage(SimpleNamespace()) is None
    assert extract_cached_prompt_tokens_from_usage({}) is None
