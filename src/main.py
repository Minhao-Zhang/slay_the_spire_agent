import copy
import datetime
import json
import os
import sys
import threading
import requests
import time

# Set up logging directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DASHBOARD_URL = "http://localhost:8000"

def notify_dashboard(endpoint: str, data: dict):
    """Sends JSON data to the dashboard in a background thread."""
    def send():
        try:
            requests.post(f"{DASHBOARD_URL}{endpoint}", json=data, timeout=0.5)
        except requests.exceptions.RequestException:
            pass
    threading.Thread(target=send, daemon=True).start()

def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
    run_dir = os.path.join(LOG_DIR, timestamp)
    os.makedirs(run_dir, exist_ok=True)
    
    print("ready", flush=True)

    event_index = 0
    last_logged_state = None

    while True:
        line = sys.stdin.readline()
        if not line: break
        line = line.strip()
        if not line: continue

        try:
            state = json.loads(line)
            notify_dashboard("/update_state", state)
        except json.JSONDecodeError as e:
            print("wait 10", flush=True)
            continue

        # 1. Handle Game Not Ready
        if not state.get("ready_for_command", False):
            print("wait 10", flush=True)
            continue

        # 2. Check for manual actions from dashboard (only poll when game is ready,
        #    so we don't consume queued actions during non-ready states)
        manual_action = None
        try:
            inst = requests.get(f"{DASHBOARD_URL}/poll_instruction", timeout=0.2).json()
            manual_action = inst.get("manual_action")
        except:
            pass

        # 3. Log every new unique state
        is_duplicate = (state == last_logged_state)
        if not is_duplicate:
            path = os.path.join(run_dir, f"{event_index:04d}.json")
            with open(path, "w") as f:
                json.dump({"state": state, "action": manual_action}, f, indent=2)
            event_index += 1
            last_logged_state = copy.deepcopy(state)

        # 4. Handle Manual Action
        if manual_action:
            print(manual_action, flush=True)
            notify_dashboard("/action_taken", {"action": manual_action})
            last_logged_state = None
            continue

        # 5. Default: Keep game alive
        print("wait 10", flush=True)

if __name__ == "__main__":
    main()
