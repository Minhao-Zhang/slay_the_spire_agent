from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agent.v2.state import V2GraphState


def build_spire_decision_graph(agent: Any):
    """Compile the v2 decision graph using the same node contract as the v1 runtime."""

    graph = StateGraph(V2GraphState)
    graph.add_node("build_prompt", agent._build_prompt)
    graph.add_node("plan_turn", agent._plan_turn)
    graph.add_node("run_agent", agent._run_agent)
    graph.add_node("run_tool", agent._run_tool)
    graph.add_node("validate_decision", agent._validate_decision)

    graph.add_edge(START, "build_prompt")
    graph.add_conditional_edges(
        "build_prompt",
        agent._after_build_prompt,
        {
            "plan_turn": "plan_turn",
            "run_agent": "run_agent",
        },
    )
    graph.add_edge("plan_turn", "run_agent")
    graph.add_conditional_edges(
        "run_agent",
        agent._after_agent,
        {
            "run_tool": "run_tool",
            "validate_decision": "validate_decision",
            "end": END,
        },
    )
    graph.add_edge("run_tool", "run_agent")
    graph.add_edge("validate_decision", END)
    return graph.compile()
