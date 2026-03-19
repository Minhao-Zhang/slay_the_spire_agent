# Slay the Spire LLM Bot

This project aims to create an LLM-powered bot capable of playing Slay the Spire.

> [!NOTE]
> This project depends on data from the [Slay the Spire Reference Spreadsheet](https://docs.google.com/spreadsheets/d/1ZsxNXebbELpcCi8N7FVOTNGdX_K9-BRC_LMgx4TORo4) and the [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) mod. Both of these resources were created by [ForgottenArbiter](https://github.com/ForgottenArbiter). This project is not affiliated with ForgottenArbiter. However, I would like to thank him for his hard work and dedication to the Slay the Spire community.

## Current Project Structure

```text
slay_the_spire_agent/
├── data/
│   ├── processed/          # Cleaned JSON facts (cards, relics, monsters)
│   └── raw/                # Excel source files
├── logs/                   # Raw JSON game states generated during play
├── scripts/
│   └── extract_reference_data.py # Parses raw Excel into processed JSON
├── src/
│   ├── main.py             # Orchestrator: Connects to CommMod, handles UI/Logging
│   ├── reference/          # Local knowledge base queries for game entities
│   │   ├── __init__.py
│   │   └── knowledge_base.py
│   └── ui/                 # Real-time FastAPI debugging dashboard
│       ├── dashboard.py
│       └── templates/
│           └── index.html
├── requirements.txt
└── README.md
```

## Setup & Configuration

This project manages Python dependencies using **uv**. 

1. **Install dependencies:**
   ```bash
   uv pip install -r requirements.txt
   ```

2. **Configure Slay the Spire Communication Mod:**
   You must point the Slay the Spire Communication Mod to your `main.py` entrypoint.
   For details on where to find the configuration file (`config.properties`) for your operating system, please refer to the [official CommunicationMod repository](https://github.com/ForgottenArbiter/CommunicationMod#running-external-processes).
   
   Ensure the `command=` property points to the absolute path of the Python executable inside your `uv` virtual environment, followed by the absolute path to `main.py`.
   
   Example (Windows):
   ```properties
   command=c:\\ABSOLUTE\\PATH\\to\\slay_the_spire_agent\\.venv\\Scripts\\python.exe c:\\ABSOLUTE\\PATH\\to\\slay_the_spire_agent\\src\\main.py
   ```

   Example (macOS):
   ```properties
   command=/ABSOLUTE/PATH/TO/slay_the_spire_agent/.venv/bin/python /ABSOLUTE/PATH/TO/slay_the_spire_agent/src/main.py
   ```

## Running the Debug Dashboard & Manual Control

To view the real-time agent tracker while playing the game, start the FastAPI dashboard in a separate terminal *before* launching Slay the Spire:

```bash
uv run python -m src.ui.dashboard
```

Once running, open your web browser to `http://localhost:8000/`. The dashboard will automatically update once you launch Slay the Spire and enter a combat encounter.

### Manual Override

The dashboard includes a "Manual Actions" input field. You can use this to manually drive the bot while Slay the Spire is running via CommunicationMod. 

To take an action, type a valid CommunicationMod command and press Enter (or click "Send action"). 

Examples of valid manual actions:
- `PLAY 1 0` (Plays the 1st card in your hand, targeting the 1st monster)
- `PLAY 3` (Plays the 3rd card in your hand, no target required)
- `END` (Ends your turn)
- `POTION Use 0 1` (Uses the potion in slot 0 on monster 1)
- `RETURN` (Click the Skip/Leave button)
- `PROCEED` (Click the Confirm button)

Whenever you submit a manual action, the `main.py` orchestrator will intercept the game's next 'wait' cycle and inject your command directly into the game.

## Replay Evaluation

You can compute baseline quality and runtime metrics from recorded logs:

```bash
uv run python -m src.eval.replay --logs-dir logs
```

Optional: evaluate one specific run folder under `logs`:

```bash
uv run python -m src.eval.replay --logs-dir logs --run 2026-03-17-11-24
```

### Capability flags

- `LLM_ENABLE_PLANNER=true` enables an optional planner node before action selection.
- `LLM_PROPOSAL_FAILURE_STREAK_LIMIT` controls how many consecutive proposal failures are tolerated before AI is disabled for the run.
