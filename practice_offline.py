#!/usr/bin/env python3
"""
practice_offline.py — Quick offline practice with step-by-step frame verification.

No LOCUS / Anthropic API calls. Uses local environment_files/ directory.
Prints a [verify] line after every action showing whether the frame changed
as expected, then reports the result.

Usage:
    python practice_offline.py
    python practice_offline.py ls20
    python practice_offline.py ls20 --levels 2
    python practice_offline.py ls20 --env-dir C:\\path\\to\\environment_files
"""

import argparse
import io
import os
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import arc_agi
from arc_agi import OperationMode

from core.game_registry import get_detector, get_companion_path

_DEFAULT_ENV_DIR = Path(__file__).parent / "environment_files"

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_parser = argparse.ArgumentParser(description="Offline practice with step-by-step verification")
_parser.add_argument("game_id", nargs="?", default="ls20",
                     help="game identifier (default: ls20)")
_parser.add_argument("--env-dir", default=str(_DEFAULT_ENV_DIR), metavar="DIR",
                     help=f"environment_files directory (default: {_DEFAULT_ENV_DIR})")
_parser.add_argument("--levels", type=int, default=1, metavar="N",
                     help="levels to attempt before stopping (default: 1)")
_parser.add_argument("--max-steps", type=int, default=50, metavar="N",
                     help="hard step cap for the whole run (default: 50)")
_args = _parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    game_id  = _args.game_id
    env_dir  = _args.env_dir
    max_lvls = _args.levels
    max_steps = _args.max_steps

    # --- Resolve detector ---------------------------------------------------
    detector = get_detector(game_id)
    if detector is None:
        print(f"[practice] No detector registered for '{game_id}'.")
        print(f"           Create games/{game_id}/detector.py to add one.")
        sys.exit(1)

    # --- Check env dir exists -----------------------------------------------
    if not Path(env_dir).exists():
        print(f"[practice] environment_files directory not found: {env_dir}")
        print( "           Pass --env-dir <path> or place environment_files/ here.")
        sys.exit(1)

    companion_path = get_companion_path(game_id)
    print(f"[practice] game={game_id}  env_dir={env_dir}  levels={max_lvls}")
    print(f"[practice] companion={companion_path}")

    # --- Check ARC_API_KEY --------------------------------------------------
    if not os.environ.get("ARC_API_KEY"):
        print("[practice] WARNING: ARC_API_KEY not set — game engine may fail.")

    # --- Build offline arcade -----------------------------------------------
    try:
        arc = arc_agi.Arcade(
            operation_mode=OperationMode.OFFLINE,
            environments_dir=env_dir,
        )
        env = arc.make(game_id)
    except Exception as exc:
        print(f"[practice] Failed to create environment: {exc}")
        sys.exit(1)

    step = 0
    levels_completed = 0

    while levels_completed < max_lvls and step < max_steps:
        level_num = levels_completed + 1
        print(f"\n{'='*50}")
        print(f"  Level {level_num}")
        print(f"{'='*50}")

        all_actions = env.action_space
        actions = [a for a in (all_actions or []) if a.is_simple()]
        if not actions:
            print("[practice] No simple actions available — stopping.")
            break

        n = len(actions)

        # --- Probe step: get initial frame ----------------------------------
        # One UP (action 0) is always safe as a probe for ls20.
        # compute_route() will see the post-probe block position and compute
        # the remaining distance correctly.
        obs = env.step(actions[0 % n])
        step += 1

        if not obs.frame:
            print("[practice] No frame returned — cannot detect state.")
            break

        prev_frame = obs.frame[0]

        # --- Detect state + compute route -----------------------------------
        try:
            state = detector.detect_state(prev_frame)
        except Exception as exc:
            print(f"[practice] detect_state failed: {exc}")
            break

        # Print detected state
        block_str = str(state.block_pos) if state.block_pos else "unknown"
        e2 = state.entity2_ring
        e2_str = (
            f"rows={e2['top']}-{e2['bot']} cols={e2['left']}-{e2['right']}"
            if e2 else "not detected"
        )
        print(f"[detect]  block={block_str}")
        print(f"[detect]  entity2={e2_str}")
        print(f"[detect]  entity1_state={state.entity1_state}")
        if state.cluster:
            cl = state.cluster
            print(f"[detect]  cluster=rows={cl['top_row']}-{cl['bot_row']} "
                  f"cols={cl['col_min']}-{cl['col_max']}")

        try:
            route = detector.compute_route(state)
        except Exception as exc:
            print(f"[practice] compute_route failed: {exc}")
            break

        _names = ["UP", "DOWN", "LEFT", "RIGHT"]
        route_names = [_names[a] if a < 4 else str(a) for a in route]
        print(f"[route]   {route}  →  {' '.join(route_names)}")
        print()

        # --- Check if probe step already completed the level ----------------
        if obs.levels_completed > levels_completed:
            print(f"[practice] Level {level_num} COMPLETE on probe step "
                  f"({step} total steps)")
            levels_completed = obs.levels_completed
            continue
        if obs.state in ("win", "game_over"):
            print(f"[practice] {obs.state} on probe step")
            break

        # --- Execute route with step-by-step verification -------------------
        level_done = False
        for route_idx, action_idx in enumerate(route):
            if step >= max_steps:
                print(f"\n[practice] Step cap reached ({max_steps})")
                break

            action_idx = action_idx % n
            name = _names[action_idx] if action_idx < 4 else str(action_idx)

            obs = env.step(actions[action_idx])
            step += 1

            if obs.frame:
                new_frame = obs.frame[0]
                try:
                    vr = detector.verify_step(prev_frame, new_frame, action_idx)
                    status = "OK  " if vr.success else "FAIL"
                    bp = vr.delta.get("before_pos", "?")
                    ap = vr.delta.get("after_pos",  "?")
                    print(f"  [{status}] step={step:3d}  "
                          f"route[{route_idx}]={action_idx} {name:<5s}  "
                          f"{vr.reason}  "
                          f"(before={bp} after={ap})")
                except Exception as exc:
                    print(f"  [ERR ] step={step:3d}  route[{route_idx}]  verify_step error: {exc}")
                prev_frame = new_frame
            else:
                print(f"  [----] step={step:3d}  route[{route_idx}]={action_idx} {name:<5s}  "
                      f"(no frame)")

            # Level complete?
            if obs.levels_completed > levels_completed:
                print(f"\n[practice] Level {level_num} COMPLETE  ({step} total steps)")
                levels_completed = obs.levels_completed
                level_done = True
                break

            # Game end?
            if obs.state in ("win", "game_over"):
                marker = "WIN" if obs.state == "win" else "GAME OVER"
                print(f"\n[practice] {marker}  "
                      f"levels={obs.levels_completed}  steps={step}")
                level_done = True
                levels_completed = obs.levels_completed
                break

        if not level_done:
            print(f"\n[practice] Route exhausted — level {level_num} not completed")
            break

    # --- Final report -------------------------------------------------------
    print(f"\n{'='*50}")
    print(f"  Result: levels_completed={levels_completed}  total_steps={step}")
    print(f"{'='*50}")
    try:
        sc = arc.get_scorecard()
        print(f"[scorecard] {sc}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
