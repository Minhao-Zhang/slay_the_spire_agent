# Glossary

- **CommunicationMod**: External game protocol boundary used over stdin/stdout.
- **State ID (`state_id`)**: Deterministic hash identity of normalized game state payload.
- **Turn Key (`turn_key`)**: Context key used to detect sequence queue freshness.
- **Proposal**: Model-generated candidate decision before final authorization/execution.
- **Decision**: Authorized command outcome after validation and approval policy.
- **HITL**: Human-in-the-loop approval workflow.
- **Interrupt**: LangGraph pause point requiring operator/system resume payload.
- **Resume**: `Command(resume=...)` payload that continues interrupted graph execution.
- **Checkpoint**: Durable graph state boundary for recovery/replay.
- **Checkpointer**: Persistence backend for thread-scoped graph state.
- **Store**: Long-term cross-thread memory persistence layer.
- **Canonical Event**: Project-owned structured telemetry record used for replay/audit.
- **Stream Event**: Live output update record (`updates`, `messages`, `custom`) for debugger.
- **Outbox Recovery**: Reconciliation mechanism when checkpoint and event append succeed/fail asymmetrically.
- **Planner Alignment**: Tactical decision relation to strategic advisory plan (`followed`, `partially_followed`, `diverged`).
- **Parity**: Behavioral equivalence between legacy and restart implementations for critical outcomes.
