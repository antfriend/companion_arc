#!/usr/bin/env python3
"""
launch_competition.py — ARC-AGI competition, level 1 offline.

Upload this file and companion_arcprize.md as a Kaggle Dataset.
Run from a notebook cell:
    !python /kaggle/input/<your-dataset>/launch_competition.py ls20

Only ARC_API_KEY is required. No internet needed. No Anthropic key needed.
Writes /kaggle/working/submission.parquet.

The L1 route is read from companion_arcprize.md (same directory as this
script) by looking for a [route] block written by LOCUS:

    [route game=ls20 level=1 steps=15 confirmed=true]
    UP×4, LEFT×3, DOWN, UP, RIGHT×3, UP×3
    [/route]

Falls back to a hardcoded default if the block is absent.
"""

import os
import re
import sys
from pathlib import Path

import pandas as pd
import arc_agi
from arc_agi import OperationMode

GAME_ID = sys.argv[1] if len(sys.argv) > 1 else "ls20"
_WORKING = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(__file__).parent
_COMPANION = Path(__file__).parent / "companion_arcprize.md"

_DIR = {"UP": 0, "DOWN": 1, "LEFT": 2, "RIGHT": 3}

# Used when companion is missing or contains no [route] block yet.
_FALLBACK_ROUTE = [0, 0, 0, 0, 2, 2, 2, 1, 0, 3, 3, 3, 0, 0, 0]


def _expand_route_str(s: str) -> list[int] | None:
    """Convert 'UP×4, LEFT×3, DOWN, UP, RIGHT×3, UP×3' → [0,0,0,0,2,2,2,1,0,3,3,3,0,0,0]."""
    actions = []
    for token in re.split(r"[,\s]+", s.strip()):
        if not token:
            continue
        m = re.match(r"(UP|DOWN|LEFT|RIGHT)[×x](\d+)$", token, re.IGNORECASE)
        if m:
            actions.extend([_DIR[m.group(1).upper()]] * int(m.group(2)))
        elif token.upper() in _DIR:
            actions.append(_DIR[token.upper()])
        else:
            return None  # unrecognised token — don't silently truncate
    return actions or None


def _parse_route_block(text: str, game_id: str, level: int = 1) -> list[int] | None:
    """
    Find the most recent [route game=<id> level=<N>] block written by LOCUS
    and return it as an action index list.
    """
    pattern = re.compile(
        rf"\[route\b[^\]]*\bgame={re.escape(game_id)}\b[^\]]*\blevel={level}\b[^\]]*\]"
        rf"(.*?)\[/route\]",
        re.DOTALL | re.IGNORECASE,
    )
    matches = pattern.findall(text)
    if not matches:
        return None
    # Last match = most recently written
    return _expand_route_str(matches[-1])


def _load_route(game_id: str) -> list[int]:
    if _COMPANION.exists():
        text = _COMPANION.read_text(encoding="utf-8")
        route = _parse_route_block(text, game_id)
        if route:
            print(f"[route] Loaded from companion ({len(route)} steps): {route}")
            return route
        print("[route] No [route] block found in companion — using fallback")
    else:
        print(f"[route] {_COMPANION.name} not found — using fallback")
    print(f"[route] Fallback: {_FALLBACK_ROUTE}")
    return _FALLBACK_ROUTE


def run_level1(game_id: str, route: list[int], verbose: bool = True) -> dict:
    arc = arc_agi.Arcade(operation_mode=OperationMode.COMPETITION)
    env = arc.make(game_id)
    obs = None
    step = 0
    for action_idx in route:
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
    route = _load_route(GAME_ID)
    print(f"\n[launch] '{GAME_ID}' — L1 offline route ({len(route)} steps)\n")
    result = run_level1(GAME_ID, route)
    print(f"\n  levels_completed: {result['levels_completed']}")
    print(f"  final_state:      {result['final_state']}")
    if result["scorecard"]:
        print(f"  scorecard:        {result['scorecard']}")
    write_submission(result, _WORKING)


if __name__ == "__main__":
    main()
