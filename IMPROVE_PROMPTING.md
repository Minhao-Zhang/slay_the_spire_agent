# Prompting Improvement Plan

Ongoing notes for improving the Slay the Spire agent's prompting strategy.

---

## 1. Current User Prompt Structure

The user prompt is built in `src/agent/prompt_builder.py` by `build_user_prompt(vm, state_id, recent_actions)`.

### Sections (in order)

| Section | Purpose |
|---------|---------|
| **STATE ID** | Identifies the exact game state |
| **PLAYER STATE** | class, floor, hp, gold, energy, turn, block |
| **PLAYER POWERS** | Active powers (e.g. No Draw) |
| **RELICS** | Name + short description |
| **POTIONS** | Indexed list; effect often "No data available" |
| **MONSTERS** | hp, intent, powers, known_moves (first 3 move names only) |
| **HAND** | Cards with cost, targeted, upgrades, desc |
| **CURRENT SCREEN** | type, title, content_keys |
| **LEGAL ACTIONS** | Numbered label + command |
| **RECENT ACTIONS THIS TURN** | Last 5 actions this turn |
| **TOOLING NOTES** | When to use pile inspection tools |

### Example (combat turn)

```markdown
## STATE ID
d6b7e664ee791906

## PLAYER STATE
- class=IRONCLAD
- floor=12
- hp=87/87
- gold=32
- energy=4
- turn=1
- block=0

## MONSTERS
- 1. Fungi Beast | hp=27/27 | intent=Attack: 7 | powers=Spore Cloud(2), Strength(1) | known_moves=Grow, Bite

## HAND
- 1. Strike | cost=1 | targeted | desc=Deal 6 damage.
- 4. Uppercut | cost=2 | targeted | desc=Deal 13 damage. Apply 1 Weak. Apply 1 Vulnerable.

## LEGAL ACTIONS
- 1. label=END TURN | command=END
- 6. label=Uppercut → Fungi Beast | command=PLAY 4 0
...
```

### System prompt

`src/agent/prompts/system_prompt.md` — gameplay guidance, elite reminders, rules, and `<final_decision>` format.

---

## 2. Chat History Scope

**Design principle:** Keep history across scenes. When history exceeds a configurable threshold (e.g. message count or token estimate), compact older exchanges using the fast model instead of resetting.

### Compact-on-threshold (target design)

- **No per-scene reset** — History persists across combat, map, rewards, events, etc.
- **Threshold** — When `len(messages)` or estimated tokens exceeds a limit (e.g. 20 exchanges, or ~8k tokens), trigger compaction.
- **Compaction** — Use the fast model to summarize older user/assistant pairs into a short `## COMPACTED HISTORY` block. Replace those messages with a single synthetic user message containing the summary. Keep the most recent N exchanges (e.g. last 4–6) intact.
- **Config** — Add `LLM_HISTORY_COMPACT_THRESHOLD` (message count) and optionally `LLM_HISTORY_KEEP_RECENT` (messages to preserve before compaction). Defaults TBD (e.g. 20 / 6).

### Current implementation (to be replaced)

Currently: history resets per **turn key** (scene type + floor). `build_turn_key` in `src/agent/tracing.py` defines scope. `summarize_for_next_scene` runs on transition and prepends a previous-scene summary to the first prompt in the new scene. This will be replaced by the compact-on-threshold approach.

### Tradeoff

- **Benefit:** Full run context (deck evolution, path choices, prior fights) without unbounded token growth.
- **Risk:** Compaction may drop nuance; threshold tuning needed. Fast-model latency on compaction calls.

---

## 3. Potential Improvements (to explore)

### High priority

- [ ] **Compact-on-threshold history** — Replace per-scene reset with compact-on-threshold: keep history across scenes; when messages exceed `LLM_HISTORY_COMPACT_THRESHOLD`, use fast model to summarize older exchanges into `## COMPACTED HISTORY`, keep last N exchanges. See §2.
- [ ] **Map planning context (MAP screen)** — When `screen.type` is MAP, add a dedicated **MAP PLANNING** section to the user prompt. Include:
  - **Next nodes** — For each reachable node: symbol (M=monster, ?=event, $=shop, R=rest) and position, so the model can choose paths strategically.
  - **Boss** — Act boss name and brief KB (from `vm["map"]["boss_name"]`, `vm["map"]["boss_kb"]`) so the model knows what to prepare for.
  - **Boss available** — Whether the boss node is reachable this choice.
  - **Current position** — Floor and current node coordinates for context.
  - Data source: `vm["map"]` has `next_nodes`, `current_node`, `boss_available`, `boss_name`, `boss_kb`. Build this section only when `screen.type == "MAP"`.
- [ ] **Remove STATE ID** — The state ID is a random hash used for internal tracking; it provides no useful signal to the LLM. Remove it from the user prompt.
- [ ] **Monster notes** — Add `notes` from `data/processed/monsters.json` to the MONSTERS section. Example: "Splits if HP is 50% or below", "*Slimed goes into the Discard Pile". Currently in KB but not included in the prompt.
- [ ] **Monster AI behavior** — Add `ai` from `data/processed/monsters.json` to the MONSTERS section. Describes move probabilities, sequencing rules, and patterns (e.g. "50% chance of each move on turn 1, then alternates between the two."). Currently in KB but not included in the prompt. Very important for predicting enemy behavior and planning ahead.

### Other

- [ ] **Log token counts** — Add `input_tokens` and `output_tokens` to the persisted AI log (`.ai.json`). `trace.token_usage` is already populated by the LLM client; extend `PersistedAiLog` and `build_persisted_ai_log()` in `src/agent/tracing.py` to include these fields. Enables cost tracking and debugging.
- [ ] **Section order** — Put LEGAL ACTIONS and MONSTERS higher for faster parsing.
- [ ] **Potion effects** — Replace "No data available" with real effect text from `data/processed/`.
- [ ] **Intent normalization** — Standardize "Intent: BUFF" vs "Attack: 7" for clarity.
- [ ] **Context additions** — Draw pile size, discard size, next-room type when available.
- [ ] **Other ideas** — TBD as discussion continues.

---

## 4. Key Files

| File | Role |
|------|------|
| `src/agent/prompt_builder.py` | Builds user prompt from VM |
| `src/agent/prompts/system_prompt.md` | System instructions |
| `src/agent/tracing.py` | `build_turn_key()` — history scope |
| `src/agent/session_state.py` | `TurnConversation` — messages, reset logic, previous_scene_summary |
| `src/agent/llm_client.py` | `summarize_for_next_scene()` — fast-model summarization |
| `data/processed/monsters.json` | Monster KB: moves, notes, ai (enriched via `get_monster_info`) |
| `data/processed/bosses.json` | Boss KB for map planning (act boss prep) |
