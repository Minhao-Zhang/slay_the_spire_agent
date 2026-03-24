# Memory Strategy

## Purpose
Define short-term and long-term memory design for LangGraph runtime, including retention, summarization, and production storage choices.

## Memory Types
- **Short-term memory**: thread-scoped state persisted by checkpointer.
- **Long-term memory**: cross-thread/user/application memory persisted by Store.

## Short-Term Memory (Thread State)
- Always include `thread_id` for message continuity.
- Keep conversation/state channels bounded to avoid context-window overflow.
- Approved strategies:
  - trim messages (`trim_messages` token-based)
  - remove messages (`RemoveMessage` with valid message graph constraints)
  - summarize older turns and keep rolling summary in state
- For message channels, use reducer-safe state models (e.g., `MessagesState` + reducers).

## Long-Term Memory (Store)
- Access Store through `Runtime` injection in nodes.
- Recommended namespace patterns:
  - `("memories", user_id)` for user profile/preferences
  - `("run_artifacts", run_id)` for run-level learned artifacts
  - `("strategy", class_id)` for class/archetype strategy memory
- Persist only normalized/validated memory records (not raw prompt dumps).

## Retrieval and Semantic Search
- Support both key lookup and semantic search.
- Semantic index enabled per environment where embedding cost and latency are acceptable.
- Limit semantic retrieval count and include score/metadata in telemetry.

## Production Storage Recommendations
- Short-term checkpointer: Postgres (sync/async as needed).
- Long-term store: Postgres or Redis, depending on read/write patterns.
- Dev/test: in-memory checkpointer/store only.
- Run `setup()` migrations as explicit deployment step.

## Memory Safety and Quality
- Memory writes should be idempotent when possible.
- Store writes must be schema-validated.
- Never store secrets/credentials in memory store.
- Record memory read/write events for audit and replay explainability.

## Context Management Policy
- Hard token budget per model profile.
- Summarize before truncating when preserving intent is critical.
- Keep tool-call coherence (assistant tool call must remain paired with tool result).
- Guard against invalid message histories after deletions.

## Suggested Rollout
1. Add minimal short-term message memory with checkpointer.
2. Add bounded trimming policy.
3. Add running summary node for long threads.
4. Add long-term store with user namespace.
5. Add semantic retrieval and quality gates.
