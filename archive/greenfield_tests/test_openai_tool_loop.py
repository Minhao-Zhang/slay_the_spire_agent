from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from src.agent_core.tool_registry import build_structured_tools
from src.llm_gateway.openai_chat import OpenAiChatGateway


def test_complete_with_tools_empty_tool_list_falls_back_to_single_shot(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    g = OpenAiChatGateway()
    g._chat = MagicMock()
    g._chat.invoke = MagicMock(
        return_value=AIMessage(content='{"command": null, "rationale": "ok"}'),
    )
    text, usage, subs = g.complete_with_tools(
        system="s",
        user="u",
        tools=[],
        max_rounds=2,
    )
    assert "command" in text
    assert subs == []
    g._chat.invoke.assert_called_once()


def test_complete_with_tools_two_step_json(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    g = OpenAiChatGateway()
    final = '{"command": "END", "rationale": "done"}'
    ai_tool = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "inspect_draw_pile",
                "args": {"question": "peek"},
                "id": "call_1",
                "type": "tool_call",
            },
        ],
    )
    ai_done = AIMessage(content=final)
    bound = MagicMock()
    bound.invoke.side_effect = [ai_tool, ai_done]
    mock_chat = MagicMock()
    mock_chat.bind_tools.return_value = bound
    g._chat = mock_chat

    vm = {
        "combat": {"draw_pile": [], "discard_pile": [], "exhaust_pile": []},
        "inventory": {"deck": []},
    }
    tools = build_structured_tools(vm)
    text, _usage, subs = g.complete_with_tools(
        system="s",
        user="u",
        tools=tools,
        max_rounds=4,
    )
    assert text == final
    assert len(subs) == 1
    assert subs[0]["tool"] == "inspect_draw_pile"
    assert bound.invoke.call_count == 2
