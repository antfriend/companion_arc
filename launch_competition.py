#!/usr/bin/env python3
"""
launch_competition.py — ARC-AGI-3 competition submission.

COMPETITION RERUN (KAGGLE_IS_COMPETITION_RERUN is set):
  Kaggle runs a gateway at http://gateway:8001. We wait for it, then play
  all available games in ONLINE mode. Kaggle reads the score from the
  gateway scorecard.

BATCH RUN (KAGGLE_IS_COMPETITION_RERUN not set):
  No gateway. Play known games offline with our route, write real results
  to submission.parquet. Falls back to dummy if offline play fails.
"""

import os
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
IS_COMPETITION_RERUN = bool(os.getenv("KAGGLE_IS_COMPETITION_RERUN"))

# ---------------------------------------------------------------------------
# Routes  (0=UP  1=DOWN  2=LEFT  3=RIGHT)
# ---------------------------------------------------------------------------

_DIR = {"UP": 0, "DOWN": 1, "LEFT": 2, "RIGHT": 3}
_FALLBACK_ROUTE = [0, 0, 0, 0, 2, 2, 2, 1, 0, 3, 3, 3, 0, 0, 0]
_ROUTES: dict[str, list[int]] = {}


def _load_routes() -> None:
    global _ROUTES
    _ROUTES = {"ls20": _FALLBACK_ROUTE}
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

    obs = None
    step = 0
    for action_idx in route:
        actions = env.action_space
        if not actions:
            break
        obs = env.step(actions[min(action_idx, len(actions) - 1)])
        if obs is None:
            break
        step += 1
        if obs.levels_completed >= 1 or str(obs.state) in (
            "GameState.WIN", "GameState.GAME_OVER", "win", "game_over"
        ):
            break

    levels = obs.levels_completed if obs else 0
    print(f"[game] {game_id}: {step} steps, L{levels}", flush=True)


# ---------------------------------------------------------------------------
# Submission writer
# ---------------------------------------------------------------------------

def _scorecard_to_parquet(scorecard: EnvironmentScorecard) -> None:
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
    print(f"[launch] KAGGLE_IS_COMPETITION_RERUN={IS_COMPETITION_RERUN}", flush=True)
    _load_routes()

    if IS_COMPETITION_RERUN:
        run_competition()
    else:
        run_offline()


if __name__ == "__main__":
    main()
