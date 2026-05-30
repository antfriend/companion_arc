#!/usr/bin/env python3
"""
search_routes.py — Find winning routes for ARC-AGI-3 competition games.

Uses random sampling: for each game, tries many short random action sequences
to find one that completes level 1.
"""

import random
import sys
import time
from pathlib import Path

import arc_agi
from arc_agi import OperationMode

ENV_DIR = r"C:\Temp\arc3\extracted\environment_files"
ACTION_NAMES = {0: "UP", 1: "DOWN", 2: "LEFT", 3: "RIGHT"}  # directional games only

KNOWN = {"ls20"}  # already have a route

# How many random trials per game
TRIALS = 500
# Max route length to try
MAX_LEN = 25
# Time limit per game (seconds)
TIME_LIMIT = 60


def _simple_actions(env):
    """Return only simple (non-click) actions from the action space."""
    return [a for a in (env.action_space or []) if a.is_simple()]


def try_route(arcade, game_id, route):
    """Play a route and return levels_completed."""
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
            name = ACTION_NAMES.get(idx, str(idx))
        count = 1
        while i + count < len(route) and route[i + count] == route[i]:
            count += 1
        parts.append(f"{name}×{count}" if count > 1 else name)
        i += count
    return " ".join(parts)


def _n_actions(arcade, game_id):
    """Return the number of simple actions available for this game."""
    env = arcade.make(game_id)
    if env is None:
        return 4
    return max(1, len(_simple_actions(env)))


def search_game(arcade, game_id):
    """Try random routes of increasing length; return winning route or None."""
    n = _n_actions(arcade, game_id)
    rng = random.Random(42)
    deadline = time.time() + TIME_LIMIT

    # Systematic: repeat each action for every length
    for a in range(n):
        for length in range(1, MAX_LEN + 1):
            if time.time() > deadline:
                break
            if try_route(arcade, game_id, [a] * length) == 1:
                return [a] * length

    # Also try the ls20 fallback route
    if try_route(arcade, game_id, [0, 0, 0, 0, 2, 2, 2, 1, 0, 3, 3, 3, 0, 0, 0]) == 1:
        return [0, 0, 0, 0, 2, 2, 2, 1, 0, 3, 3, 3, 0, 0, 0]

    # Random sampling
    tried = 0
    for length in range(1, MAX_LEN + 1):
        for _ in range(max(1, TRIALS // MAX_LEN)):
            if time.time() > deadline:
                return None
            route = [rng.randrange(n) for _ in range(length)]
            tried += 1
            if try_route(arcade, game_id, route) == 1:
                print(f"  found after {tried} trials", flush=True)
                return route

    return None


def main():
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
        print(f"{game_id}: searching...", flush=True)
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
    print("\n=== WINNING ROUTES ===")
    for game, val in results.items():
        if val:
            route, acts = val
            nums = ",".join(str(a) for a in route)
            print(f"  {game}: [{nums}]  # {format_route(route, acts)}")
        else:
            print(f"  {game}: None")


if __name__ == "__main__":
    main()
