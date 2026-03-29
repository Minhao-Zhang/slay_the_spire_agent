/**
 * The monitor’s “LLM user prompt” panel uses the server snapshot field
 * ``agent.llm_user_prompt`` and ``proposal.user_prompt`` (from
 * ``src/ui/dashboard.py``), which call the same ``build_user_prompt`` as the
 * live agent or echo the trace. Do not rebuild the tactical message in the
 * browser — it will drift from what the model sees.
 */

export {};
