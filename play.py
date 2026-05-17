import os
import sys
import json
import queue
import argparse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import numpy as np
import arc_agi
from arc_agi import OperationMode
from dotenv import load_dotenv

np.set_printoptions(threshold=np.inf, linewidth=200)

load_dotenv()

if not os.getenv("ARC_API_KEY"):
    print("ARC_API_KEY not set. Add it to .env or set it in your environment.")
    sys.exit(1)

LOG_FILE = os.path.join(os.path.dirname(__file__), "session.log")
_log = open(LOG_FILE, "w", buffering=1, encoding="utf-8")

_action_queue: queue.Queue = queue.Queue()
_game_state: dict = {"step": 0, "actions": [], "done": False, "obs_state": None, "levels_completed": 0}
_state_lock = threading.Lock()


def log(msg: str = "") -> None:
    print(msg)
    _log.write(msg + "\n")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # suppress HTTP access log

    def do_GET(self):
        if self.path == "/state":
            with _state_lock:
                body = json.dumps(_game_state).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/action":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            _action_queue.put(str(data.get("action", "")))
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"queued"}')
        else:
            self.send_response(404)
            self.end_headers()


def pick_action_interactive(actions: list) -> object | None:
    log("\nAvailable actions:")
    for i, action in enumerate(actions):
        log(f"  {i}: {action}")
    raw = input("\nAction (number or 'quit'): ").strip().lower()
    log(f"Input: {raw}")
    if raw == "quit":
        return None
    try:
        return actions[int(raw)]
    except (ValueError, IndexError):
        log("Invalid — try again.")
        return pick_action_interactive(actions)


def pick_action_server(actions: list) -> object | None:
    log("\nAvailable actions:")
    for i, action in enumerate(actions):
        log(f"  {i}: {action}")
    with _state_lock:
        _game_state["actions"] = list(range(len(actions)))
    log("Waiting for POST /action ...")
    while True:
        raw = _action_queue.get().strip().lower()
        log(f"Input: {raw}")
        if raw == "quit":
            return None
        try:
            return actions[int(raw)]
        except (ValueError, IndexError):
            log(f"Invalid action '{raw}' — ignored, still waiting.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("game_id", nargs="?", help="Game ID (e.g. ls20)")
    parser.add_argument("--server", action="store_true", help="Accept actions via HTTP (default port 5001)")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()

    game_id = args.game_id or input("Game ID (e.g. ls20): ").strip()

    if args.server:
        httpd = HTTPServer(("localhost", args.port), _Handler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        log(f"HTTP interface on http://localhost:{args.port}/")
        log("  GET  /state   -> {step, actions, done, obs_state, levels_completed}")
        log("  POST /action  -> {\"action\": N}  or  {\"action\": \"quit\"}")
        pick_fn = pick_action_server
    else:
        pick_fn = pick_action_interactive

    arc = arc_agi.Arcade(operation_mode=OperationMode.COMPETITION)
    env = arc.make(game_id)

    log(f"\nStarted '{game_id}' in COMPETITION mode.")
    if not args.server:
        log("Consult @LOCUS in Claude Code before committing each action.\n")

    prev_frames = []
    step = 0

    while True:
        actions = env.action_space
        if not actions:
            log("\nNo actions available — level complete.")
            break

        with _state_lock:
            _game_state.update({"step": step, "actions": list(range(len(actions))), "done": False})

        action = pick_fn(actions)
        if action is None:
            log("\nSession ended by user.")
            break

        step += 1
        obs = env.step(action)
        log(f"\n=== STEP {step} | state={obs.state}  levels_completed={obs.levels_completed}  win_levels={obs.win_levels} ===")
        if obs.frame:
            for i, grid in enumerate(obs.frame):
                log(f"frame[{i}]:\n{grid}")
                if i < len(prev_frames):
                    diff = np.argwhere(grid != prev_frames[i])
                    if len(diff):
                        log(f"CHANGED cells (row,col): old->new")
                        for r, c in diff:
                            log(f"  [{r},{c}]: {prev_frames[i][r,c]}->{grid[r,c]}")
                    else:
                        log("NO CHANGE from previous frame")
            prev_frames = list(obs.frame)

        with _state_lock:
            _game_state.update({
                "step": step,
                "obs_state": obs.state,
                "levels_completed": obs.levels_completed,
                "done": obs.state in ("win", "game_over"),
            })

        if hasattr(obs, "state") and obs.state in ("win", "game_over"):
            log(f"\nLevel ended: {obs.state}")
            break

    log("\n--- Scorecard ---")
    log(str(arc.get_scorecard()))
    _log.close()


if __name__ == "__main__":
    main()
