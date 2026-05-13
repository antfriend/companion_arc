import os
import sys
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
_log = open(LOG_FILE, "w", buffering=1)


def log(msg: str = "") -> None:
    print(msg)
    _log.write(msg + "\n")


def pick_action(actions: list) -> object | None:
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
        return pick_action(actions)


def main():
    game_id = input("Game ID (e.g. ls20): ").strip()

    arc = arc_agi.Arcade(operation_mode=OperationMode.COMPETITION)
    env = arc.make(game_id)

    log(f"\nStarted '{game_id}' in COMPETITION mode.")
    log("Consult @LOCUS in Claude Code before committing each action.\n")

    prev_frames = []
    step = 0

    while True:
        actions = env.action_space
        if not actions:
            log("\nNo actions available — level complete.")
            break

        action = pick_action(actions)
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
                        log(f"CHANGED cells (row,col): old→new")
                        for r, c in diff:
                            log(f"  [{r},{c}]: {prev_frames[i][r,c]}→{grid[r,c]}")
                    else:
                        log("NO CHANGE from previous frame")
            prev_frames = list(obs.frame)

        if hasattr(obs, "state") and obs.state in ("win", "game_over"):
            log(f"\nLevel ended: {obs.state}")
            break

    log("\n--- Scorecard ---")
    log(str(arc.get_scorecard()))
    _log.close()


if __name__ == "__main__":
    main()
