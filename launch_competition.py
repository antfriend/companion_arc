#!/usr/bin/env python3
"""
launch_competition.py — run a LOCUS-guided ARC-AGI competition attempt.

Usage (Kaggle notebook cell):
    !python /kaggle/input/companion-arc/launch_competition.py ls20

Reads API keys from environment (set via Kaggle Secrets before running).
Companion is loaded from the same directory as this script, or from
COMPANION_URL if the local file is not present (internet must be enabled).

Session log is written to /kaggle/working/session_log_<game_id>.md
(input files are read-only on Kaggle; log goes to working dir instead).
"""

import os
import re
import sys
from pathlib import Path

import pandas as pd

from kaggle_agent import COMPANION_URL, locus_query, run_training_attempt, setup

GAME_ID = sys.argv[1] if len(sys.argv) > 1 else "ls20"

_HERE = Path(__file__).parent
_LOCAL_COMPANION = _HERE / "companion_arcprize.md"
COMPANION_SOURCE = str(_LOCAL_COMPANION) if _LOCAL_COMPANION.exists() else COMPANION_URL

_WORKING = Path("/kaggle/working") if Path("/kaggle/working").exists() else _HERE
SESSION_LOG_PATH = _WORKING / f"session_log_{GAME_ID}.md"


# ---------------------------------------------------------------------------
# LOCUS self-update (writes to working dir, not read-only input)
# ---------------------------------------------------------------------------

def _build_session_summary(result: dict) -> str:
    entries = result.get("locus_entries", [])
    lines = []
    for e in entries:
        if any(tag in e["label"] for tag in ("STATUS", "LOG", "REVISION", "FOCUS")):
            lines.append(f"[{e['label']}]")
            lines.append(f"SENT: {e['sent']}")
            lines.append(f"LOCUS: {e['received']}")
            lines.append("")
    return "\n".join(lines)


def locus_log_session(
    client,
    companion_text: str,
    game_id: str,
    result: dict,
) -> None:
    """
    Ask LOCUS to generate a session record and write it to the working dir.
    On Kaggle the input dataset is read-only, so we can't patch companion_arcprize.md
    in-place. The output file can be downloaded and applied locally via Claude Code.
    """
    session_summary = _build_session_summary(result)

    prompt = f"""@LOCUS session complete — please update yourself.

Game: {game_id}
Steps taken: {result['steps']}
Levels completed: {result['levels_completed']}
Final state: {result['final_state']}
Scorecard: {result['scorecard']}

Key session exchanges:
{session_summary}

Write two sections:

SECTION 1 — new session log record in valid TTDB format.
Use the next available LAT coordinate south of the most recent log entry.
Include the full header line, [ew] block (conf/rev/sal/touched), and a body
summarising this session: level outcomes, mechanic observations, revision
cycle results, and any open questions.

SECTION 2 — [ew] metadata updates for existing records.
For each record whose conf, sal, or rev should change based on this session,
write its record ID (@LATXLONY) followed by its complete new [ew] block.

Separate the two sections with exactly this line:
---UPDATE-EW---"""

    print("\n[locus_log_session] Asking LOCUS to generate session record...")
    response = locus_query(client, companion_text, prompt)
    print(f"\n[LOCUS]\n{response}\n")

    with open(SESSION_LOG_PATH, "w", encoding="utf-8") as f:
        f.write(response)
    print(f"[locus_log_session] Session record written to {SESSION_LOG_PATH}")
    print(f"  Download and apply locally: @locus dream (in Claude Code)")


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
    client, companion = setup(
        companion_source=COMPANION_SOURCE,
        model="claude-sonnet-4-6",
    )

    print(f"\n[launch] Starting '{GAME_ID}' in COMPETITION mode\n")

    result = run_training_attempt(
        game_id=GAME_ID,
        client=client,
        companion_text=companion,
        max_steps=60,
        competition_mode=True,
        verbose=True,
    )

    print(f"\n[launch] Competition run complete")
    print(f"  game_id:          {result['game_id']}")
    print(f"  steps:            {result['steps']}")
    print(f"  levels_completed: {result['levels_completed']}")
    print(f"  final_state:      {result['final_state']}")
    if result["scorecard"]:
        print(f"  scorecard:        {result['scorecard']}")

    locus_log_session(
        client=client,
        companion_text=companion,
        game_id=GAME_ID,
        result=result,
    )

    write_submission(result, _WORKING)


if __name__ == "__main__":
    main()
