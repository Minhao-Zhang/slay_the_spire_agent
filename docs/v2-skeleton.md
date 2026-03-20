# V2 LangGraph Skeleton

This branch adds a compatibility-first v2 scaffold that preserves the current
runtime while introducing the main architectural seam needed for the rewrite:

- a provider protocol for model backends
- a legacy OpenAI-compatible adapter
- an externally built LangGraph graph
- a dedicated v2 runtime class
- an opt-in runtime switch from `src/main.py`

## Goals of this scaffold

The intent is to let the project evolve toward a cleaner rewrite without
breaking the current game loop, dashboard, or trace contracts.

This first pass keeps the current data flow and trace shapes but moves the
decision runtime toward explicit interfaces that can later support:

- multiple OpenAI-compatible endpoints
- scene-specific graphs
- a more formal application layer
- typed domain/application DTOs

## New modules

### `src/agent/v2/protocols.py`

Defines the `LlmProvider` protocol and the `LlmTurnResult` contract used by the
LangGraph runtime.

### `src/agent/v2/adapters/legacy_openai.py`

Wraps the existing `src.agent.llm_client.LLMClient` behind the new provider
protocol, preserving current OpenAI-compatible behavior.

### `src/agent/v2/graph_builder.py`

Compiles the decision graph separately from the runtime class. This keeps
LangGraph as the orchestration layer while moving graph construction into its
own reusable unit.

### `src/agent/v2/runtime.py`

Introduces `V2SpireDecisionAgent`, which reuses the current node methods from
`SpireDecisionAgent` but swaps in the provider abstraction and external graph
builder.

### `src/agent/v2/deps.py`

Lightweight dependency bundle for future node extraction and scene-specific
graph wiring.

## Opt-in usage

The new runtime is **off by default**. To run the v2 scaffold:

```bash
SPIRE_AGENT_RUNTIME=v2 uv run python src/main.py
```

If `SPIRE_AGENT_RUNTIME` is unset, the existing v1 runtime stays in place.

## What this branch does not do yet

This is still a scaffold, not the full rewrite. It does **not** yet:

- split the app into domain/application/adapters packages
- introduce scene-specific graphs
- replace dict-heavy state handling with typed models
- move dashboard/control flow into a separate application layer
- swap persistence/logging to versioned event models

## Recommended next implementation steps

1. Extract scene-specific graph nodes from `src.agent.graph`.
2. Define typed decision context objects per scene.
3. Introduce provider capability models instead of implicit attribute access.
4. Route `src/main.py` through an application-level turn engine.
5. Move raw state normalization and legal action generation into typed services.
