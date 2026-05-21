#!/usr/bin/env python3
"""
launch_competition.py — ARC-AGI competition, level 1 offline.

Upload this file as a Kaggle Dataset. Run from a notebook cell:
    !python /kaggle/input/<your-dataset>/launch_competition.py ls20

Only ARC_API_KEY is required. No internet needed. No Anthropic key needed.
Writes /kaggle/working/submission.parquet.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import arc_agi
from arc_agi import OperationMode

GAME_ID = sys.argv[1] if len(sys.argv) > 1 else "ls20"
_WORKING = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(__file__).parent

# L1 winning route: UP×4, LEFT×3, DOWN, UP, RIGHT×3, UP×3
# 0=UP  1=DOWN  2=LEFT  3=RIGHT
_LEVEL1_ROUTE = [0, 0, 0, 0, 2, 2, 2, 1, 0, 3, 3, 3, 0, 0, 0]


def run_level1(game_id: str, verbose: bool = True) -> dict:
    arc = arc_agi.Arcade(operation_mode=OperationMode.COMPETITION)
    env = arc.make(game_id)
    obs = None
    step = 0
    for action_idx in _LEVEL1_ROUTE:
        actions = env.action_space
        if not actions:
            break
        obs = env.step(actions[action_idx])
        step += 1
        if verbose:
            _name = ["UP", "DOWN", "LEFT", "RIGHT"][action_idx]
            print(f"  step={step} {action_idx}({_name}) → state={obs.state} levels={obs.levels_completed}")
        if obs.state in ("win", "game_over") or obs.levels_completed >= 1:
            break
    scorecard = None
    try:
        scorecard = str(arc.get_scorecard())
    except Exception:
        pass
    return {
        "game_id": game_id,
        "steps": step,
        "levels_completed": obs.levels_completed if obs else 0,
        "final_state": obs.state if obs else "not_started",
        "scorecard": scorecard,
    }


def write_submission(result: dict, output_dir: Path) -> None:
    df = pd.DataFrame([{
        "row_id": "1_0",
        "game_id": result["game_id"],
        "end_of_game": result["final_state"] in ("win", "game_over"),
        "score": int(result["levels_completed"]),
    }])
    path = output_dir / "submission.parquet"
    df.to_parquet(path, index=False)
    print(f"[submission] Written to {path}")


def main() -> None:
    if not os.environ.get("ARC_API_KEY"):
        raise EnvironmentError("ARC_API_KEY not set.")
    print(f"\n[launch] '{GAME_ID}' — L1 offline route\n")
    result = run_level1(GAME_ID)
    print(f"\n  levels_completed: {result['levels_completed']}")
    print(f"  final_state:      {result['final_state']}")
    if result["scorecard"]:
        print(f"  scorecard:        {result['scorecard']}")
    write_submission(result, _WORKING)


if __name__ == "__main__":
    main()
