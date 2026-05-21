#!/usr/bin/env python3
"""
launch_competition.py — ARC-AGI competition attempt, fully offline.

Usage (Kaggle notebook cell):
    !python /kaggle/input/companion-arc/launch_competition.py ls20

Level 1 is solved with the known hardcoded route — no Anthropic key needed.
Only ARC_API_KEY is required (set via Kaggle Secrets before running).

Submission file is written to /kaggle/working/submission.parquet.
"""

import os
import sys
from pathlib import Path

import pandas as pd

from kaggle_agent import run_training_attempt

GAME_ID = sys.argv[1] if len(sys.argv) > 1 else "ls20"

_HERE = Path(__file__).parent
_WORKING = Path("/kaggle/working") if Path("/kaggle/working").exists() else _HERE


# ---------------------------------------------------------------------------
# Submission writer
# ---------------------------------------------------------------------------

def write_submission(result: dict, output_dir: Path) -> Path:
    """Write submission.parquet required by Kaggle's submission system."""
    final_state = result.get("final_state", "")
    df = pd.DataFrame([{
        "row_id": "1_0",
        "game_id": result["game_id"],
        "end_of_game": final_state in ("win", "game_over"),
        "score": int(result.get("levels_completed", 0)),
    }])
    path = output_dir / "submission.parquet"
    df.to_parquet(path, index=False)
    print(f"[submission] Written to {path}")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not os.environ.get("ARC_API_KEY"):
        raise EnvironmentError(
            "ARC_API_KEY not set. In Kaggle: add it under notebook Settings → Secrets."
        )

    print(f"\n[launch] Starting '{GAME_ID}' in COMPETITION mode (offline L1)\n")

    result = run_training_attempt(
        game_id=GAME_ID,
        client=None,
        companion_text=None,
        max_steps=60,
        competition_mode=True,
        verbose=True,
        offline_levels=1,
        stop_after_offline=True,
    )

    print(f"\n[launch] Competition run complete")
    print(f"  game_id:          {result['game_id']}")
    print(f"  steps:            {result['steps']}")
    print(f"  levels_completed: {result['levels_completed']}")
    print(f"  final_state:      {result['final_state']}")
    if result["scorecard"]:
        print(f"  scorecard:        {result['scorecard']}")

    write_submission(result, _WORKING)


if __name__ == "__main__":
    main()
