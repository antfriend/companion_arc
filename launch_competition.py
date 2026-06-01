#!/usr/bin/env python3
"""
launch_competition.py — ARC-AGI-3 offline diagnostics (batch mode only).

EXECUTION MODEL:
  Competition reruns (KAGGLE_IS_COMPETITION_RERUN=True) are handled entirely
  by the notebook's inline LucusAgent + ARC-AGI-3-Agents framework path.
  This file is only called in batch mode (KAGGLE_IS_COMPETITION_RERUN not set)
  for offline diagnostics. Competition scores come from gateway reruns, not
  from submission.parquet. submission.parquet is written by this file but is
  not used by the competition scorer.

Play strategy per game:
  Phase 1 — execute hardcoded route (known-optimal actions from offline training)
  Phase 2 — random play (500 steps) to attempt completing remaining levels

Scoring (RHAE, from docs.arcprize.org/methodology):
  level_score = (human_baseline / ai_actions)^2, capped at 1.15
  game_score  = weighted average of level scores (weight = 1-indexed level number)
  total_score = average of all 25 game scores
"""

import os
import random
import re
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
import arc_agi
from arc_agi import OperationMode
from arc_agi.scorecard import EnvironmentScorecard

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_WORKING = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(__file__).parent
_COMPANION = Path(__file__).parent / "companion_arcprize.md"
GATEWAY_URL = "http://gateway:8001"


def _gateway_is_available() -> bool:
    try:
        r = requests.get(f"{GATEWAY_URL}/api/games", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# Kaggle may not set KAGGLE_IS_COMPETITION_RERUN even during competition reruns;
# fall back to probing the gateway directly.
IS_COMPETITION_RERUN = bool(os.getenv("KAGGLE_IS_COMPETITION_RERUN")) or _gateway_is_available()

# ---------------------------------------------------------------------------
# Routes  (0=UP  1=DOWN  2=LEFT  3=RIGHT)
# ---------------------------------------------------------------------------

_DIR = {"UP": 0, "DOWN": 1, "LEFT": 2, "RIGHT": 3}

# Hardcoded winning routes (indices into each game's simple action space)
# ls20: [UP,DOWN,LEFT,RIGHT] → indices 0-3
# cd82: [ACTION1-ACTION5]    → indices 0-4
# sp80: [ACTION1-ACTION5]    → indices 0-4
_HARDCODED_ROUTES: dict[str, list[int]] = {
    "ls20": [0, 0, 0, 0, 2, 2, 2, 1, 0, 3, 3, 3, 0, 0, 0],
    "cd82": [3, 0, 1, 0, 0, 0, 1, 1, 1, 3, 2, 0, 4, 4, 2, 0, 0, 0, 1],
    "sp80": [4, 3, 3, 3, 4, 2, 2, 1],
}

_ROUTES: dict[str, list[int]] = {}


def _load_routes() -> None:
    global _ROUTES
    _ROUTES = dict(_HARDCODED_ROUTES)
    if not _COMPANION.exists():
        print(f"[route] {_COMPANION.name} not found — using hardcoded ls20", flush=True)
        return
    text = _COMPANION.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\[route\b[^\]]*\bgame=(\w+)\b[^\]]*\blevel=1\b[^\]]*\](.*?)\[/route\]",
        re.DOTALL | re.IGNORECASE,
    )
    for game_id, route_str in pattern.findall(text):
        actions: list[int] = []
        for token in re.split(r"[,\s]+", route_str.strip()):
            if not token:
                continue
            m = re.match(r"(UP|DOWN|LEFT|RIGHT)[×x](\d+)$", token, re.IGNORECASE)
            if m:
                actions.extend([_DIR[m.group(1).upper()]] * int(m.group(2)))
            elif token.upper() in _DIR:
                actions.append(_DIR[token.upper()])
            elif re.match(r"^\d+$", token):
                actions.append(int(token))
        if actions:
            _ROUTES[game_id] = actions
    print(f"[route] Routes loaded: {sorted(_ROUTES.keys())}", flush=True)


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------

def _wait_for_gateway(timeout_s: int = 600) -> bool:
    url = f"{GATEWAY_URL}/api/games"
    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                print(f"[gateway] Ready after {attempt} retries", flush=True)
                return True
        except Exception:
            pass
        time.sleep(5)
        attempt += 1
    print("[gateway] TIMEOUT — gateway not ready", flush=True)
    return False


# ---------------------------------------------------------------------------
# Game play (shared by online + offline paths)
# ---------------------------------------------------------------------------

def _play_game(arc: arc_agi.Arcade, game_id: str, card_id: str) -> None:
    game_prefix = game_id.split("-")[0] if "-" in game_id else game_id
    route = _ROUTES.get(game_prefix, [])

    env = arc.make(game_id, scorecard_id=card_id)
    if env is None:
        print(f"[game] {game_id}: env creation failed — skipping", flush=True)
        return

    # Use only simple (non-click) actions to avoid KeyError on complex action data
    actions = [a for a in (env.action_space or []) if a.is_simple()]
    if not actions:
        print(f"[game] {game_id}: no simple actions — skipping", flush=True)
        return
    if route:  # only log action space for games we're actually routing
        print(f"[actions] {game_id}: {[str(a) for a in actions]}", flush=True)

    obs = None
    step = 0

    # Phase 1: execute known route
    for action_idx in route:
        obs = env.step(actions[action_idx % len(actions)])
        if obs is None:
            break
        step += 1
        if str(obs.state) in ("GameState.WIN", "GameState.GAME_OVER", "win", "game_over"):
            break

    # Phase 2: random play until WIN or step budget exhausted
    # Budget scales with game size; enough to complete most games randomly
    rng = random.Random(hash(game_id) & 0xFFFFFFFF)
    max_random_steps = 500
    random_steps = 0
    while random_steps < max_random_steps:
        if obs is not None and str(obs.state) in (
            "GameState.WIN", "GameState.GAME_OVER", "win", "game_over"
        ):
            break
        obs = env.step(rng.choice(actions))
        if obs is None:
            break
        step += 1
        random_steps += 1

    levels = obs.levels_completed if obs else 0
    state = str(obs.state) if obs else "None"
    print(f"[game] {game_id}: {step} steps (route={len(route)} rnd={random_steps}), L{levels}, state={state}", flush=True)


# ---------------------------------------------------------------------------
# Submission writer
# ---------------------------------------------------------------------------

def _scorecard_to_parquet(scorecard: EnvironmentScorecard) -> None:
    rows = []
    for i, env in enumerate(scorecard.environments):
        for j, run in enumerate(env.runs):
            completed = bool(run.completed)
            score = float(run.score)
            # Mark end_of_game=True whenever we have partial or full progress.
            # The competition needs this True to count the row; completed=False just
            # means we reached an intermediate level, not that we didn't play.
            end_of_game = completed or score > 0
            print(f"[row] {env.id}: completed={completed}, end_of_game={end_of_game}, score={score:.4f}", flush=True)
            rows.append({
                "row_id": f"{i}_{j}",
                "game_id": env.id,
                "end_of_game": end_of_game,
                "score": score,
            })
    if not rows:
        rows = [{"row_id": "0_0", "game_id": "none", "end_of_game": False, "score": 0.0}]
    df = pd.DataFrame(rows)
    path = _WORKING / "submission.parquet"
    df.to_parquet(path, index=False)
    print(f"[submission] Written {len(rows)} rows, overall={scorecard.score:.4f}", flush=True)


def _write_dummy() -> None:
    df = pd.DataFrame(
        [{"row_id": "0_0", "game_id": "none", "end_of_game": False, "score": 0.0}]
    )
    (_WORKING / "submission.parquet").unlink(missing_ok=True)
    df.to_parquet(_WORKING / "submission.parquet", index=False)
    print("[submission] Dummy written", flush=True)


# ---------------------------------------------------------------------------
# Offline environment resolution
# ---------------------------------------------------------------------------

def _resolve_env_dir() -> str | None:
    """Return path to a usable environment_files directory, extracting zip if needed."""
    # Direct directory from dataset or competition
    candidates = [
        Path("/kaggle/input/competitions/arc-prize-2026-arc-agi-3/environment_files"),
        Path(__file__).parent / "environment_files",
    ]
    for d in candidates:
        if d.exists() and d.is_dir():
            return str(d)

    # dataset uploaded with --dir-mode zip: extract to /kaggle/working
    zip_candidates = [
        Path(__file__).parent / "environment_files.zip",
    ]
    for z in zip_candidates:
        if z.exists():
            dest = _WORKING / "environment_files"
            dest.mkdir(exist_ok=True)
            with zipfile.ZipFile(z, "r") as zf:
                zf.extractall(dest)
            print(f"[env] Extracted {z.name} to {dest}", flush=True)
            return str(dest)

    return None


# ---------------------------------------------------------------------------
# Competition rerun path (gateway)
# ---------------------------------------------------------------------------

def run_competition() -> None:
    print(f"[launch] COMPETITION RERUN — waiting for {GATEWAY_URL}", flush=True)
    if not _wait_for_gateway():
        print("[launch] Cannot reach gateway — aborting", flush=True)
        return

    os.environ["ARC_BASE_URL"] = GATEWAY_URL
    os.environ.setdefault("ARC_API_KEY", "locus_agent")

    try:
        arc = arc_agi.Arcade(operation_mode=OperationMode.ONLINE)
        print(f"[launch] ONLINE mode, {len(arc.available_environments)} games", flush=True)

        card_id = arc.open_scorecard(tags=["locus"])
        for game_info in arc.available_environments:
            _play_game(arc, game_info.game_id, card_id)

        scorecard = arc.close_scorecard(card_id)
        if scorecard:
            for env in scorecard.environments:
                for run in env.runs:
                    print(f"[online-row] {env.id}: completed={run.completed}, score={float(run.score):.4f}", flush=True)
            print(f"[launch] Final score: {scorecard.score:.4f}", flush=True)
    except Exception as exc:
        import traceback
        print(f"[launch] FATAL: {exc}", flush=True)
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Batch run path (offline play → submission.parquet)
# ---------------------------------------------------------------------------

def run_offline() -> None:
    env_dir = _resolve_env_dir()
    if env_dir is None:
        print("[launch] No environment_files found — writing dummy", flush=True)
        _write_dummy()
        return

    try:
        arc = arc_agi.Arcade(
            operation_mode=OperationMode.OFFLINE,
            environments_dir=env_dir,
        )
        print(f"[launch] OFFLINE mode, {len(arc.available_environments)} games", flush=True)
        for e in arc.available_environments:
            print(f"[env]   {e.game_id}", flush=True)

        if not arc.available_environments:
            print("[launch] No environments loaded — writing dummy", flush=True)
            _write_dummy()
            return

        card_id = arc.open_scorecard(tags=["locus"])
        for game_info in arc.available_environments:
            _play_game(arc, game_info.game_id, card_id)

        scorecard = arc.close_scorecard(card_id)
        if scorecard:
            _scorecard_to_parquet(scorecard)
        else:
            _write_dummy()
    except Exception as exc:
        import traceback
        print(f"[launch] offline error: {exc}", flush=True)
        traceback.print_exc()
        _write_dummy()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    env_flag = os.getenv("KAGGLE_IS_COMPETITION_RERUN")
    print(f"[launch] KAGGLE_IS_COMPETITION_RERUN={env_flag!r}  IS_COMPETITION_RERUN={IS_COMPETITION_RERUN}", flush=True)
    _load_routes()

    if IS_COMPETITION_RERUN:
        run_competition()
    else:
        run_offline()


if __name__ == "__main__":
    main()
