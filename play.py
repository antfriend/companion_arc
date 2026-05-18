import os
import sys
import json
import queue
import argparse
import threading
from urllib.parse import urlparse, parse_qs
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
_game_state: dict = {
    "step": 0, "actions": [], "done": False,
    "obs_state": None, "levels_completed": 0,
    "frame_compact": None,  # sparse JSON representation of current frame(s)
}
_state_lock = threading.Lock()


def log(msg: str = "") -> None:
    print(msg)
    _log.write(msg + "\n")


# ---------------------------------------------------------------------------
# Compact grid encoding — replaces full numpy array dumps in the log.
# A 64×64 grid with large uniform regions compresses from ~500 tokens to ~20.
# ---------------------------------------------------------------------------

def _infer_bg(grid) -> int:
    """Background is the most-frequent cell value."""
    return int(np.bincount(grid.flatten()).argmax())


def compact_grid_str(grid, bg: int | None = None) -> str:
    """
    Sparse run-length text suitable for logging.

    Example output:
        grid 64x64 bg=4
          r8:  c32-40=3
          r9:  c32=3, c33-39=5, c40=3
    """
    rows, cols = grid.shape
    if bg is None:
        bg = _infer_bg(grid)
    lines = [f"grid {rows}x{cols} bg={bg}"]
    for r in range(rows):
        row = grid[r]
        if np.all(row == bg):
            continue
        segs = []
        c = 0
        while c < cols:
            val = int(row[c])
            start = c
            while c < cols and int(row[c]) == val:
                c += 1
            if val != bg:
                end = c - 1
                segs.append(f"c{start}={val}" if start == end else f"c{start}-{end}={val}")
        if segs:
            lines.append(f"  r{r}: " + ", ".join(segs))
    return "\n".join(lines)


def compact_grid_json(grid, bg: int | None = None) -> dict:
    """
    Sparse JSON representation for the /frame and /state HTTP endpoints.

    Schema: {"shape":[H,W], "bg":N, "runs":[{"r":R,"c0":C0,"c1":C1,"v":V}, ...]}
    Each run is a horizontal span of identical non-background cells.
    """
    rows, cols = grid.shape
    if bg is None:
        bg = _infer_bg(grid)
    runs = []
    for r in range(rows):
        row = grid[r]
        if np.all(row == bg):
            continue
        c = 0
        while c < cols:
            val = int(row[c])
            start = c
            while c < cols and int(row[c]) == val:
                c += 1
            if val != bg:
                runs.append({"r": r, "c0": start, "c1": c - 1, "v": val})
    return {"shape": [rows, cols], "bg": bg, "runs": runs}


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

def _json_response(handler, data: dict | list, status: int = 200) -> None:
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(body)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # suppress HTTP access log

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/state":
            # Existing endpoint — now also includes compact frame summary.
            with _state_lock:
                _json_response(self, _game_state)

        elif path == "/frame":
            # Compact sparse JSON for the current frame(s).
            # Cheaper than reading the log; no numpy arrays.
            # Response: {"frames": [<compact_grid_json>, ...]}
            with _state_lock:
                fc = _game_state.get("frame_compact")
            _json_response(self, {"frames": fc or []})

        elif path == "/log/tail":
            # Last N lines of session.log — lets Claude read just recent context.
            # GET /log/tail?n=50  (default 50)
            try:
                n = int(qs.get("n", ["50"])[0])
            except (ValueError, TypeError):
                n = 50
            n = max(1, min(n, 2000))
            try:
                with open(LOG_FILE, encoding="utf-8") as f:
                    lines = f.readlines()
                tail = "".join(lines[-n:])
            except OSError:
                tail = ""
            body = tail.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        elif path == "/log/grep":
            # Search the log for a pattern — returns matching lines.
            # GET /log/grep?q=STEP&n=20
            pattern = qs.get("q", [""])[0]
            try:
                n = int(qs.get("n", ["20"])[0])
            except (ValueError, TypeError):
                n = 20
            n = max(1, min(n, 500))
            matches = []
            if pattern:
                try:
                    with open(LOG_FILE, encoding="utf-8") as f:
                        for line in f:
                            if pattern in line:
                                matches.append(line.rstrip())
                            if len(matches) >= n:
                                break
                except OSError:
                    pass
            _json_response(self, {"pattern": pattern, "matches": matches})

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/action":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            _action_queue.put(str(data.get("action", "")))
            _json_response(self, {"status": "queued"}, 202)
        else:
            self.send_response(404)
            self.end_headers()


# ---------------------------------------------------------------------------
# Action pickers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Autopilot — sequence execution for learned levels
# ---------------------------------------------------------------------------

def _find_block_in_compact(compact_frame: dict, block_val: int = 12) -> list:
    """Return (row, col) list of positions where block_val appears in a compact grid."""
    cells = []
    for run in compact_frame.get("runs", []):
        if run["v"] == block_val:
            for c in range(run["c0"], run["c1"] + 1):
                cells.append((run["r"], c))
    return cells


def _verify_level_start(compact_frame: dict, cfg: dict) -> str:
    """
    Check block position after first action of a level against expected values.
    Returns 'PASS', 'WARN', or 'SKIP' (no verify_start key in cfg).
    """
    vc = cfg.get("verify_start")
    if not vc:
        return "SKIP"
    cells = _find_block_in_compact(compact_frame, vc.get("block_val", 12))
    if not cells:
        log("[AUTO] verify: block value not found in frame.")
        return "WARN"
    rows = sorted({r for r, _ in cells})
    cols = sorted({c for _, c in cells})
    log(f"[AUTO] block at rows {rows[0]}-{rows[-1]}, cols {cols[0]}-{cols[-1]}")
    ok = True
    exp_rows = vc.get("rows")
    exp_cols = vc.get("cols")
    if exp_rows and [rows[0], rows[-1]] != exp_rows:
        log(f"[AUTO] verify WARN: expected rows {exp_rows}, got [{rows[0]},{rows[-1]}]")
        ok = False
    if exp_cols and (cols[0] < exp_cols[0] or cols[-1] > exp_cols[1]):
        log(f"[AUTO] verify WARN: expected cols {exp_cols[0]}-{exp_cols[1]}, got {cols[0]}-{cols[-1]}")
        ok = False
    if ok:
        log("[AUTO] verify PASS")
    return "PASS" if ok else "WARN"


def load_sequences(path: str) -> list:
    """Load level sequences from a JSON file. Returns the 'levels' list."""
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("levels", [])


def run_auto(env, arc, seq_path: str, args) -> None:
    """Execute winning sequences for all learned levels without user input."""
    levels = load_sequences(seq_path)
    log(f"[AUTO] {len(levels)} level sequence(s) loaded from {os.path.basename(seq_path)}")

    completed = 0       # mirrors obs.levels_completed
    lvl_idx = 0         # index into levels[]
    seq_pos = 0         # position within current level's action sequence
    global_step = 0
    start_checked = False
    prev_frames: list = []

    while True:
        actions = env.action_space
        if not actions:
            log("\n[AUTO] No actions available — game complete.")
            break

        if lvl_idx >= len(levels):
            log(f"\n[AUTO] Level {lvl_idx + 1}: no recorded sequence. Stopping autopilot.")
            break

        cfg = levels[lvl_idx]
        seq = cfg["sequence"]
        lvl_num = cfg.get("level", lvl_idx + 1)

        if seq_pos >= len(seq):
            log(f"\n[AUTO] Sequence for level {lvl_num} exhausted ({len(seq)} steps) without win.")
            break

        ai = seq[seq_pos]
        if ai >= len(actions):
            log(f"[AUTO] Action index {ai} out of range ({len(actions)} available). Aborting.")
            break

        action = actions[ai]
        global_step += 1
        log(f"\n[AUTO] step={global_step} level={lvl_num} seq={seq_pos}/{len(seq)} action={ai}")

        obs = env.step(action)
        seq_pos += 1

        log(f"state={obs.state}  levels_completed={obs.levels_completed}  win_levels={obs.win_levels}")

        if obs.frame:
            compact_frames = []
            for i, grid in enumerate(obs.frame):
                if args.full:
                    log(f"frame[{i}]:\n{grid}")
                else:
                    log(f"frame[{i}]:\n{compact_grid_str(grid)}")
                compact_frames.append(compact_grid_json(grid))

                if i < len(prev_frames):
                    diff = np.argwhere(grid != prev_frames[i])
                    if len(diff):
                        log(f"DIFF frame[{i}]: {len(diff)} cell(s)")
                        for r, c in diff:
                            log(f"  [{r},{c}]: {prev_frames[i][r,c]}->{grid[r,c]}")
                    else:
                        log(f"NO CHANGE frame[{i}]")

            prev_frames = list(obs.frame)
            with _state_lock:
                _game_state["frame_compact"] = compact_frames

            if seq_pos == 1 and not start_checked:
                result = _verify_level_start(compact_frames[0], cfg)
                if result == "WARN":
                    log(f"[AUTO] Start mismatch on level {lvl_num}. Sequence may fail. Proceeding.")
                start_checked = True

        with _state_lock:
            _game_state.update({
                "step": global_step,
                "obs_state": obs.state,
                "levels_completed": obs.levels_completed,
                "done": obs.state in ("win", "game_over"),
            })

        if obs.levels_completed > completed:
            log(f"\n[AUTO] Level {lvl_num} WON in {seq_pos} steps! Advancing to level {lvl_num + 1}.")
            completed = obs.levels_completed
            lvl_idx += 1
            seq_pos = 0
            start_checked = False
            prev_frames = []

        if obs.state in ("win", "game_over"):
            log(f"\n[AUTO] Game ended: {obs.state}")
            break


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("game_id", nargs="?", help="Game ID (e.g. ls20)")
    parser.add_argument("--server", action="store_true", help="Accept actions via HTTP (default port 5001)")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--full", action="store_true",
                        help="Log full numpy arrays instead of compact sparse format")
    parser.add_argument("--auto", action="store_true",
                        help="Autopilot mode: execute winning sequences from JSON file (no user input required)")
    parser.add_argument("--sequences", type=str,
                        help="Path to sequences JSON (default: <game_id>_sequences.json in script directory)")
    args = parser.parse_args()

    if args.auto and not args.game_id:
        parser.error("--auto requires game_id as a positional argument")
    game_id = args.game_id or input("Game ID (e.g. ls20): ").strip()

    if args.server:
        httpd = HTTPServer(("localhost", args.port), _Handler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        log(f"HTTP interface on http://localhost:{args.port}/")
        log("  GET  /state          -> {step, actions, done, obs_state, levels_completed, frame_compact}")
        log("  GET  /frame          -> {frames: [sparse_grid, ...]}  (compact JSON, no numpy)")
        log("  GET  /log/tail?n=N   -> last N lines of session.log  (default 50)")
        log("  GET  /log/grep?q=PAT&n=N -> first N lines matching PAT")
        log("  POST /action         -> {\"action\": N}  or  {\"action\": \"quit\"}")
        pick_fn = pick_action_server
    else:
        pick_fn = pick_action_interactive

    arc = arc_agi.Arcade(operation_mode=OperationMode.COMPETITION)
    env = arc.make(game_id)

    log(f"\nStarted '{game_id}' in COMPETITION mode.")

    if args.auto:
        seq_default = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{game_id}_sequences.json")
        seq_path = args.sequences or seq_default
        if not os.path.isfile(seq_path):
            log(f"Sequences file not found: {seq_path}")
            sys.exit(1)
        log(f"[AUTO] Autopilot mode — sequences from {seq_path}")
        run_auto(env, arc, seq_path, args)
    else:
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
                compact_frames = []
                for i, grid in enumerate(obs.frame):
                    if args.full:
                        log(f"frame[{i}]:\n{grid}")
                    else:
                        log(f"frame[{i}]:\n{compact_grid_str(grid)}")
                    compact_frames.append(compact_grid_json(grid))

                    if i < len(prev_frames):
                        diff = np.argwhere(grid != prev_frames[i])
                        if len(diff):
                            log(f"DIFF frame[{i}]: {len(diff)} cell(s)")
                            for r, c in diff:
                                log(f"  [{r},{c}]: {prev_frames[i][r,c]}->{grid[r,c]}")
                        else:
                            log(f"NO CHANGE frame[{i}]")

                prev_frames = list(obs.frame)
                with _state_lock:
                    _game_state["frame_compact"] = compact_frames

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
    try:
        log(str(arc.get_scorecard()))
    except Exception as e:
        log(f"Scorecard unavailable: {e}")
    _log.close()


if __name__ == "__main__":
    main()
