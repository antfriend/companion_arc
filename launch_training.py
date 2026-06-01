#!/usr/bin/env python3
"""
launch_training.py — run a LOCUS-guided ARC-AGI training attempt locally.

Usage:
    python launch_training.py [game_id]
    python launch_training.py ls20

Reads API keys from .env. After the run, LOCUS writes a new session log
record to companion_arcprize.md and updates [ew] metadata on any records
whose conf/sal/rev changed during the session.
"""

import argparse
import io
import os
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import re
from pathlib import Path

from dotenv import load_dotenv

from kaggle_agent import locus_query, run_training_attempt, setup

load_dotenv()

COMPANION_PATH = Path(__file__).parent / "companion_arcprize.md"

_parser = argparse.ArgumentParser(description="LOCUS-guided ARC-AGI training run")
_parser.add_argument("game_id", nargs="?", default="ls20")
_parser.add_argument(
    "--offline-levels", type=int, default=2, metavar="N",
    help="levels whose known route is hardcoded before handing off to LOCUS "
         "(default 2 = L1+L2 hardcoded via _LEVEL2_ROUTE; 1 = L1 only; 0 = LOCUS from step 0)",
)
_parser.add_argument(
    "--env-dir", default=None, metavar="DIR",
    help="path to environment_files directory for OFFLINE mode "
         "(e.g. C:\\Temp\\arc3\\extracted\\environment_files)",
)
_args = _parser.parse_args()

GAME_ID = _args.game_id
OFFLINE_LEVELS = _args.offline_levels
ENV_DIR = _args.env_dir

# Known winning routes for competition games (indices into is_simple() action space)
# ls20 uses the kaggle_agent.py defaults; others are looked up here
_COMPETITION_ROUTES: dict[str, dict[int, list[int]]] = {
    "cd82": {1: [3, 0, 1, 0, 0, 0, 1, 1, 1, 3, 2, 0, 4, 4, 2, 0, 0, 0, 1]},
    "sp80": {1: [4, 3, 3, 3, 4, 2, 2, 1]},
}


# ---------------------------------------------------------------------------
# LOCUS self-update
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


def _apply_ew_updates(companion_file: Path, ew_updates_text: str) -> None:
    """
    Parse LOCUS's [ew] update instructions and patch them into the file.

    LOCUS is expected to emit one or more blocks of the form:
        @LATXLONY
        [ew]
        conf:N
        rev:N
        sal:N
        touched:N
        [/ew]
    """
    content = companion_file.read_text(encoding="utf-8")
    update_blocks = re.findall(
        r"(@LAT-?\d+LON-?\d+).*?(\[ew\].*?\[/ew\])",
        ew_updates_text,
        re.DOTALL,
    )
    if not update_blocks:
        return

    updated = 0
    for record_id, new_ew in update_blocks:
        pattern = re.compile(
            rf"({re.escape(record_id)}[^\n]*\n)\[ew\].*?\[/ew\]",
            re.DOTALL,
        )
        new_content, n = pattern.subn(rf"\g<1>{new_ew}", content, count=1)
        if n:
            content = new_content
            updated += 1
            print(f"  [ew] updated: {record_id}")

    if updated:
        companion_file.write_text(content, encoding="utf-8")
        print(f"[locus_apply_updates] {updated} [ew] block(s) patched in {companion_file.name}")


def locus_apply_updates(
    client,
    companion_text: str,
    game_id: str,
    result: dict,
) -> None:
    """
    Ask LOCUS to generate session record text and [ew] updates, then write
    both to companion_arcprize.md.

    New session record is appended. [ew] metadata blocks are patched in-place
    for any records whose conf/sal/rev changed this session.
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

    print("\n[locus_apply_updates] Asking LOCUS to generate updates...")
    response = locus_query(client, companion_text, prompt)
    print(f"\n[LOCUS]\n{response}\n")

    # Split on the separator — if absent, treat the whole response as the new record
    parts = response.split("---UPDATE-EW---", 1)
    new_record_text = parts[0].strip()
    ew_updates_text = parts[1].strip() if len(parts) > 1 else ""

    # Append new session record
    with open(COMPANION_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n---\n\n{new_record_text}\n")
    print(f"[locus_apply_updates] Session record appended to {COMPANION_PATH.name}")

    # Patch [ew] blocks on existing records
    if ew_updates_text:
        _apply_ew_updates(COMPANION_PATH, ew_updates_text)
    else:
        print("[locus_apply_updates] No [ew] updates returned by LOCUS")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    client, companion = setup(
        companion_source=str(COMPANION_PATH),
        model="claude-sonnet-4-6",
    )

    print(f"\n[launch] Starting '{GAME_ID}' in practice mode\n")

    game_prefix = GAME_ID.split("-")[0]
    result = run_training_attempt(
        game_id=GAME_ID,
        client=client,
        companion_text=companion,
        max_steps=125,
        competition_mode=False,
        verbose=True,
        offline_levels=OFFLINE_LEVELS,
        environments_dir=ENV_DIR,
        game_routes=_COMPETITION_ROUTES.get(game_prefix),
    )

    print(f"\n[launch] Training complete")
    print(f"  game_id:          {result['game_id']}")
    print(f"  steps:            {result['steps']}")
    print(f"  levels_completed: {result['levels_completed']}")
    print(f"  final_state:      {result['final_state']}")
    if result["scorecard"]:
        print(f"  scorecard:        {result['scorecard']}")

    locus_apply_updates(
        client=client,
        companion_text=companion,
        game_id=GAME_ID,
        result=result,
    )


if __name__ == "__main__":
    main()
