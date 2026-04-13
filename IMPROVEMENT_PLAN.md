# Slay the Spire Agent — Improvement Plan

> Generated from audit discussion, April 2026.
> This document is the authoritative plan for the next stage of agent improvements.

---

## High-Level Vision: What "Next Stage" Looks Like

The agent currently works as a prompt-heavy LLM wrapper: game state goes in, a command comes out. The next stage transforms it into a **knowledge-grounded strategic agent** where:

1. The LLM receives **factual game mechanics** it can rely on instead of hallucinating rules.
2. A **knowledge layer** (reorganized, chunked, tagged) feeds contextual strategy to every decision.
3. **Computed analysis** (map DAG paths, deck trajectory) supplements LLM reasoning with quantitative data.
4. **Reflection and memory** become a real closed loop: lessons are validated against outcomes, not just appended.
5. **Observability** is rich enough to evaluate changes within 5-10 runs, not 50.

The work is organized into **4 phases**, each independently shippable and testable.

---

## Configuration Redesign: Always-On Architecture

This section describes the new configuration model that threads through all phases. The current `.env` has 44 variables organized around feature flags (`LLM_ENABLE_PLANNER`, `REASONING_BUDGET_ENABLED`, `MEMORY_RETRIEVAL_ENABLED`, `REFLECTION_ENABLED`). This creates a combinatorial explosion of 16+ configurations that can't be individually evaluated.

**This is a full rewrite. No backward compatibility with old `.env` variable names. Old `.env` files must be rewritten from the new template.**

### Design Principle: No Feature Flags

**Everything is always on.** Planning, memory retrieval, reflection — these are core architecture, not optional add-ons. The system has three runtime layers:

| Layer | Role | Model Used | Runs When |
|---|---|---|---|
| **Strategist** | Knowledge selection, strategic notes, turn plan | Support model | Every scene change |
| **Combat Planner** | Battle guide for the current encounter | Decision model | Combat turn 1 |
| **Decision Agent** | The actual card play / action | Decision model | Every turn |
| **Reflector** (post-run) | Extract lessons from the run | Decision model | After each run |
| **Consolidator** (post-run) | Archive bad lessons | No model (deterministic) | Every N runs |

### Two Models, Clear Roles

- **Decision model** (`DECISION_MODEL` + `DECISION_REASONING_EFFORT`) — the primary model. Used for all player-facing decisions, combat plans, and reflection. This determines gameplay quality.
- **Support model** (`SUPPORT_MODEL` + `SUPPORT_REASONING_EFFORT`) — the lightweight model. Used for the strategist and history compaction. These are internal plumbing calls that need to be fast and cheap.

Both models have **explicit, independent reasoning effort controls**. This lets you experiment with combinations like a strong decision model at high effort + a cheap support model at no effort, or the same model for both at different effort levels.

No per-screen model routing. Every main decision uses `DECISION_MODEL`. If you want to experiment with a cheaper model, change one variable and the entire run uses it. Easy to compare across runs.

### New `.env.example`

```env
# ── API Connection ──────────────────────────────────────────────
API_KEY=
API_BASE_URL=https://api.openai.com/v1

# ── Decision Model (gameplay decisions, combat plans, reflection) ──
DECISION_MODEL=gpt-5.4
DECISION_REASONING_EFFORT=medium         # none / low / medium / high

# ── Support Model (strategist, history compaction) ──────────────
SUPPORT_MODEL=gpt-5.4-mini
SUPPORT_REASONING_EFFORT=low             # none / low / medium / high

# ── Agent Behavior ──────────────────────────────────────────────
AGENT_MODE=propose                       # propose (human approves) or auto
AUTO_START_NEXT_GAME=false

# ── Knowledge & Memory Paths ────────────────────────────────────
KNOWLEDGE_DIR=data/knowledge
MEMORY_DIR=data/memory

# ── Experimentation ─────────────────────────────────────────────
PROMPT_PROFILE=default                   # switch prompt variants for A/B testing
EXPERIMENT_TAG=                          # human-readable label for this run config

# ── Advanced (rarely changed) ───────────────────────────────────
MAX_TOOL_ROUNDTRIPS=3
REQUEST_TIMEOUT_SECONDS=60
MAX_RETRIES=0
HISTORY_COMPACT_TOKEN_THRESHOLD=50000
HISTORY_KEEP_RECENT=10
CONSOLIDATION_EVERY_N_RUNS=5
DASHBOARD_MAX_INGRESS_AGE_SECONDS=90
```

**From 44 variables to 19.** Every variable name is self-documenting — no `LLM_` prefix soup. Reading the `.env` tells you exactly what each value controls.

> **Note:** 18 of the 19 variables are read by `AgentConfig`. The exception is `DASHBOARD_MAX_INGRESS_AGE_SECONDS`, which is read directly by `src/ui/dashboard.py` via `os.getenv()` — the dashboard is a separate process that doesn't use `AgentConfig`.

### Naming Conventions

The old `.env` used inconsistent prefixes (`LLM_`, `AGENT_`, `MEMORY_`, `REFLECTION_`, `REASONING_`, `CONSOLIDATION_`, `DASHBOARD_`). The new names follow these rules:

1. **No unnecessary prefixes.** `API_KEY` not `LLM_API_KEY`. There's only one API.
2. **Role in the name.** `DECISION_MODEL` and `SUPPORT_MODEL` tell you what the model does, not how it's implemented.
3. **Full words.** `REQUEST_TIMEOUT_SECONDS` not `LLM_TIMEOUT_SECONDS`. `KNOWLEDGE_DIR` not `AGENT_KNOWLEDGE_DIR`.
4. **Grouped by purpose.** Decision model vars start with `DECISION_`. Support model vars start with `SUPPORT_`.

### Variables Removed and Where They Go

| Old Variable | Disposition |
|---|---|
| `LLM_API_KEY` | Renamed → `API_KEY` |
| `LLM_BASE_URL` | Renamed → `API_BASE_URL` |
| `LLM_MODEL_REASONING` | Renamed → `DECISION_MODEL` |
| `LLM_MODEL_FAST` | Renamed → `SUPPORT_MODEL` |
| `LLM_REASONING_EFFORT` | Renamed → `DECISION_REASONING_EFFORT` |
| `LLM_FAST_REASONING_EFFORT` | Renamed → `SUPPORT_REASONING_EFFORT` |
| `AGENT_MODE` | Unchanged |
| `AUTO_START_NEXT_GAME` | Unchanged |
| `LLM_PROMPT_PROFILE` | Renamed → `PROMPT_PROFILE` |
| `LLM_MAX_TOOL_ROUNDTRIPS` | Renamed → `MAX_TOOL_ROUNDTRIPS` |
| `LLM_TIMEOUT_SECONDS` | Renamed → `REQUEST_TIMEOUT_SECONDS` |
| `LLM_MAX_RETRIES` | Renamed → `MAX_RETRIES` |
| `LLM_HISTORY_COMPACT_TOKEN_THRESHOLD` | Renamed → `HISTORY_COMPACT_TOKEN_THRESHOLD` |
| `LLM_HISTORY_KEEP_RECENT` | Renamed → `HISTORY_KEEP_RECENT` |
| `CONSOLIDATION_EVERY_N_RUNS` | Unchanged |
| `DASHBOARD_INGRESS_MAX_AGE_SECONDS` | Renamed → `DASHBOARD_MAX_INGRESS_AGE_SECONDS` |
| `AGENT_MEMORY_DIR` | Renamed → `MEMORY_DIR` |
| `AGENT_STRATEGY_DIR` | Replaced by `KNOWLEDGE_DIR` |
| `AGENT_EXPERT_GUIDES_DIR` | Replaced by `KNOWLEDGE_DIR` |
| `LLM_ENABLE_PLANNER` | **Deleted.** Always on. |
| `REASONING_BUDGET_ENABLED` | **Deleted.** Router removed. |
| `LLM_COMBAT_TURN_MODEL` | **Deleted.** Uses `DECISION_MODEL`. |
| `LLM_NON_COMBAT_TURN_MODEL` | **Deleted.** Uses `DECISION_MODEL`. |
| `LLM_COMBAT_PLAN_MODEL` | **Deleted.** Uses `DECISION_MODEL`. |
| `LLM_PLANNER_COMBAT_ONLY_TURN_ONE` | **Deleted.** Always turn-1 only. |
| `LLM_PLANNER_COMBAT_MAX_OUTPUT_TOKENS` | **Deleted.** Constant: `2048`. |
| `LLM_PLANNER_COMBAT_MAX_CARDS_PER_SECTION` | **Deleted.** Constant: `80`. |
| `MEMORY_RETRIEVAL_ENABLED` | **Deleted.** Always on. |
| `REFLECTION_ENABLED` | **Deleted.** Always on. |
| `LLM_TIMEOUT_SECONDS_REASONING` | **Deleted.** Uses `REQUEST_TIMEOUT_SECONDS`. |
| `LLM_TIMEOUT_SECONDS_FAST` | **Deleted.** Derived: `REQUEST_TIMEOUT_SECONDS / 3`. |
| `LLM_CONNECT_TIMEOUT_SECONDS` | **Deleted.** Constant: `5.0`. |
| `LLM_PROBE_TIMEOUT_SECONDS` | **Deleted.** Constant: `6.0`. |
| `LLM_PROPOSAL_FAILURE_STREAK_LIMIT` | **Deleted.** Constant: `3`. |
| `LLM_PROPOSAL_TIMEOUT_SECONDS` | **Deleted.** Derived from `REQUEST_TIMEOUT_SECONDS`. |
| `LLM_HISTORY_TOKENIZER_MODEL` | **Deleted.** Derived from `DECISION_MODEL`. |
| `LLM_HISTORY_COMPACTION_TRANSCRIPT_MAX_CHARS` | **Deleted.** Constant: `200_000`. |
| `MEMORY_MAX_HITS` | **Deleted.** Constant: `8`. |
| `MEMORY_CHAR_BUDGET` | **Deleted.** Constant: `6000`. |
| `MEMORY_MIN_PROCEDURAL_CONFIDENCE` | **Deleted.** Constant: `0.35`. |
| `REFLECTION_MAX_LESSONS_PER_RUN` | **Deleted.** Constant: `10`. |
| `CONSOLIDATION_CONFIDENCE_ARCHIVE_THRESHOLD` | **Deleted.** Constant: `0.2`. |

### New `AgentConfig` Class

```python
class AgentConfig(BaseModel):
    # API Connection
    api_base_url: str = "https://api.openai.com/v1"
    api_key: str = ""

    # Decision model — gameplay decisions, combat plans, reflection
    decision_model: str = "gpt-5.4"
    decision_reasoning_effort: str = "medium"   # none / low / medium / high

    # Support model — strategist, history compaction
    support_model: str = "gpt-5.4-mini"
    support_reasoning_effort: str = "low"       # none / low / medium / high

    # Agent behavior
    agent_mode: str = "propose"
    auto_start_next_game: bool = False

    # Knowledge & Memory paths
    knowledge_dir: str = "data/knowledge"
    memory_dir: str = "data/memory"

    # Experimentation
    prompt_profile: str = "default"
    experiment_tag: str = ""

    # Advanced
    max_tool_roundtrips: int = 3
    request_timeout_seconds: float = 60.0
    max_retries: int = 0
    history_compact_token_threshold: int = 50_000
    history_keep_recent: int = 10
    consolidation_every_n_runs: int = 5

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.decision_model)

    @property
    def support_timeout_seconds(self) -> float:
        return max(10.0, self.request_timeout_seconds / 3)

    @property
    def proposal_timeout_seconds(self) -> float:
        return max(120.0, self.request_timeout_seconds * float(self.max_tool_roundtrips + 1))

    @property
    def experiment_id(self) -> str:
        import hashlib
        key_fields = (
            self.decision_model, self.decision_reasoning_effort,
            self.support_model, self.support_reasoning_effort,
            self.prompt_profile,
        )
        return hashlib.sha256("|".join(key_fields).encode()).hexdigest()[:12]
```

**`get_agent_config()` env mapping — clean, no legacy support:**
```python
@lru_cache(maxsize=1)
def get_agent_config() -> AgentConfig:
    load_dotenv()
    return AgentConfig(
        api_base_url=os.getenv("API_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("API_KEY", ""),
        decision_model=os.getenv("DECISION_MODEL", "gpt-5.4"),
        decision_reasoning_effort=os.getenv("DECISION_REASONING_EFFORT", "medium").strip().lower(),
        support_model=os.getenv("SUPPORT_MODEL", "gpt-5.4-mini"),
        support_reasoning_effort=os.getenv("SUPPORT_REASONING_EFFORT", "low").strip().lower(),
        agent_mode=os.getenv("AGENT_MODE", "propose"),
        auto_start_next_game=os.getenv("AUTO_START_NEXT_GAME", "false").strip().lower() == "true",
        knowledge_dir=os.getenv("KNOWLEDGE_DIR", "data/knowledge").strip() or "data/knowledge",
        memory_dir=os.getenv("MEMORY_DIR", "data/memory").strip() or "data/memory",
        prompt_profile=os.getenv("PROMPT_PROFILE", "default").strip() or "default",
        experiment_tag=os.getenv("EXPERIMENT_TAG", "").strip(),
        max_tool_roundtrips=int(os.getenv("MAX_TOOL_ROUNDTRIPS", "3")),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
        max_retries=int(os.getenv("MAX_RETRIES", "0")),
        history_compact_token_threshold=int(os.getenv("HISTORY_COMPACT_TOKEN_THRESHOLD", "50000")),
        history_keep_recent=int(os.getenv("HISTORY_KEEP_RECENT", "10")),
        consolidation_every_n_runs=int(os.getenv("CONSOLIDATION_EVERY_N_RUNS", "5")),
    )
```

Module-level constants (not user-facing):
```python
CONNECT_TIMEOUT_SECONDS = 5.0
PROBE_TIMEOUT_SECONDS = 6.0
PROPOSAL_FAILURE_STREAK_LIMIT = 3
COMBAT_PLAN_MAX_OUTPUT_TOKENS = 2048
COMBAT_PLAN_MAX_CARDS_PER_SECTION = 80
MAX_MEMORY_HITS = 8
MEMORY_CHAR_BUDGET = 6000
MIN_PROCEDURAL_CONFIDENCE = 0.35
REFLECTION_MAX_LESSONS_PER_RUN = 10
CONSOLIDATION_ARCHIVE_THRESHOLD = 0.2
HISTORY_COMPACTION_MAX_CHARS = 200_000
```

### What Happens to `ReasoningBudgetRouter`

**Deleted entirely.** The file `src/agent/reasoning_budget.py` is removed.

Its four responsibilities are redistributed:

1. **Model selection** → gone. Always `config.decision_model` for decisions, `config.support_model` for support calls.
2. **Reasoning effort** → gone. Always `config.decision_reasoning_effort` for decisions, `config.support_reasoning_effort` for support calls.
3. **Retrieval mode** → gone. The strategist always runs on scene change; cached output is reused within the same scene. There is no "skip" / "tag_match" / "full" / "reuse" taxonomy.
4. **Tool filter** → moves to a simple static function in `src/agent/tool_registry.py`:

```python
def tool_filter_for_context(vm: dict) -> str | None:
    """Return a tool context filter string based on the current screen."""
    if vm.get("combat"):
        return "combat"
    screen_type = str((vm.get("screen") or {}).get("type", "NONE")).upper()
    return {
        "MAP": "map", "CARD_REWARD": "reward", "COMBAT_REWARD": "reward",
        "SHOP_SCREEN": "reward", "SHOP_ROOM": "reward", "BOSS_REWARD": "reward",
        "EVENT": "event", "REST": "reward",
    }.get(screen_type)
```

### How Models Are Used in Each Layer

| Call Site | Model | Effort | Timeout |
|---|---|---|---|
| Main decision (`_run_agent`) | `config.decision_model` | `config.decision_reasoning_effort` | `config.request_timeout_seconds` |
| Combat plan (`_ensure_combat_plan`) | `config.decision_model` | `config.decision_reasoning_effort` | `config.request_timeout_seconds` |
| Reflection (`reflect_on_run`) | `config.decision_model` | `"high"` (always — reflection needs deep analysis) | `config.request_timeout_seconds` |
| Strategist (`run_strategist`) | `config.support_model` | `config.support_reasoning_effort` | `config.support_timeout_seconds` |
| History compaction | `config.support_model` | `config.support_reasoning_effort` | `config.support_timeout_seconds` |

### Impact on the Graph Pipeline

The `_retrieve_memory` node currently calls the budget router, then does tag retrieval, then optionally calls the retrieval planning filter. In the new design:

- **`_retrieve_memory` is replaced by `run_strategist`** (Phase 3). The strategist handles knowledge selection + strategic planning in one call.
- The graph becomes: `START → run_strategist → resolve_combat_plan → assemble_prompt → run_agent → ...`
- `resolve_combat_plan` is a renamed, simplified version of the current `resolve_planning` that only handles the combat plan (non-combat planning moves to the strategist).
- Model and effort are read directly from config — no routing logic.

### Trace Field Changes

| Field | Change |
|---|---|
| `reasoning_profile_name` | **Removed** (no router, no profiles) |
| `retrieval_mode_used` | **Removed** (strategist always runs on scene change or reuses) |
| `llm_turn_model_key` | **Removed** (always the decision model; redundant) |
| `reasoning_effort_used` | Stays — records `config.decision_reasoning_effort` for the decision, or `config.support_reasoning_effort` for support calls |
| `llm_model_used` | Stays — records the actual model name string |
| `experiment_tag` | **New** — from `config.experiment_tag` |
| `experiment_id` | **New** — from `config.experiment_id` |
| `strategist_ran` | **New** — boolean, true if strategist LLM was called this turn (false = reused cache) |

### Implementation Phasing

The config redesign is **not a single PR**. It threads through the existing phases:

- **Phase 0:** Fix dead config using current names. No config rename yet — these fixes are against code that will be deleted in Phase 3, but they're cheap insurance if Phase 3 is delayed.
- **Phase 1:** Introduce `KNOWLEDGE_DIR` as the only new env var. `MemoryStore` starts loading from the new path. Old `AGENT_STRATEGY_DIR` / `AGENT_EXPERT_GUIDES_DIR` code is deleted (no backward compat).
- **Phase 3:** The big cut — full `.env` rewrite:
  - Rewrite `AgentConfig` and `get_agent_config()` with new field names
  - Delete `ReasoningBudgetRouter` and `src/agent/reasoning_budget.py`
  - Remove all feature-flag fields (`planner_enabled`, `memory_retrieval_enabled`, `reflection_enabled`, `reasoning_budget_enabled`, `combat_plan_only_turn_one`, etc.)
  - Move tool filter to `tool_registry.py`
  - Update graph pipeline to use strategist node
  - Write new `.env.example`
  - Update `src/main.py` and `src/ui/dashboard.py` to use new config field names
  - Update all `LLMClient` calls to use `config.decision_model` / `config.support_model` with their respective efforts
- **Phase 4:** `experiment_tag` and `experiment_id` are already on `AgentConfig` from Phase 3; Phase 4 wires them into replay/dashboard.

The config rename is bundled with Phase 3 because that's when the router is deleted and the strategist is introduced — doing it earlier would require maintaining the old router with new variable names, which is pointless churn.

---

## Phase 0: Bug Fixes and Quick Wins (Day 1)

These are small, surgical changes. Each is independently mergeable. No architectural changes.

### 0.1 — Fix dead config: `combat_plan_llm`

**Problem:** `planning.py` line 67 hardcodes `plan_key = "reasoning"` instead of reading `config.combat_plan_llm`.

**File:** `src/agent/planning.py`

**Change:**
```python
# Line 67 — BEFORE:
plan_key = "reasoning"

# AFTER:
plan_key = config.combat_plan_llm
```

No other changes needed. `config.combat_plan_llm` is already normalized to `"fast"` or `"reasoning"` by `_normalize_llm_slot()` in `config.py`. `LLMClient.generate_combat_plan` already accepts `model_key`.

**Test:** Run existing `tests/test_planning.py`. Verify trace field `combat_plan_model_used` reflects the config value.

### 0.2 — Fix dead config: `combat_plan_only_turn_one`

**Problem:** `planning.py` lines 86-89 always use `turn_n == 1 or ((turn_n - 1) % 5 == 0)` regardless of `config.combat_plan_only_turn_one`.

**File:** `src/agent/planning.py`

**Change:** Replace the `should_generate` block (lines 83-89):
```python
# BEFORE:
if turn_n is None:
    should_generate = not bool(session.combat_plan_guide)
else:
    should_generate = turn_n == 1 or ((turn_n - 1) % 5 == 0)
    if session.combat_plan_last_turn == turn_n:
        should_generate = False

# AFTER:
if turn_n is None:
    should_generate = not bool(session.combat_plan_guide)
else:
    if config.combat_plan_only_turn_one:
        should_generate = turn_n == 1
    else:
        should_generate = turn_n == 1 or ((turn_n - 1) % 5 == 0)
    if session.combat_plan_last_turn == turn_n:
        should_generate = False
```

**Test:** Unit test with `combat_plan_only_turn_one=True` — verify plan generates only on turn 1. With `False` — verify it regenerates on turn 6, 11, etc.

### 0.3 — Inject deck info on card reward screens

**Problem:** On `CARD_REWARD` screens, the agent cannot see its deck size or composition without calling a tool. From logs, the agent takes 65% of offered cards, resulting in 31-card decks.

**File:** `src/agent/prompt_builder.py`, inside `_screen_content_lines()` (around line 577)

**Change:** After the existing "YOU DO NOT NEED TO TAKE A CARD" lines and before the card list, add a deck snapshot:
```python
elif screen_type == "CARD_REWARD":
    cards = content.get("cards") or []

    # --- NEW: deck snapshot ---
    inv = vm.get("inventory") or {}
    deck = inv.get("deck") or []
    if isinstance(deck, list) and deck:
        deck_size = len(deck)
        type_counts: dict[str, int] = {}
        upgrades = 0
        for c in deck:
            if not isinstance(c, dict):
                continue
            ct = ((c.get("kb") or {}).get("type") or c.get("type") or "").upper()
            if ct:
                type_counts[ct] = type_counts.get(ct, 0) + 1
            if c.get("upgrades", 0):
                upgrades += 1
        type_str = ", ".join(f"{t}={n}" for t, n in sorted(type_counts.items()))
        lines.append(f"YOUR DECK: {deck_size} cards ({type_str}). {upgrades} upgraded.")
        if deck_size >= 25:
            lines.append(
                f"WARNING: Deck has {deck_size} cards. Larger decks lose consistency. "
                "Skip this reward unless the card is exceptional or fills a critical gap."
            )
    # --- END NEW ---

    lines.append(
        "YOU DO NOT NEED TO TAKE A CARD ON THIS SCREEN. ..."
    )
    # ... rest unchanged
```

**Details:**
- The `vm["inventory"]["deck"]` is always populated when in-game (see `state_processor.py` line 108-115).
- Each card dict has optional `kb.type` (from knowledge base) or raw `type` field.
- The warning threshold of 25 is based on the heuristic that 24-ish is the ideal deck size.
- This adds ~2 lines to the prompt on card reward screens only.

**Test:** Write a unit test for `_screen_content_lines` with a mock VM containing a 26-card deck on a CARD_REWARD screen. Assert the output includes `YOUR DECK: 26 cards` and the WARNING line.

### 0.4 — Exclude SOURCES.md from retrieval

**Problem:** `data/expert_guides/SOURCES.md` (a bibliography) is loaded as expert-weight gameplay advice by `MemoryStore` because it globs `*.md`.

**File:** `src/agent/memory/store.py`, inside `_load_markdown_dir()` (around line 108)

**Change:** Skip files that are clearly metadata, not gameplay content:
```python
for path in sorted(base_dir.glob("*.md")):
    # Skip metadata files (sources, changelogs, etc.)
    if path.stem.upper() in ("SOURCES", "CHANGELOG", "README"):
        continue
    # ... rest unchanged
```

**Alternative (simpler):** Rename `SOURCES.md` to `SOURCES.txt` so the glob doesn't match it. This requires no code change but is less robust.

**Test:** Verify `MemoryStore().knowledge_index_entries()` does not contain any entry with `id` starting with `expert:SOURCES`.

### 0.5 — Add deck_size and screen_type to AI decision trace

**Problem:** The `.ai.json` sidecar doesn't include deck size, making it hard to analyze deck growth over a run without cross-referencing raw state files.

**File:** `src/agent/schemas.py` — add fields to `AgentTrace`:
```python
class AgentTrace(BaseModel):
    # ... existing fields ...
    deck_size: Optional[int] = None           # NEW
    retrieved_lesson_ids: list[str] = Field(default_factory=list)  # NEW
```

**File:** `src/agent/tracing.py` — in `build_persisted_ai_log()`, include the new fields in the persisted output.

**File:** `src/agent/graph.py` — in `_retrieve_memory()`, after building the hit list, populate `trace.retrieved_lesson_ids`:
```python
# After hits are finalized:
trace.retrieved_lesson_ids = [self._hit_stable_id(h) for h in hits]
```

**File:** `src/agent/graph.py` — in the `propose()` method (or wherever the trace is first created from VM), set:
```python
trace.deck_size = len((vm.get("inventory") or {}).get("deck") or [])
```

**Also add to `PersistedAiLog`:** `deck_size` and `retrieved_lesson_ids` fields so they appear in `.ai.json`.

**Test:** Run a mock proposal and verify the `.ai.json` output contains `deck_size` and `retrieved_lesson_ids`.

---

## Phase 1: Knowledge Layer Redesign (Days 2-3)

This phase reorganizes the data folder, enriches the system prompt with game mechanics, and integrates the new strategy guide. Everything here is about **what the agent knows**, not how it reasons.

### 1.1 — Reorganize data/ folder structure

**Goal:** Replace the confusing `strategy/` + `expert_guides/` split with a single `knowledge/` directory organized by topic.

**New structure:**
```
data/
├── knowledge/                    ← all agent-retrievable markdown
│   ├── fundamentals/
│   │   ├── game_mechanics.md     ← NEW (written from scratch)
│   │   ├── deckbuilding.md       ← extracted from strategy guide + general_principles
│   │   ├── resource_economy.md   ← extracted from strategy guide (HP/gold/potion sections)
│   │   └── potion_tactics.md     ← NEW (extracted from strategy guide potion section)
│   ├── acts/
│   │   ├── act1_strategy.md      ← merged: act1_guide + expert_act1_checks
│   │   ├── act2_strategy.md      ← merged: act2_guide + expert_act2_elites_and_bosses
│   │   ├── act3_strategy.md      ← merged: act3_guide + expert_act3_and_endgame
│   │   └── act4_heart.md         ← extracted from strategy guide Act 4 section
│   ├── characters/
│   │   ├── ironclad.md           ← from ironclad_archetypes + removal heuristics from guide
│   │   ├── silent.md
│   │   ├── defect.md
│   │   └── watcher.md
│   ├── combat/
│   │   ├── elite_strategies.md   ← rewritten with REAL per-elite content (from guide + expert)
│   │   ├── boss_strategies.md    ← rewritten with per-boss content
│   │   └── relics_and_synergies.md ← from strategy guide relic/paradigm sections
│   ├── navigation/
│   │   ├── map_pathing.md        ← merged: map_pathing + strategy guide routing section
│   │   └── event_reference.md    ← existing, unchanged
│   └── meta/
│       └── sources.txt           ← renamed from SOURCES.md (not retrieved)
├── reference/                    ← renamed from processed/
│   ├── cards.json
│   ├── relics.json
│   ├── monsters.json
│   ├── bosses.json
│   ├── events.json
│   ├── potions.json
│   ├── powers.json               ← power/buff display text (+ tool `get_power_info`); no separate buff_descriptions file
│   └── orb_mechanics.json
├── memory/                       ← unchanged (runtime NDJSON)
├── Slay the Spire Mechanics Guide.md    ← human reference only; NOT loaded by MemoryStore
└── Slay the Spire Strategy Guide.md     ← human reference only; NOT loaded by MemoryStore
```

**Files to delete from active directories:** `acts.json`, `score_bonuses.json`, `global_statistics.json` (unused by any code).

**Each knowledge file must have YAML frontmatter:**
```yaml
---
tags: [act1, combat, elite, ironclad, general]
---
```

Tags should use the same vocabulary as `context_tags.py`: act names (`act1`, `act2`, `act3`), screen types (`combat`, `map`, `event`, `rest`, `reward`), character names (`ironclad`, `silent`, `defect`, `watcher`), and topic tags (`deck_building`, `pathing`, `boss`, `elite`, `potion`, `relic`, `general`, `reference`).

**Content guidelines for each merged file:**
- Lead with the most actionable, specific advice (not general philosophy).
- Keep each file under 2000 characters to fit within retrieval char budgets.
- If a topic needs more than 2000 characters, split into subtopic files.
- Never duplicate content across files. Each fact should live in exactly one place.
- Write in imperative style: "Kill the outside Sentry first" not "Players should consider killing...".

### 1.2 — Update MemoryStore to use new structure

**File:** `src/agent/config.py`

**Changes:**
- Replace `strategy_dir` and `expert_guides_dir` fields with a single `knowledge_dir` field:
```python
# REMOVE:
strategy_dir: str = "data/strategy"
expert_guides_dir: str = "data/expert_guides"

# ADD:
knowledge_dir: str = "data/knowledge"
```
- Add `resolved_knowledge_dir()` method.
- Update `get_agent_config()` to read `KNOWLEDGE_DIR` env var (default `"data/knowledge"`).
- Delete all references to `AGENT_STRATEGY_DIR` and `AGENT_EXPERT_GUIDES_DIR` (no backward compat).

**File:** `src/agent/memory/store.py`

**Changes:**
- Replace the two-directory load (`_load_markdown_dir` for strategy + expert) with a **recursive** glob of `knowledge_dir`:
```python
def reload(self) -> None:
    self._strategy_docs = self._load_knowledge_tree(self.knowledge_dir)
    self._procedural = self._load_ndjson(...)
    self._episodic = self._load_ndjson(...)

def _load_knowledge_tree(self, base_dir: Path) -> list[_StrategyDoc]:
    """Recursively load all *.md under base_dir."""
    out: list[_StrategyDoc] = []
    if not base_dir.is_dir():
        return out
    for path in sorted(base_dir.rglob("*.md")):
        if path.stem.upper() in ("SOURCES", "CHANGELOG", "README"):
            continue
        # ... same parse logic as before ...
        # All files get the same weight (remove strategy vs expert distinction)
```
- Remove the `STRATEGY_EFFECTIVE_CONFIDENCE` vs `EXPERT_GUIDE_EFFECTIVE_CONFIDENCE` distinction. Use a single weight (e.g., `1.5`) for all knowledge docs. The tag overlap scoring already differentiates relevance.

**File:** `src/agent/graph.py`

**Changes:**
- Update `SpireDecisionAgent.__init__` to pass `knowledge_dir` instead of `strategy_dir` + `expert_guides_dir`.

**File:** `.env.example`

**Changes:**
- Replace `AGENT_STRATEGY_DIR` and `AGENT_EXPERT_GUIDES_DIR` with `KNOWLEDGE_DIR=data/knowledge`.

**No backward compatibility.** Old `.env` files must be updated to use the new variable names.

### 1.3 — Write `game_mechanics.md` and add mechanics to system prompt

**The system prompt gets a compact mechanics section.** This is factual engine information the LLM needs every turn.

**File:** `src/agent/prompts/system_prompt.md`

**Add after line 1** (after "You are an AI assistant helping play Slay the Spire."):

```markdown
## Core game mechanics

- You draw 5 cards per turn (base). You have 3 energy per turn (base).
- Block wears off at the start of your turn. Damage to a blocked target reduces block first.
- After defeating an act boss, you heal to full HP and choose a boss relic.
- Potion slots: 2 at base (3 with Potion Belt). Use potions proactively — they are stored tempo, not emergency reserves.
- Vulnerable: target takes 50% more attack damage (3 turns default).
- Weak: target deals 25% less attack damage (3 turns default).
- Strength: +N damage per attack card played. Dexterity: +N block per block card played.
- Exhaust: card is removed from combat (not from your deck). It goes to the exhaust pile.
- Ethereal: if still in hand at end of turn, card is exhausted.
- Innate: card starts in your opening hand.
- Retain: card is not discarded at end of turn.
- Artifact: negates the next debuff applied to the holder.
- Intangible: all damage and HP loss is reduced to 1 per hit.
```

This adds ~15 lines (~250 tokens). Over 400 decisions/run, that's ~100k extra input tokens. Acceptable given the accuracy improvement.

**File:** `data/knowledge/fundamentals/game_mechanics.md`

A longer version (1500-2000 chars) with more detail: scaling mechanics, how multi-hit attacks interact with Vulnerable, how Thorns work, how orb slots work for Defect, stance mechanics for Watcher. This is retrieved when context tags match, not injected every turn.

### 1.4 — Write `potion_tactics.md` and add potion guidance to system prompt

**File:** `src/agent/prompts/system_prompt.md`

**Replace** the single potion line (current line 15) with a dedicated potion section:

```markdown
## Potion usage

- Potions are stored tempo. Use them proactively to save HP, not as emergency panic buttons.
- Use offensive potions (Fire Potion, Attack Potion) on turn 1 of elite fights to shorten the fight.
- Use defensive potions (Block Potion, Ghost in a Jar) when you'd otherwise take large damage.
- If all potion slots are full and you're about to get a potion reward, use one first.
- Don't enter a boss fight with full potion slots — use at least one before or during the fight.
- Scaling potions (Cultist Potion, Power Potion) are premium in long boss fights.
- A potion used to save 20 HP is worth more than holding it "just in case."
```

**File:** `data/knowledge/fundamentals/potion_tactics.md`

Extract the full potion economy section from the strategy guide (~800 chars) with tags: `[potion, combat, general, reference]`.

### 1.5 — Chunk and integrate the strategy guide

**Do NOT load the raw 233-line file as a single document.** Instead, extract its content into the topic-specific files created in 1.1.

**Mapping from strategy guide sections to knowledge files:**

| Guide Section | Target File |
|---|---|
| "Philosophy of Deckbuilding" | `knowledge/fundamentals/deckbuilding.md` |
| "Deck Engines" table | `knowledge/fundamentals/deckbuilding.md` |
| "Card Removal Heuristics" per-character table | `knowledge/characters/{ironclad,silent,defect,watcher}.md` |
| "Resource Management: HP" | `knowledge/fundamentals/resource_economy.md` |
| "Potion Economy" | `knowledge/fundamentals/potion_tactics.md` |
| "Merchant Shop Priorities" | `knowledge/fundamentals/resource_economy.md` |
| "Elite Snowball" | `knowledge/navigation/map_pathing.md` |
| "Flexible Routing" | `knowledge/navigation/map_pathing.md` |
| "Act 1-4 sections" | `knowledge/acts/act{1,2,3}_strategy.md` and `act4_heart.md` |
| "Relic Ecosystem" | `knowledge/combat/relics_and_synergies.md` |
| "Top-Down Framework" | `knowledge/fundamentals/deckbuilding.md` (the "why") |

**Keep long-form guides at repo paths like `data/Slay the Spire Strategy Guide.md` for human reference only** (outside `knowledge/` so `MemoryStore` never ingests them as retrieved docs).

---

## Phase 2: Map Analysis and Deck Trajectory (Days 4-6)

This phase adds **computed intelligence** — Python functions that analyze game state and inject quantitative data into prompts.

### 2.1 — Map path analysis function

**New file:** `src/agent/map_analysis.py`

**Function signature:**
```python
def analyze_map_paths(
    nodes: list[dict],
    current_node: dict | None,
    next_nodes: list[dict],
    boss_available: bool,
) -> list[dict]:
    """
    For each next_node, enumerate all reachable paths to the boss.
    Return a list of path analyses, one per next_node.

    Each analysis contains:
    - next_node: {x, y, symbol}
    - path_count: how many distinct paths from this node to the boss
    - encounter_summary: {monster: N, elite: N, rest: N, shop: N, event: N, treasure: N}
    - notable_sequences: list of strings like "elite→rest" or "elite→elite" (2-node patterns)
    - sample_path: the path with the most rest sites (as list of symbols)
    """
```

**Algorithm:**
1. Build adjacency from `nodes[].children[]`. Each node is keyed by `(x, y)`.
2. The boss is the implicit terminal node (y = max_y + 1, or `boss_available`).
3. For each `next_node`, run DFS to enumerate all paths to nodes at the maximum `y` level.
4. For each path, count node types by `symbol`: `M`=monster, `E`=elite, `R`=rest, `$`=shop, `?`=event, `T`=treasure.
5. Aggregate across paths: min/max/avg of each type.
6. Detect 2-node sequences of interest: elite→rest, elite→elite, rest→elite.

**Performance:** The map is tiny (50-70 nodes, max branching factor 3, max 15 rows). DFS with memoization runs in <1ms. No performance concern.

**Integration into prompt:** In `prompt_builder.py`, in `_map_planning_lines()` (line 406), after the existing `next_nodes` display, add a `## Path Analysis` section:

```python
def _map_planning_lines(vm: dict[str, Any]) -> list[str]:
    # ... existing code ...

    # NEW: computed path analysis
    map_state = vm.get("map") or {}
    analysis = analyze_map_paths(
        nodes=map_state.get("nodes") or [],
        current_node=map_state.get("current_node"),
        next_nodes=map_state.get("next_nodes") or [],
        boss_available=map_state.get("boss_available", False),
    )
    for a in analysis:
        sym = a["next_node"].get("symbol", "?")
        x, y = a["next_node"].get("x", "?"), a["next_node"].get("y", "?")
        s = a["encounter_summary"]
        parts = [f"{k}={v}" for k, v in s.items() if v > 0]
        lines.append(
            f"Path from ({x},{y})={sym}: {a['path_count']} routes to boss. "
            f"Typical: {', '.join(parts)}. "
            f"Sample: {' → '.join(a['sample_path'])}"
        )
```

This replaces the vague "Balance risk vs reward" line with real data like:
```
Path from (2,3)=E: 4 routes to boss. Typical: elite=2, rest=1, monster=3, shop=1.
  Sample: E → M → R → M → $ → M
Path from (1,3)=M: 3 routes to boss. Typical: elite=0, rest=2, monster=4, shop=0.
  Sample: M → ? → R → M → R → M
```

**Test:** Unit test with a small hand-crafted map (10 nodes, 3 rows). Verify path counts and encounter summaries are correct.

### 2.2 — Deck trajectory awareness

**Goal:** On card reward, shop, and event screens, the agent should see its full deck (not just size) and receive a deck assessment.

**New function in `src/agent/prompt_builder.py`:**
```python
def _deck_assessment_lines(vm: dict[str, Any]) -> list[str]:
    """Build a compact deck assessment for reward/shop/event screens."""
    inv = vm.get("inventory") or {}
    deck = inv.get("deck") or []
    if not isinstance(deck, list) or not deck:
        return []

    lines = []
    deck_size = len(deck)
    type_counts: dict[str, int] = {}
    cost_counts: dict[int, int] = {}
    upgrades = 0
    card_names: dict[str, int] = {}

    for c in deck:
        if not isinstance(c, dict):
            continue
        ct = ((c.get("kb") or {}).get("type") or c.get("type") or "").upper()
        if ct:
            type_counts[ct] = type_counts.get(ct, 0) + 1
        cost = c.get("cost")
        if isinstance(cost, int):
            cost_counts[cost] = cost_counts.get(cost, 0) + 1
        if c.get("upgrades", 0):
            upgrades += 1
        name = c.get("name", "?")
        card_names[name] = card_names.get(name, 0) + 1

    type_str = ", ".join(f"{t}={n}" for t, n in sorted(type_counts.items()))
    cost_str = ", ".join(f"{k}-cost={v}" for k, v in sorted(cost_counts.items()))
    lines.append(f"DECK ({deck_size} cards, {upgrades} upgraded): {type_str}")
    lines.append(f"Cost curve: {cost_str}")

    # Card list grouped by type
    by_type: dict[str, list[str]] = {}
    for c in deck:
        if not isinstance(c, dict):
            continue
        ct = ((c.get("kb") or {}).get("type") or c.get("type") or "").upper() or "OTHER"
        name = c.get("name", "?")
        if c.get("upgrades", 0):
            name += "+"
        by_type.setdefault(ct, []).append(name)
    for t in sorted(by_type):
        lines.append(f"  {t}: {', '.join(sorted(by_type[t]))}")

    if deck_size >= 25:
        lines.append(
            f"⚠ Deck is {deck_size} cards. Skip unless the card is exceptional."
        )

    return lines
```

**Integration:** Call `_deck_assessment_lines(vm)` and include as a subsection on `CARD_REWARD`, `SHOP_SCREEN`, `BOSS_REWARD`, and `EVENT` screens in `build_prompt_groups()`.

**Note on Phase 0.3 overlap:** Phase 0.3 adds a minimal deck size + warning to card rewards. Phase 2.2 replaces that with the full assessment. When implementing Phase 2.2, remove the Phase 0.3 code and replace it with this richer version.

### 2.3 — Add `inspect_full_deck` tool

**File:** `src/agent/tool_registry.py`

Add a new tool that returns the full card list (not just aggregates like `inspect_deck_summary`):
```python
"inspect_full_deck": {
    "description": "List every card in the master deck with name, type, cost, upgrades, and KB description.",
    "contexts": ["combat", "reward", "shop", "event", "map", "rest"],
    "executor": _run_full_deck_tool,
}
```

This gives the agent the option to inspect the full deck in any context, not just during card rewards. The deck assessment (2.2) is auto-injected on reward screens, but the tool lets the agent pull the info on demand during combat or other screens.

---

## Phase 3: Strategist Agent, Config Redesign, and Memory Improvements (Days 7-10)

This is the largest phase. It implements the **always-on architecture** described in the Configuration Redesign section above: deletes the budget router, renames config fields, removes all feature flags, replaces deterministic strategy with an LLM-powered strategist node, and fixes the reflection pipeline.

### 3.0 — Delete `ReasoningBudgetRouter` and simplify config

**This is done first within Phase 3, as everything else depends on it.**

**Delete file:** `src/agent/reasoning_budget.py`

**Move tool filter to `src/agent/tool_registry.py`:**
```python
def tool_filter_for_context(vm: dict) -> str | None:
    if vm.get("combat"):
        return "combat"
    screen_type = str((vm.get("screen") or {}).get("type", "NONE")).upper()
    return {
        "MAP": "map", "CARD_REWARD": "reward", "COMBAT_REWARD": "reward",
        "SHOP_SCREEN": "reward", "SHOP_ROOM": "reward", "BOSS_REWARD": "reward",
        "EVENT": "event", "REST": "reward",
    }.get(screen_type)
```

**Rewrite `src/agent/config.py`:**
- New `AgentConfig` class with simplified fields (see Configuration Redesign section above).
- Module-level constants for values that used to be env vars.
- Clean env var mapping in `get_agent_config()` — no legacy support.

**Update `src/agent/graph.py`:**
- Remove `from src.agent.reasoning_budget import ReasoningBudgetRouter`.
- Remove `self.budget_router = ReasoningBudgetRouter(self.config)` from `__init__`.
- In `_run_agent` (or wherever model_key is set), use `config.decision_model` directly instead of `profile.model_key`.
- Import and use `tool_filter_for_context(vm)` for tool filtering.

**Update `src/agent/schemas.py`:**
- Remove `reasoning_profile_name` and `retrieval_mode_used` from `AgentTrace` and `PersistedAiLog`.
- Add `experiment_tag`, `experiment_id`, `strategist_ran` to `AgentTrace`.

**Update `.env.example`:** Replace with the new 19-variable version (see Configuration Redesign section).

**Update tests:** Delete or rewrite `tests/test_reasoning_budget.py` (if it exists). Update any test that references removed config fields.

### 3.1 — Design the Strategist node

**What it replaces:**
- `session_state.py` → `update_strategy_memory()` (deterministic 4-slot dict)
- `planning.py` → `_non_combat_plan_block()` (hardcoded heuristic bullets)
- `graph.py` → `_retrieve_memory()` (tag retrieval + retrieval planning filter)
- `graph.py` → `_retrieval_planning_filter()` (knowledge selection LLM call)
- `reasoning_budget.py` → the entire file (retrieval mode logic)

**What it becomes:** A single LangGraph node `run_strategist` that replaces both `retrieve_memory` and `resolve_planning` for non-combat. The combat planner (`_ensure_combat_plan`) stays as a separate step that runs after the strategist.

**New file:** `src/agent/strategist.py`

**When it runs:** On **scene change only** (new `turn_key`), NOT every turn. During subsequent turns within the same scene, the previous strategist output is reused. This keeps cost low (~1 call per scene, not per turn).

**Detection:** Compare `state["trace"].turn_key` against `session.scene_key`. If they differ, run the strategist. Otherwise, reuse `session.strategy_notes` from the previous call.

**Input to the strategist LLM:**
```python
{
    "game_state": {  # compact VM
        "floor": 23,
        "act": 2,
        "screen": "CARD_REWARD",
        "class": "IRONCLAD",
        "hp": "45/80",
        "gold": 180,
        "boss": "The Champ",
        "deck_size": 22,
        "deck_types": {"ATTACK": 10, "SKILL": 8, "POWER": 3, "STATUS": 1},
        "relics": ["Burning Blood", "Vajra", "Fusion Hammer"],
        "potions": ["Fire Potion", "Block Potion"],
        "enemies": ["Chosen", "Cultist"]  # if in combat
    },
    "knowledge_index": [...],  # first 220 entries from knowledge_index_entries()
    "previous_strategy": {  # from session
        "deck_trajectory": "Building strength-scaling with Demon Form...",
        "pathing_intent": "Targeting 2 elites in Act 2...",
        "threat_assessment": "Low on block cards, vulnerable to multi-hit...",
        "resource_plan": "Save Fire Potion for next elite..."
    },
    "recent_actions": ["Took Inflame from card reward", "Rested at campfire"]
}
```

**Output schema (JSON):**
```json
{
    "selected_entry_ids": ["strategy:act2_strategy.md", "procedural:abc123"],
    "situation_note": "Floor 23, Act 2. Deck is 22 cards with solid strength scaling. ...",
    "turn_plan": "Evaluate this card reward against deck trajectory. Skip unless...",
    "strategy_update": {
        "deck_trajectory": "Strength-scaling Ironclad. Need: more block, draw. Avoid: more attacks.",
        "pathing_intent": "One more elite if HP allows, then shop + rest before Champ.",
        "threat_assessment": "Champ executes at 50% HP. Need burst damage + block for execute turn.",
        "resource_plan": "Use Fire Potion on next elite turn 1. Save Block Potion for Champ."
    }
}
```

**Prompt for the strategist:**

**New file:** `src/agent/prompts/strategist_prompt.md`

```markdown
You are the strategic planning layer for a Slay the Spire AI agent.

You receive the current game state summary, a knowledge index, and the previous strategic notes.

Your job:
1. Select 2-6 knowledge entry IDs most relevant to the current decision.
2. Write a brief situation assessment (2-3 sentences).
3. Write a turn plan for the current screen (1-3 sentences of specific advice).
4. Update the 4 strategy fields. Each should be 1-2 sentences of SPECIFIC, ACTIONABLE guidance.
   - deck_trajectory: What archetype are we building? What cards do we need/avoid?
   - pathing_intent: Why are we on this path? What's the plan for remaining floors?
   - threat_assessment: What's the biggest risk right now? What would kill this run?
   - resource_plan: How should we use HP, gold, potions? What are we saving for?

Rules:
- Be specific. "Need more block" is too vague. "Need 2+ block cards with 8+ base block for Champ's execute turn" is good.
- Revise previous strategy when the situation changes. Don't just repeat it.
- If the deck already has 24+ cards, default turn_plan to "Skip unless exceptional."
- Account for the boss of the current act in all strategy fields.

Respond with a single JSON object (no markdown fences).
```

**Model:** Use `config.support_model` with `config.support_reasoning_effort`. The strategist is a planning call, not a decision call. Timeout: `config.support_timeout_seconds`. It should complete in <2 seconds.

### 3.2 — Wire the Strategist into the LangGraph pipeline

**File:** `src/agent/graph.py`

**New graph structure:**
```python
def _build_graph(self):
    graph = StateGraph(GraphState)
    graph.add_node("run_strategist", self._run_strategist)         # REPLACES retrieve_memory
    graph.add_node("resolve_combat_plan", self._resolve_combat_plan)  # SIMPLIFIED from resolve_planning
    graph.add_node("assemble_prompt", self._assemble_prompt)
    graph.add_node("run_agent", self._run_agent)
    graph.add_node("run_tool", self._run_tool)
    graph.add_node("validate_decision", self._validate_decision)
    graph.add_edge(START, "run_strategist")
    graph.add_edge("run_strategist", "resolve_combat_plan")
    graph.add_edge("resolve_combat_plan", "assemble_prompt")
    graph.add_edge("assemble_prompt", "run_agent")
    # ... conditional edges for run_tool / validate_decision unchanged
```

Key changes vs current:
- `retrieve_memory` node → **deleted**, replaced by `run_strategist`
- `resolve_planning` node → **renamed** to `resolve_combat_plan`, simplified to only handle combat plans (non-combat planning moves to strategist)
- No `budget_router` field on `SpireDecisionAgent` — deleted
- Model key and tool filter set directly in `_run_agent`:
  ```python
  model_key = "decision"  # always the decision model
  tool_filter = tool_filter_for_context(state["vm"])
  ```

**New `GraphState` fields:**
```python
class GraphState(TypedDict, total=False):
    # ... existing fields ...
    strategist_output: dict[str, Any] | None   # NEW
    # REMOVED: turn_model_key, turn_reasoning_effort (no longer per-turn routing)
```

**The `_run_strategist` node:**
1. Set `state["tool_filter"] = tool_filter_for_context(vm)`.
2. Check if scene changed (`trace.turn_key != session.scene_key`). If same scene, reuse `session.strategy_notes` and `self._cached_memory_hits`. Set `trace.strategist_ran = False`. Return.
3. Build the strategist input (compact VM + knowledge index + previous strategy + recent actions).
4. Call the **support model** (`config.support_model` with `config.support_reasoning_effort`) with the strategist prompt. Timeout: `config.support_timeout_seconds`.
5. Parse the JSON output.
6. Map `selected_entry_ids` → `RetrievalHit` objects from the tag-retrieved pool (same logic as current `_retrieval_planning_filter`).
7. Update `session.strategy_notes` with the `strategy_update` fields.
8. Cache hits and planning block for same-scene reuse.
9. Set `trace.strategist_ran = True` and populate trace fields.

**The `_resolve_combat_plan` node (simplified):**
- Only runs `_ensure_combat_plan()` — the combat-specific LLM plan.
- Uses `config.decision_model` with `config.decision_reasoning_effort` for the combat plan call.
- The non-combat plan block (`_non_combat_plan_block`) is **deleted** — its role is now covered by the strategist's `turn_plan` field.

**Changes to `TurnConversation`:**
- Replace `strategy_memory: dict[str, str]` with `strategy_notes: dict[str, str]` (same shape, but now LLM-maintained).
- Remove `update_strategy_memory()` method entirely.
- Add `update_strategy_notes(notes: dict[str, str])` that merges new notes.
- Keep `strategy_memory_lines()` renamed to `strategy_notes_lines()` — same rendering logic.

**Combat plan:** Keep `_ensure_combat_plan()` as-is inside the strategist node. The strategist handles non-combat planning; the combat planner handles combat-specific plans. They compose.

### 3.3 — Fix reflection: validate lessons against outcomes and use proper effort

**Problem 1:** Lessons are never validated. `times_contradicted` is never updated.

**Problem 2:** The reflection LLM call should use the decision model with `reasoning_effort="high"` (not the configurable effort). Reflection happens once per run (not per turn) and needs deep analysis to extract quality lessons.

**File:** `src/agent/reflection/runner.py`

**Change:** Where the reflection LLM call is made, override reasoning effort:
```python
reflection_result = llm_client.call(
    model=config.decision_model,
    reasoning_effort="high",  # always high for reflection, regardless of config
    timeout=config.request_timeout_seconds,
    ...
)
```

This is the one place where effort is NOT read from config — it's always `"high"`. The "How Models Are Used in Each Layer" table in the Configuration Redesign section documents this.

**File:** `src/agent/reflection/analyzer.py`

**Add to `RunAnalyzer.analyze()`:** Collect all `retrieved_lesson_ids` from AI sidecars (new field from Phase 0.5) and attach to the `RunReport`:
```python
class RunReport(BaseModel):
    # ... existing fields ...
    retrieved_lesson_ids: list[str] = Field(default_factory=list)  # NEW: all lesson IDs used in this run
```

**File:** `src/agent/reflection/memory_storage.py`

**Add a new function `update_lesson_outcomes()`:**
```python
def update_lesson_outcomes(
    store: MemoryStore,
    retrieved_ids: list[str],
    victory: bool,
) -> None:
    """After a run, update times_validated or times_contradicted on retrieved lessons."""
    procedural_rows = list(store.procedural_entries)
    dirty = False
    retrieved_procedural = {
        rid.replace("procedural:", "")
        for rid in retrieved_ids
        if rid.startswith("procedural:")
    }
    for i, entry in enumerate(procedural_rows):
        if entry.id not in retrieved_procedural:
            continue
        e = entry.model_copy(deep=True)
        if victory:
            e.times_validated = int(e.times_validated) + 1
        else:
            e.times_contradicted = int(e.times_contradicted) + 1
        procedural_rows[i] = e
        dirty = True
    if dirty:
        store.rewrite_procedural(procedural_rows)
```

**Call this from `runner.py`** in `run_reflection_pipeline()`, after the reflection LLM call, using the `RunReport.retrieved_lesson_ids` and `RunReport.victory`.

### 3.4 — Fix consolidation: use outcome data

**File:** `src/agent/reflection/consolidator.py`

**Replace** the simple confidence-threshold archive with outcome-aware logic:
```python
def consolidate_procedural_memory(store: MemoryStore) -> ConsolidationSummary:
    summary = ConsolidationSummary()
    threshold = CONSOLIDATION_ARCHIVE_THRESHOLD  # module-level constant from config.py
    out: list[ProceduralEntry] = []
    for entry in store.procedural_entries:
        e = entry.model_copy(deep=True)
        status = (e.status or "").lower()
        if status == "archived":
            out.append(e)
            continue
        # Archive if: low confidence AND mostly contradicted
        validated = int(e.times_validated)
        contradicted = int(e.times_contradicted)
        total_uses = validated + contradicted
        if total_uses >= 3 and contradicted > validated:
            e.status = "archived"
            summary.archived_ids.append(e.id)
        elif float(e.confidence) < threshold and total_uses == 0:
            e.status = "archived"
            summary.archived_ids.append(e.id)
        out.append(e)
    store.rewrite_procedural(out)
    # ... log as before
```

This means:
- Lessons that were retrieved in 3+ runs and led to more losses than wins get archived.
- Lessons with low confidence AND zero usage also get archived (nobody's retrieving them).
- Lessons with good win/loss ratios survive regardless of initial confidence.

---

## Phase 4: Observability and Evaluation (Days 11-13)

### 4.1 — Wire experiment_id into traces and run metrics

**Already defined in Phase 3.0:** The `experiment_id` property on `AgentConfig` and the `experiment_tag`/`experiment_id`/`strategist_ran` fields on `AgentTrace` are created as part of Phase 3.0 (see Configuration Redesign section). Phase 4.1 only adds the wiring to populate them at runtime.

**File:** `src/agent/graph.py` — when creating a trace (in `propose()` or wherever `AgentTrace` is instantiated), set:
```python
trace.experiment_tag = self.config.experiment_tag
trace.experiment_id = self.config.experiment_id
```

**File:** `src/agent/tracing.py` — ensure `experiment_tag` and `experiment_id` appear in both `.ai.json` sidecars and `run_metrics.ndjson` lines, so replay and dashboard can group by experiment without parsing config.

### 4.2 — Extend replay.py with multi-run comparison

**File:** `src/eval/replay.py`

Add functions:
```python
def compare_experiments(base_dir: Path) -> dict:
    """Group runs by experiment_id, compute per-group metrics."""
    # For each experiment_id:
    #   - win_rate (with 95% Wilson confidence interval)
    #   - avg_floor_reached, avg_deck_size_at_end
    #   - avg_tokens_per_run, avg_latency_per_decision
    #   - skip_rate on card rewards
    #   - potion_use_rate (potion actions / combat turns)

def seed_paired_comparison(base_dir: Path, exp_a: str, exp_b: str) -> dict:
    """For runs sharing a seed across two experiments, compute paired differences."""
    # Match runs by seed
    # For each pair: diff in floor_reached, victory, deck_size
    # Return: paired mean diff, p-value (sign test or paired t-test)
```

### 4.3 — Add surrogate metrics to run_metrics.ndjson

**File:** `src/agent/tracing.py`

In `append_ai_decision_run_metric()`, add fields:
- `deck_size`: from VM
- `card_reward_action`: `"take"` | `"skip"` | `null` (only on CARD_REWARD screens)
- `potion_used`: `true` if the decision includes a `POTION USE` command
- `screen_type`: already in trace, ensure it's in the metric line

These enable computing skip_rate, potion_use_rate, and deck_growth_curve from `run_metrics.ndjson` alone, without parsing `.ai.json` files.

### 4.4 — Multi-run dashboard page

**File:** `apps/web/src/components/MultiRunMetricsPage.tsx` (new)

A page at `/metrics/compare` that:
1. Fetches all run summaries via `GET /api/runs` + `GET /api/runs/{name}/metrics?summary=1`
2. Groups by `experiment_id` (parsed from the first `.ai.json` in each run)
3. Displays per-group: win rate, avg floor, avg deck size, avg tokens, run count
4. Line chart: floor reached over time (run index on x-axis)
5. Bar chart: deck size at end per run

**File:** `src/ui/dashboard.py`

Add endpoint `GET /api/experiments` that runs the `compare_experiments()` logic from replay.py and returns the grouped metrics as JSON.

---

## Appendix: Files Modified Per Phase

| Phase | Files Modified | Files Created | Files Deleted |
|---|---|---|---|
| 0.1 | `src/agent/planning.py` | — | — |
| 0.2 | `src/agent/planning.py` | — | — |
| 0.3 | `src/agent/prompt_builder.py` | — | — |
| 0.4 | `src/agent/memory/store.py` | — | — |
| 0.5 | `src/agent/schemas.py`, `src/agent/tracing.py`, `src/agent/graph.py` | — | — |
| 1.1 | — | 15+ knowledge .md files | superseded dirs removed; git history is rollback |
| 1.2 | `src/agent/config.py`, `src/agent/memory/store.py`, `src/agent/graph.py`, `.env.example` | — | — |
| 1.3 | `src/agent/prompts/system_prompt.md` | `data/knowledge/fundamentals/game_mechanics.md` | — |
| 1.4 | `src/agent/prompts/system_prompt.md` | `data/knowledge/fundamentals/potion_tactics.md` | — |
| 1.5 | — | content merged into 1.1 files | — |
| 2.1 | `src/agent/prompt_builder.py` | `src/agent/map_analysis.py` | — |
| 2.2 | `src/agent/prompt_builder.py` | — | — |
| 2.3 | `src/agent/tool_registry.py` | — | — |
| 3.0 | `src/agent/config.py`, `src/agent/graph.py`, `src/agent/schemas.py`, `src/agent/tool_registry.py`, `.env.example` | — | **`src/agent/reasoning_budget.py`** |
| 3.1 | — | `src/agent/strategist.py`, `src/agent/prompts/strategist_prompt.md` | — |
| 3.2 | `src/agent/graph.py`, `src/agent/session_state.py`, `src/agent/planning.py` | — | — |
| 3.3 | `src/agent/reflection/analyzer.py`, `src/agent/reflection/memory_storage.py`, `src/agent/reflection/runner.py` | — | — |
| 3.4 | `src/agent/reflection/consolidator.py` | — | — |
| 4.1 | (done in 3.0) | — | — |
| 4.2 | `src/eval/replay.py` | — | — |
| 4.3 | `src/agent/tracing.py` | — | — |
| 4.4 | `src/ui/dashboard.py` | `apps/web/src/components/MultiRunMetricsPage.tsx` | — |

---

## Testing Strategy

Each phase should be tested before merging:

- **Phase 0:** Run existing test suite (`pytest tests/`). Add unit tests for the new deck-size logic and SOURCES exclusion.
- **Phase 1:** Manual verification: start the agent, check that `MemoryStore` loads all knowledge files, retrieval returns relevant hits. Run 1 game to floor 10 and inspect prompts.
- **Phase 2:** Unit tests for `map_analysis.py` with hand-crafted maps. Manual inspection of prompts on MAP screens.
- **Phase 3:** Unit tests for strategist JSON parsing. Integration test: mock VM → strategist call → verify strategy_notes updated. Run 1 full game and compare decision quality.
- **Phase 4:** Run `replay.py` on existing logs. Verify `experiment_id` appears in traces. Verify multi-run comparison output.

---

## Risk Register

| Risk | Mitigation |
|---|---|
| Knowledge reorg breaks retrieval quality | Roll back via git; A/B by pointing `KNOWLEDGE_DIR` at a branch or copy of the old tree. |
| Strategist adds latency (extra LLM call per scene) | Only runs on scene change, not every turn. Uses fast model. Budget ~1-2s per call. |
| Strategist hallucinates bad strategy | Include previous strategy in prompt for continuity. Monitor via `strategy_notes` in traces. |
| Map analysis function has bugs | Unit test with known maps. Path counts are verifiable by hand. |
| Reflection outcome tracking has selection bias | Lessons retrieved in both wins and losses are most informative. Track both counters. |
| Data folder reorg is a large diff | Do it in a single commit with a clear message; rely on git for rollback. |
