# Spire Agent

**Spire Agent** is an **autonomous LLM agent** for *Slay the Spire* (via [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod)) with **human-in-the-loop** control: you can **observe** full traces and context, **shape decisions** (approve, edit, reject, retry), or **hand off** to fully automatic play. The stack is built to study **long-horizon** play—runs span many floors and acts, so planning, retrieval, and post-run memory matter as much as the next button press.

## What you get

- **Autonomous loop** — LangGraph agent with tools, policy-validated commands, and modes from full autonomy (`auto`) to gated proposals (`propose`) to human-only (`manual`).
- **Monitor (`/`)** — Live game state plus **observability**: prompts, strategist layer, combat framing, reasoning when available, proposals, and a session log—so you can audit *why* a long-run choice was made.
- **Human decisions** — Same surface for **intervention**: approve or change a line, retry after failure, switch mode without restarting the game.
- **Planning horizon** — Curated `data/knowledge/`, factual `data/reference/`, **map path analysis**, a **strategist** (support model) for scene-level notes, **combat planning**, **retrieval** + `MEMORY_DIR`, and **reflection** after runs so lessons accumulate across the spire.
- **`/metrics` · `/metrics/map`** — Per-run analytics and map replay to review **multi-act** trajectories, not just single combats.

## Screenshots

| **Monitor** (`/`) — combat, legal actions, model context, trace, session log | **Run metrics** (`/metrics`) — charts and per-run analytics |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------- |
| ![Monitor dashboard](docs/images/dashboard_screenshot.png)                   | ![Run metrics](docs/images/metric_screenshot.png)             |

## Requirements

- **Python 3.11+** ([`pyproject.toml`](pyproject.toml))
- **[uv](https://docs.astral.sh/uv/)**
- **Node.js** (repo root npm workspaces)
- **Slay the Spire** + CommunicationMod (configure in [Run the stack](#run-the-stack))

## Install

```bash
uv sync
npm install
```

Copy [`.env.example`](.env.example) to `.env`. Set an OpenAI-compatible `API_BASE_URL`; **Responses API** is the best-tested path. Leave `API_KEY` empty for manual-only mode. Other variables are documented in `.env.example`.

## Run the stack

**1. API server** — Repo root: `run_api.bat` or `./run_api.sh` → `http://127.0.0.1:8000` (see console echo; `localhost` also works).

**2. Web UI (dev)** — Repo root: `npm run dev:web` → `http://127.0.0.1:5173` (**/** Monitor, **/metrics**, **/metrics/map**).

**3. CommunicationMod** — Set `command` to an absolute path to this repo:

- **Windows:** `command=ABSOLUTE_PATH\run_agent.bat`
- **macOS / Linux:** `command=ABSOLUTE_PATH/run_agent.sh` and `chmod +x run_agent.sh`

[`run_agent.bat`](run_agent.bat) / [`run_agent.sh`](run_agent.sh) use `.venv` and `python -m src.main` from the repo (after `uv sync`).

**4. Game** — Start *Slay the Spire* with CommunicationMod and run a mod session.

## How it works

The **bridge** ([`src/main.py`](src/main.py)) runs **`SpireDecisionAgent`**: a LangGraph loop that, each step, fuses the live view with **retrieval** (`data/knowledge`, `data/reference`), **strategist** output and **combat planning** for longer-horizon context, **map analysis** when you are on the map, and **memory** from past scenes and runs. The **decision** model chooses actions (with tools); outputs are **validated** before execution. The **API server** carries **HITL** state—approvals, edits, mode—so humans stay in the loop for **observability and decisions** while the agent can otherwise run on its own. The bridge sends the final command to the game. The **`logs/`** tree feeds **Metrics** and **map** for reviewing whole runs.

```mermaid
flowchart TB
  Game[("Slay the Spire + CommunicationMod")] <--> Bridge["Game bridge\n(LangGraph + propose)"]
  Bridge <--> Api["API server\n(HITL · traces)"]
  Api <--> UI["Browser UI\nobserve · decide · metrics"]

  subgraph Know["Knowledge & memory"]
    KBM["Strategy markdown\n(data/knowledge)"]
    RefJ["Reference JSON\n(data/reference)"]
    Mem["Lesson store\n(MEMORY_DIR)"]
    Post["Reflector · consolidator\n(post-run)"]
  end

  subgraph Runtime["On bridge"]
    Strat["Strategist\n(SUPPORT_MODEL)"]
    Ctx["Context\n(view model · retrieval · combat plan ·\nmap analysis · strategist · memory)"]
    Loop["LangGraph · DECISION_MODEL · tools"]
    Pol["Policy → validated command"]
    Strat --> Ctx --> Loop --> Pol
  end

  KBM --> Ctx
  RefJ --> Ctx
  Mem --> Ctx
  Bridge --> Runtime
  Pol --> Bridge
  Loop -.->|traces| Api
  UI -.->|approve · mode| Api

  Bridge --> Logs[("Run logs")]
  Logs --> Replay["Replay · metrics · map"]
  Logs -.-> Post
  Post --> Mem
```



More detail: [`ARCHITECTURE.md`](ARCHITECTURE.md), [data-flow-diagram.md](data-flow-diagram.md), [user-sequence-diagram.md](user-sequence-diagram.md).

## Limitations

### Watcher stance not in JSON (stock CommunicationMod)

Unmodified [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) does **not** put the Watcher’s stance on `combat_state.player` in JSON (HP, block, energy, powers, orbs only). The agent cannot rely on stance from the wire unless the mod is extended (e.g. `stance_id`).

Source: [CommunicationMod `GameStateConverter.java` — `convertPlayerToJson`](https://github.com/ForgottenArbiter/CommunicationMod/blob/master/src/main/java/communicationmod/GameStateConverter.java#L715-L741)
