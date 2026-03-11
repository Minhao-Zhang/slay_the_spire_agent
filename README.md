# Slay the Spire LLM Bot

This project aims to create an LLM-powered bot capable of playing Slay the Spire.

> [!NOTE]
> This project depends on data from the [Slay the Spire Reference Spreadsheet](https://docs.google.com/spreadsheets/d/1ZsxNXebbELpcCi8N7FVOTNGdX_K9-BRC_LMgx4TORo4) and the [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) mod. Both of these resources were created by [ForgottenArbiter](https://github.com/ForgottenArbiter). This project is not affiliated with ForgottenArbiter. However, I would like to thank him for his hard work and dedication to the Slay the Spire community.

## Current Project Structure

```text
slay_the_spire_agent/
├── logs/                   # Raw JSON game states generated during play
├── src/
│   ├── main.py             # Orchestrator: Connects to CommMod, handles UI/Logging
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
   uv pip sync requirements.txt
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

## Running the Debug Dashboard

To view the real-time agent tracker while playing the game, start the FastAPI dashboard in a separate terminal *before* launching Slay the Spire:

```bash
cd slay_the_spire_agent
uv run src/ui/dashboard.py
```

Once running, open your web browser to `http://localhost:8000/`. The dashboard will automatically update once you launch Slay the Spire and enter a combat encounter.
