import json
import os

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.ui.state_processor import process_state

app = FastAPI()

manual_actions_queue = []

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/update_state")
async def update_state(request: Request):
    try:
        data = await request.json()
        vm = process_state(data)
        message = json.dumps({"type": "state", "payload": vm})
        await manager.broadcast(message)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- Local Replay API ---
LOGS_DIR = os.path.join(BASE_DIR, "..", "..", "logs")


@app.get("/api/runs")
async def get_runs():
    """Returns a list of all available run directories in the logs folder."""
    try:
        if not os.path.exists(LOGS_DIR):
            return {"runs": []}
        runs = [d for d in os.listdir(LOGS_DIR) if os.path.isdir(os.path.join(LOGS_DIR, d))]
        runs.sort(reverse=True)
        return {"runs": runs}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/runs/{run_name}")
async def get_run_states(run_name: str):
    """Returns an ordered list of processed view-model payloads for a run."""
    try:
        run_path = os.path.join(LOGS_DIR, run_name)
        if not os.path.exists(run_path):
            return {"status": "error", "message": "Run not found"}

        states = []
        files = [f for f in os.listdir(run_path) if f.endswith('.json')]
        files.sort()

        for file in files:
            with open(os.path.join(run_path, file), 'r', encoding='utf-8') as f:
                data = json.load(f)
                states.append(process_state(data))

        return {"states": states}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/poll_instruction")
async def poll_instruction():
    """Called by main.py to see what it should do."""
    return {
        "manual_action": manual_actions_queue.pop(0) if manual_actions_queue else None
    }


@app.post("/log")
async def log_message(request: Request):
    try:
        data = await request.json()
        message = data.get("message", "")
        ws_msg = json.dumps({"type": "log", "payload": message})
        await manager.broadcast(ws_msg)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/action_taken")
async def action_taken(request: Request):
    try:
        data = await request.json()
        action = data.get("action", "")
        message = json.dumps({"type": "action", "payload": action})
        await manager.broadcast(message)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class ManualAction(BaseModel):
    action: str


@app.post("/submit_action")
async def submit_action(cmd: ManualAction):
    """Called by the frontend UI to queue a manual action."""
    action_str = cmd.action.strip()
    if action_str:
        manual_actions_queue.append(action_str)
        return {"status": "queued", "action": action_str}
    return {"status": "ignored"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
