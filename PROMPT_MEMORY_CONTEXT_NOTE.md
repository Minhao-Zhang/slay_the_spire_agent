# Prompt size, memory retrieval, and context — engineering note

This document consolidates analysis and recommendations from an internal review (April 2026). It is intended for evaluation by another engineer; it is **not** a product spec and does not replace [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md).

---

## 1. What dominates tactical prompt size (empirical)

A sample high–token decision was taken from:

`logs/games/2026-04-13-07-49-19_THE_SILENT_A1_44319930/0032.ai.json` (MAP, floor 3).

Approximate breakdown of **`user_message`** (tactical text only):

| Section | ~Chars | ~Share of `user_message` |
|--------|--------|---------------------------|
| **Reference & past lessons / RETRIEVED KNOWLEDGE** (full bodies of selected markdown files) | ~11,200 | ~69% |
| **Current scene** (map planning + path analysis + map scene layout/connections) | ~2,800 | ~17% |
| Other (strategist prefix, history, loadout, legal actions, tooling notes) | remainder | ~14% |

**API `input_tokens` vs sidecar text:** The same event logged **`input_tokens` ≈ 68k** with **`cached_input_tokens` ≈ 63k** and **`uncached_input_tokens` ≈ 5.3k**. The sidecar stores one **`user_message`** per decision (~16k chars); the gap is **system prompt, full chat history, tool definitions, and provider accounting** (including reasoning models).

**Tools:** In that run, **`tool_names` were empty** on sampled sidecars — deck tool usage was **not** the driver of those particular large prompts.

---

## 2. How knowledge gets into the prompt (mechanics)

### 2.1 Candidate pool (deterministic, not “regex on files”)

- **`build_context_tags(vm)`** ([`src/agent/memory/context_tags.py`](src/agent/memory/context_tags.py)) derives tags from structured VM fields (floor/act, screen type, class, enemy names → slugs, event KB, boss name, etc.).
- **`MemoryStore.retrieve()`** ([`src/agent/memory/store.py`](src/agent/memory/store.py)) scores **procedural**, **strategy** (L1 markdown), and **episodic** entries by **tag-set overlap** (and procedural confidence). It fills up to **`max_results`** and **`char_budget`**.
- **`tag_utils.slugify_token`** uses a small regex only to **normalize** strings into tag tokens; it does **not** match “which file to retrieve.”

### 2.2 Final selection (LLM when strategist runs)

- On **scene change** (see §4), **`run_strategist_llm`** ([`src/agent/strategist.py`](src/agent/strategist.py)) receives **`knowledge_index[:220]`** (snippets) and **`pool_hits`**, and returns **`selected_entry_ids`**.
- **`map_selected_ids_to_hits`** maps those IDs to full **`RetrievalHit`** objects (full **`body`**). Invalid / empty selection falls back to top **`pool_hits[:max_hits]`**.
- If AI is disabled, the graph uses **`pool_hits[:MAX_MEMORY_HITS]`** with **no** strategist LLM.

### 2.3 Constants and pool sizing

From [`src/agent/config.py`](src/agent/config.py):

- **`MAX_MEMORY_HITS = 8`**
- **`MEMORY_CHAR_BUDGET = 6000`**

From [`src/agent/graph.py`](src/agent/graph.py) **`_run_strategist`**:

- **`pool_max = max(MAX_MEMORY_HITS * 3, 24)` → 24**
- **`pool_budget = max(MEMORY_CHAR_BUDGET, 12_000)` → effectively 12_000** for the **retrieval pool**

So the **written 6000** budget is **not** the effective ceiling for the pool passed to **`retrieve()`**.

### 2.4 Prompt emission

- **`_format_memory_hits`** in [`src/agent/prompt_builder.py`](src/agent/prompt_builder.py) emits **full `h.body`** per hit with **no** per-hit truncation at render time.

### 2.5 Strategist prompt vs code

[`src/agent/prompts/strategist_prompt.md`](src/agent/prompts/strategist_prompt.md) asks for **2–6** knowledge IDs; **`MAX_MEMORY_HITS`** and slicing still allow **up to 8**.

### 2.6 Duplicate planning text

Non-combat prompts can include both:

- **`build_planning_block_from_strategist`** → `## Strategic context` (situation + turn plan), and  
- **`build_non_combat_plan_block`** → `## TURN PLAN` with the same turn plan again.

That duplicates tokens without adding new information.

---

## 3. Alignment with IMPROVEMENT_PLAN.md

| Plan intent (see IMPROVEMENT_PLAN.md) | Current behavior |
|--------------------------------------|------------------|
| Knowledge files ~**&lt;2000 chars**, split if larger (Phase 1.1) | Tree matches taxonomy; **`combat/boss_strategies.md`** and **`combat/elite_strategies.md`** are the main size risks; one hit = **whole file body**. |
| **`MEMORY_CHAR_BUDGET = 6000`** | Pool uses **`max(..., 12_000)`** in **`graph.py`**, inflating the pool vs the documented constant. |
| Strategist selects **2–6** entries (Phase 3) | Code allows **8**; no hard cap at 6. |
| Non-combat planning via strategist (Phase 3.2 direction) | **`build_non_combat_plan_block`** still adds a second **TURN PLAN** block. |
| Map path analysis (Phase 2) | **Implemented** (`map_analysis` + `_map_planning_lines`); plan is **not** “delete map context,” it is **add structured analysis**. |

---

## 4. Is “context” refetched every new game state?

**Depends what you call context.**

| Kind | Every new `state_id` / `propose()`? |
|------|-------------------------------------|
| **Tag retrieval + strategist + full `memory_hits` text** | **No.** Gated on **`turn_key`** (scene): if **`session.scene_key == trace.turn_key`**, cached hits and planning blocks are reused; **`strategist_ran = false`**. Refetch when **`turn_key`** changes or on first scene (`scene_key` was `None`). |
| **`build_user_prompt` from current `vm`** (hand, legal actions, map lines, etc.) | **Yes.** Rebuilt every graph invoke. |
| **`session.messages` (chat history)** | **Yes.** User + assistant appended after each proposal; compaction may run when over threshold. |

**Graph order:** `START → run_strategist → resolve_combat_plan → assemble_prompt → run_agent → …`  
`session.scene_key` is updated in **`_assemble_prompt`** via **`set_scene(turn_key)`**, so **`_run_strategist`** compares the **previous** proposal’s stored scene to the **current** trace’s **`turn_key`**.

---

## 5. Run-level action journal (implemented elsewhere)

A **cross-scene `run_journal`** (bounded deque), **`describe_execution`**, and **`send_game_command`** in **`main.py`** were added so tactical history is not cleared on every **`turn_key`** change like **`action_history`**. See design discussion in `new_actions_history_design.md` (if present). This note does not re-spec that work.

---

## 6. Recommendations (for evaluation — no implementation commitment)

### 6.1 Quick wins

- Remove or replace **`max(MEMORY_CHAR_BUDGET, 12_000)`** with an explicit, documented constant (or use **6000** as written in the plan).
- Enforce **2–6** selected hits in code to match **`strategist_prompt.md`** (or raise **`MAX_MEMORY_HITS`** to 6).
- Add a **per-hit or total character cap** in **`_format_memory_hits`** (or before) so tactical prompts cannot balloon from eight full files.
- **Deduplicate** `## Strategic context` vs `## TURN PLAN` for non-combat.

### 6.2 Structural (plan-aligned)

- **Chunk knowledge** so retrieval granularity is smaller than one file (IDs → chunks), especially for boss/elite compendia.
- **Summarization / compression** of selected knowledge for the **tactical** model: natural place is the **strategist** (same support call) with **grounding** and **strict length limits**; optional separate summarize step if you need a global cap.
- Revisit **retrieve() merge order** (`procedural + strategy + episodic`) if you need episodic to appear under tight budgets.

### 6.3 Summarization vs raw strategy bodies

Using **summaries or extractive snippets** instead of full markdown in the tactical prompt is **reasonable** and matches the direction of IMPROVEMENT_PLAN (small units, bounded budget). Risks: **lost edge-case detail** and **hallucination** if purely abstractive — mitigate with **grounding**, **per-doc caps**, and optionally **extract-then-compress**.

---

## 7. How to reproduce log analysis locally

```powershell
# List a run’s sidecars
cmd /c "dir /s /b logs\games\<RUN_FOLDER>\*.ai.json"

# Rank by input_tokens (Python one-liner or small script)
uv run python -c "import json, pathlib; p=pathlib.Path(r'logs/games/<RUN_FOLDER>');
rows=[]
for f in p.glob('*.ai.json'):
 d=json.loads(f.read_text(encoding='utf-8'));
 rows.append((d.get('input_tokens')or 0,len(d.get('user_message')or''),f.name))
rows.sort(key=lambda x:-x[0]);
print(rows[:15])"
```

Workspace search tools may **ignore** `logs/` (e.g. cursorignore); use shell or IDE on disk paths if needed.

---

## 8. References (code)

| Topic | Location |
|-------|----------|
| Strategist + cache | [`src/agent/graph.py`](src/agent/graph.py) `_run_strategist`, `_assemble_prompt` |
| Strategist LLM + ID mapping | [`src/agent/strategist.py`](src/agent/strategist.py) |
| Retrieval + hits | [`src/agent/memory/store.py`](src/agent/memory/store.py) |
| Context tags | [`src/agent/memory/context_tags.py`](src/agent/memory/context_tags.py) |
| Prompt sections | [`src/agent/prompt_builder.py`](src/agent/prompt_builder.py) |
| Constants | [`src/agent/config.py`](src/agent/config.py) |
| Roadmap | [`IMPROVEMENT_PLAN.md`](IMPROVEMENT_PLAN.md) |

---

*End of note.*
