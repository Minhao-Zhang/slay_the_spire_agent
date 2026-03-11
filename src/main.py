import copy
import datetime
import json
import os
import sys
import threading
import requests
import shutil

# Set up logging directory rooted from the project root rather than this script
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DASHBOARD_URL = "http://localhost:8000"

def notify_dashboard(endpoint: str, data: dict):
    """Sends JSON data to the dashboard in a background thread so we don't block the game."""
    def send():
        try:
            requests.post(f"{DASHBOARD_URL}{endpoint}", json=data, timeout=0.5)
        except requests.exceptions.RequestException:
            pass # Dashboard is offline, ignore gracefully
    threading.Thread(target=send, daemon=True).start()

def enforce_log_limit(log_dir: str, limit: int = 20):
    """Ensures no more than `limit` log directories exist, deleting the oldest ones."""
    if not os.path.exists(log_dir):
        return
    
    subdirs = [os.path.join(log_dir, d) for d in os.listdir(log_dir) if os.path.isdir(os.path.join(log_dir, d))]
    subdirs.sort()  # Sorts by name, which is timestamp-based
    
    if len(subdirs) > limit:
        dirs_to_delete = subdirs[:-limit]
        for d in dirs_to_delete:
            try:
                shutil.rmtree(d)
                print(f"Deleted old log directory: {d}", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"Failed to delete old log directory {d}: {e}", file=sys.stderr, flush=True)

def main():
    # Setup logging directory first
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
    run_dir = os.path.join(LOG_DIR, timestamp)
    os.makedirs(run_dir, exist_ok=True)
    
    # Clean up old logs, keeping the last 20 sessions
    enforce_log_limit(LOG_DIR, limit=20)

    # 1. Immediately tell CommunicationMod we are ready
    print("ready", flush=True)

    event_index = 0
    last_logged_state = None

    # 2. Block and read lines one by one
    while True:
        line = sys.stdin.readline()
        if not line:
            break  # EOF, CommunicationMod closed the pipe

        line = line.strip()
        if not line:
            continue

        try:
            state = json.loads(line)
            # Update live dashboard with the current state
            notify_dashboard("/update_state", state)
            
        except json.JSONDecodeError as e:
            # Send errors to stderr so they appear in communication_mod_errors.log
            print(f"Failed to parse JSON: {e}", file=sys.stderr, flush=True)
            # Must respond with *something* so the game doesn't hang
            print("wait 10", flush=True)
            continue

        # If the game is just broadcasting state but isn't ready for a command (e.g. animations),
        # we don't log a new file, we just tell it to keep waiting.
        if not state.get("ready_for_command", False):
            print("wait 10", flush=True)
            continue

        if state == last_logged_state:
            print("wait 10", flush=True)
            continue
            
        last_logged_state = copy.deepcopy(state)
        
        # We have a valid, actionable state.
        action = "wait 10"  # We just wait 10 frames and observe again for now
        
        # Log to disk
        path = os.path.join(run_dir, f"{event_index:04d}.json")
        with open(path, "w") as f:
            json.dump({"state": state, "action": action}, f, indent=2)
            
        event_index += 1

        # Notify dashboard of the action being taken
        notify_dashboard("/action_taken", {"action": action})

        # Tell the game what to do next
        print(action, flush=True)


if __name__ == "__main__":
    main()
