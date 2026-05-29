#!/usr/bin/env python3
"""
launch_competition.py — ARC-AGI-3 competition submission.

The notebook IS the game server. Kaggle's evaluation system connects to
port 8001, opens a scorecard in competition_mode, plays all games, and
closes the scorecard. The on_scorecard_close callback writes submission.parquet.

A dummy submission.parquet is written before the server starts so the
notebook never fails with "no submission file" if the evaluator times out.
"""

import os
from pathlib import Path

import pandas as pd
import arc_agi
from arc_agi import OperationMode
from arc_agi.scorecard import EnvironmentScorecard

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_WORKING = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(__file__).parent

# Competition may supply environment files alongside the wheels; our dataset
# is the fallback. Both paths are checked at runtime.
_ENV_DIRS = [
    Path("/kaggle/input/competitions/arc-prize-2026-arc-agi-3/environment_files"),
    Path(__file__).parent / "environment_files",
    Path("environment_files"),
]


def _find_env_dir() -> str:
    for d in _ENV_DIRS:
        if d.exists() and d.is_dir():
            print(f"[env] Using environments_dir={d}", flush=True)
            return str(d)
    print("[env] No environment_files dir found — using default", flush=True)
    return "environment_files"


# ---------------------------------------------------------------------------
# Submission writer (called when scorecard closes)
# ---------------------------------------------------------------------------

def _write_submission(scorecard: EnvironmentScorecard) -> None:
    rows = []
    for i, env in enumerate(scorecard.environments):
        for j, run in enumerate(env.runs):
            rows.append({
                "row_id": f"{i}_{j}",
                "game_id": env.id,
                "end_of_game": bool(run.completed),
                "score": float(run.score),
            })
    if not rows:
        rows = [{"row_id": "0_0", "game_id": "none", "end_of_game": False, "score": 0.0}]
    df = pd.DataFrame(rows)
    path = _WORKING / "submission.parquet"
    df.to_parquet(path, index=False)
    print(f"[submission] Written {len(rows)} rows, overall_score={scorecard.score:.4f}", flush=True)


def _write_dummy() -> None:
    df = pd.DataFrame(
        [{"row_id": "0_0", "game_id": "none", "end_of_game": False, "score": 0.0}]
    )
    path = _WORKING / "submission.parquet"
    df.to_parquet(path, index=False)
    print(f"[submission] Dummy written to {path}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    environments_dir = _find_env_dir()

    arc = arc_agi.Arcade(
        operation_mode=OperationMode.OFFLINE,
        environments_dir=environments_dir,
    )
    print(f"[launch] {len(arc.available_environments)} environments loaded", flush=True)
    for e in arc.available_environments:
        print(f"[env]   {e.game_id}", flush=True)

    # Write a dummy first — overwritten by on_scorecard_close if evaluator connects
    _write_dummy()

    print("[launch] Starting server on 0.0.0.0:8001 ...", flush=True)
    arc.listen_and_serve(
        host="0.0.0.0",
        port=8001,
        competition_mode=True,
        on_scorecard_close=_write_submission,
        scorecard_timeout=300,  # auto-close idle scorecards after 5 min
    )


if __name__ == "__main__":
    main()
