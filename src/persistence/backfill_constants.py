"""Canonical ``backfill_jobs`` status and stage strings (Phase 1 design)."""

# status
BF_STATUS_PENDING = "pending"
BF_STATUS_RUNNING = "running"
BF_STATUS_SUCCEEDED = "succeeded"
BF_STATUS_FAILED = "failed"

# stage (ordered progress within a run import)
BF_STAGE_RUNS = "runs"
BF_STAGE_FRAMES = "frames"
BF_STAGE_DECISIONS = "decisions"
BF_STAGE_LLM_CALLS = "llm_calls"
BF_STAGE_RUN_END = "run_end"
BF_STAGE_DONE = "done"
