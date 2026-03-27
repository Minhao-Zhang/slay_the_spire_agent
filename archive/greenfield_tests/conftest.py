from __future__ import annotations

import pytest

import src.control_api.app as control_api_app
from src.control_api.agent_runtime import reset_agent_runtime_for_tests
from src.decision_engine.proposer import set_llm_gateway_for_tests
from src.memory.runtime import reset_app_memory_store_for_tests


@pytest.fixture(autouse=True)
def _reset_llm_gateway_override() -> None:
    set_llm_gateway_for_tests(None)
    yield
    set_llm_gateway_for_tests(None)


@pytest.fixture(autouse=True)
def _reset_memory_store() -> None:
    reset_app_memory_store_for_tests()
    yield
    reset_app_memory_store_for_tests()


@pytest.fixture(autouse=True)
def _reset_agent_runtime() -> None:
    reset_agent_runtime_for_tests()
    yield
    reset_agent_runtime_for_tests()


@pytest.fixture(autouse=True)
def _reset_control_api_snapshot() -> None:
    """Isolate HTTP/WS snapshot state across tests (trace tests also hit the FastAPI app)."""
    with control_api_app._lock:
        control_api_app._snapshot.clear()
        control_api_app._snapshot.update(
            {
                "view_model": None,
                "state_id": None,
                "ingress": None,
                "error": None,
                "agent": None,
            },
        )
    yield
