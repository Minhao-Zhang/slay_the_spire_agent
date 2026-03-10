import copy
import datetime
import json
import os
import sys

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")


def main():
    # Setup logging directory first
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    run_dir = os.path.join(LOG_DIR, timestamp)
    os.makedirs(run_dir, exist_ok=True)

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
        
        # We have a valid, actionable state. Log it.
        action = "wait 10"  # We just wait 10 frames and observe again
        
        path = os.path.join(run_dir, f"{event_index:04d}.json")
        with open(path, "w") as f:
            json.dump({"state": state, "action": action}, f, indent=2)
            
        event_index += 1

        # Tell the game what to do next
        print(action, flush=True)


if __name__ == "__main__":
    main()
