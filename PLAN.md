# Slay the Spire Agent Architecture Plan

## 1. Overview
The agent will use an exploratory, tool-calling architecture. It relies on a **Hybrid Context Strategy**: injecting immediate, tactical game state into the prompt every turn, while providing tools for the agent to look up static reference data (like card upgrades or boss mechanics) on demand.

The lifecycle of the agent should be managed as a state machine (e.g., using **LangGraph** or a custom OpenAI loop) to handle the cyclical nature of the ongoing game.

## 2. The Core Loop
Every action the agent takes follows this loop:
1. **Receive Raw State:** Game state JSON is received from CommunicationMod.
2. **Translate to Text:** Python parses the JSON and injects crucial details (HP, current hand, current enemies) into a concise text prompt.
3. **Agent Evaluation:** The LLM receives the prompt and decides if it has enough information to act.
4. **Tool Use (Optional):** If the LLM needs more info (e.g., "What does this new relic do?"), it makes parallel tool calls. The Python harness fetches this static data from `knowledge_base.py` and returns it.
5. **Decide Action:** The LLM uses Chain of Thought reasoning to output a final game command (e.g., `PLAY 1 0`).
6. **Execution:** The harness sends the command to the game.

## 3. Context Management Strategy

### A. Injected Context (Provided Every Turn)
*Crucial for immediate tactical awareness. Must be injected directly into the system prompt text.*

- **Player State:** Current HP, Max HP, Energy, Block, active Powers, Gold.
- **Current Hand:** List of playable cards, their energy costs, and their base text.
- **Current Enemies:** Names, current HP, Block, and their *current intentions* (e.g., attacking for 15).
- **Enemy AI Rules:** The specific behavioral rules/probabilities for *only* the enemies currently on screen (pulled automatically from `monsters.json`).
- **Valid Actions:** A list of the legally permitted CommunicationMod commands for this specific phase (e.g., Play, End, Potion).

### B. Tool Calls (Available On-Demand)
*Used for exploration, long-term planning, and deep mechanics analysis to save context window tokens.*

- `get_card_details(card_name)`: Returns upgrade information and edge-case mechanics for specific cards (useful during draft screens).
- `get_relic_details(relic_name)`: Returns specific mechanics for relics (useful in shops or chests).
- `get_boss_info(act_number)`: Returns the AI behavior of the upcoming Act boss (crucial for long-term deckbuilding strategy).
- `view_draw_pile()` / `view_discard_pile()`: Returns the list of cards remaining in the deck to calculate draw probabilities before playing actions.

## 4. Required Next Steps
1. **Enhance Prompts:** Build the Python translator function in `src/llm/` to parse the `0002.json` style logs into the condensed text format.
2. **Integrate Tools:** Update the `ChatSession` in `src/llm/client.py` to support the OpenAI `tools` parameter and handle tool execution loops.
3. **Test Loop:** Run the agent in a controlled combat encounter to verify it can reliably ask for a card's info and then play it successfully.
