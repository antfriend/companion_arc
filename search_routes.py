#!/usr/bin/env python3
"""
search_routes.py — Find winning routes for ARC-AGI-3 competition games.

Strategy per game:
  1. BFS/exhaustive for routes up to length BFS_MAX (fast, complete coverage)
  2. Systematic single-action repeats (all-0s, all-1s, ...) up to REPEAT_MAX
  3. Random sampling for longer routes

Usage:
  python search_routes.py [env_dir]

  env_dir defaults to C:\\Temp\\arc3\\extracted\\environment_files
  or the competition path /kaggle/input/competitions/arc-prize-2026-arc-agi-3/environment_files
"""

import itertools
import random
import sys
import time
from pathlib import Path

import arc_agi
from arc_agi import OperationMode

_DEFAULT_DIRS = [
    r"C:\Temp\arc3\extracted\environment_files",
    "/kaggle/input/competitions/arc-prize-2026-arc-agi-3/environment_files",
]

ENV_DIR = sys.argv[1] if len(sys.argv) > 1 else next(
    (d for d in _DEFAULT_DIRS if Path(d).exists()), _DEFAULT_DIRS[0]
)

# Games with known winning routes (skip in search)
KNOWN = {"ls20", "cd82", "sp80"}

# Search parameters
BFS_MAX = 6       # exhaustive BFS up to this length (n^BFS_MAX combos — keep ≤7)
REPEAT_MAX = 40   # try each single action repeated 1..REPEAT_MAX times
TRIALS = 2000     # random trials per length bucket
MAX_LEN = 35      # max route length for random search
TIME_LIMIT = 90   # seconds per game


def _simple_actions(env):
    return [a for a in (env.action_space or []) if a.is_simple()]


def try_route(arcade, game_id, route):
    env = arcade.make(game_id)
    if env is None:
        return -1
    actions = _simple_actions(env)
    if not actions:
        return 0
    obs = None
    for action_idx in route:
        obs = env.step(actions[action_idx % len(actions)])
        if obs is None:
            break
        if obs.levels_completed >= 1:
            return 1
    return 0


def format_route(route, action_objects=None):
    if not route:
        return ""
    parts = []
    i = 0
    while i < len(route):
        idx = route[i]
        if action_objects and idx < len(action_objects):
            name = str(action_objects[idx]).replace("GameAction.", "")
        else:
            name = {0: "UP", 1: "DOWN", 2: "LEFT", 3: "RIGHT"}.get(idx, f"A{idx}")
        count = 1
        while i + count < len(route) and route[i + count] == route[i]:
            count += 1
        parts.append(f"{name}×{count}" if count > 1 else name)
        i += count
    return " ".join(parts)


def _n_actions(arcade, game_id):
    env = arcade.make(game_id)
    if env is None:
        return 4
    return max(1, len(_simple_actions(env)))


def search_game(arcade, game_id):
    """Return winning route list or None."""
    n = _n_actions(arcade, game_id)
    rng = random.Random(42)
    deadline = time.time() + TIME_LIMIT

    # 1. BFS: exhaustive search up to BFS_MAX length
    for length in range(1, BFS_MAX + 1):
        if time.time() > deadline:
            break
        for route in itertools.product(range(n), repeat=length):
            if time.time() > deadline:
                break
            if try_route(arcade, game_id, list(route)) == 1:
                return list(route)

    # 2. Systematic single-action repeats beyond BFS_MAX
    for a in range(n):
        for length in range(BFS_MAX + 1, REPEAT_MAX + 1):
            if time.time() > deadline:
                break
            if try_route(arcade, game_id, [a] * length) == 1:
                return [a] * length

    # 3. Random sampling (length BFS_MAX+1 through MAX_LEN)
    tried = 0
    for length in range(BFS_MAX + 1, MAX_LEN + 1):
        for _ in range(max(1, TRIALS // (MAX_LEN - BFS_MAX))):
            if time.time() > deadline:
                return None
            route = [rng.randrange(n) for _ in range(length)]
            tried += 1
            if try_route(arcade, game_id, route) == 1:
                print(f"  found after {tried} random trials", flush=True)
                return route

    return None


def main():
    print(f"[env_dir] {ENV_DIR}", flush=True)
    arcade = arc_agi.Arcade(
        operation_mode=OperationMode.OFFLINE,
        environments_dir=ENV_DIR,
    )

    games = sorted(e.game_id for e in arcade.available_environments)
    print(f"Loaded {len(games)} games", flush=True)

    results = {}
    t0 = time.time()

    for game_id in games:
        prefix = game_id.split("-")[0]
        if prefix in KNOWN:
            print(f"{game_id}: SKIP (known)", flush=True)
            continue

        t1 = time.time()
        print(f"{game_id}: searching (BFS≤{BFS_MAX}, repeat≤{REPEAT_MAX}, rand×{TRIALS})...", flush=True)
        route = search_game(arcade, game_id)
        elapsed = time.time() - t1

        if route:
            env = arcade.make(game_id)
            acts = _simple_actions(env) if env else []
            fmt = format_route(route, acts)
            print(f"  WIN in {len(route)} steps: {fmt}  ({elapsed:.1f}s)", flush=True)
            results[prefix] = (route, acts)
        else:
            print(f"  NOT FOUND ({elapsed:.1f}s)", flush=True)
            results[prefix] = None

    total = time.time() - t0
    print(f"\nDone in {total:.1f}s", flush=True)

    # Output in copy-paste format for both competition files
    found = {g: v for g, v in results.items() if v}
    not_found = [g for g, v in results.items() if not v]

    print("\n=== WINNING ROUTES — paste into _ROUTES / _HARDCODED_ROUTES ===")
    for game, (route, acts) in sorted(found.items()):
        nums = ", ".join(str(a) for a in route)
        fmt = format_route(route, acts)
        print(f'    "{game}": [{nums}],  # {fmt}')

    if not_found:
        print(f"\nNOT FOUND ({len(not_found)}): {', '.join(sorted(not_found))}")

    print(f"\nSummary: {len(found)} found, {len(not_found)} not found out of {len(results)} searched")


if __name__ == "__main__":
    main()
