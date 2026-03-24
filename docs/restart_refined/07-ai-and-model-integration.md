# AI and Model Integration

## Integration Strategy
- Use LangChain v1 model interfaces.
- Prefer provider-native structured output where robust.
- Use tool-based structured fallback for cross-provider compatibility.
- Keep provider details isolated to `llm_gateway`.

## API Mode Compatibility

### OpenAI Responses API
- Preferred for rich typed output and reasoning compatibility.
- Better fit for reasoning/content block normalization.

### OpenAI Chat Completions API
- Fully supported for text streaming and command generation.
- Reasoning visibility may be reduced; treat reasoning as optional.

## Structured Output Requirements
- Decision schema must be strict and versioned.
- No execution from unvalidated model output.
- Validation stage must resolve/normalize against legal actions.

## Tool Loop Requirements
- Tool calls are bounded and observable.
- Unknown/invalid tool requests are validated out safely.
- Tool call and tool result traces stay paired for replay coherence.

## Streaming Requirements
- LangGraph stream modes: `updates`, `messages`, `custom`.
- Canonical stream envelope must abstract provider differences.
- Frontend receives normalized blocks; provider extras are optional metadata.

## Reasoning Handling Policy
- Reasoning is observability context, not execution authority.
- Reasoning visibility profile-gated:
  - local debug may show full/extended reasoning,
  - remote/prod-like defaults to summary/redacted view.

## Provider Failure Policy
- On provider schema drift, fail-open to minimum canonical text stream.
- Mark parse issues in telemetry without crashing orchestration.
- On stream interruption, preserve partial context and continue safe lifecycle handling.

## Performance Targets
- model output chunks visible quickly in debugger (< 250ms median render from receive path).
- usage summaries captured when available; marked incomplete otherwise.
