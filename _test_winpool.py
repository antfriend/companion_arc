"""Per-game flaky-win pool for the ACTUAL submitted explorers (random / v1 / goal).

Answers: on the games we DO have (canonical), which games does the explorer ever
complete, and how reliably? A leaderboard score is the mean of per-game scores; if
only a handful are winnable and each is won stochastically, the score is "a few
flaky wins + noise" (and run-to-run which-games-win drives the variance). This
sweeps many seeds and reports per-game win-rate (L1+ completion) per policy.

NOTE: canonical != the hidden scored set, so this is a stand-in for the STRUCTURE
(stable vs random pool), not the hidden-set numbers. The submitted policy scores ~0
on most canonical games (they need routes / are precise), so expect a small pool.

Usage: python _test_winpool.py [--seeds N] [--budget N] [game ...]
"""
import importlib.util
import io
import random
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.general_agent import GeneralAgent
from core.goal_agent import GoalSeekAgent

ROOT = Path(__file__).parent
ENV_DIR = ROOT / "environment_files"
ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
           GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
_END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")

SEEDS = 20
BUDGET = 250
if "--seeds" in sys.argv:
    i = sys.argv.index("--seeds"); SEEDS = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
if "--budget" in sys.argv:
    i = sys.argv.index("--budget"); BUDGET = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
GAMES = sys.argv[1:] or ["ls20", "cd82", "sp80", "re86", "tu93", "wa30",
                         "ar25", "g50t", "sk48", "cn04", "ka59"]

_POLICIES = ["random", "v1", "goal"]


def load(game):
    inst = next((ENV_DIR / game).iterdir())
    spec = importlib.util.spec_from_file_location("wp_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
                if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def play(cls, policy, seed, budget):
    """Return (won, max_levels)."""
    g = cls()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    raw = list(getattr(g, "_available_actions", [1, 2, 3, 4, 5]))
    mo = [ACTIONS[a - 1] for a in raw if a != 6]      # movement only
    n = len(mo)
    rng = random.Random(seed)
    if policy == "random":
        agent = None
    elif policy == "v1":
        agent = GeneralAgent(n, seed=seed)
    else:
        agent = GoalSeekAgent(n, seed=seed, goal_mode="near")
    won, maxlvl = False, 0
    for _ in range(budget):
        if obs is None or str(obs.state) in _END or not obs.frame:
            break
        full = np.asarray(obs.frame[-1])
        a = rng.randrange(n) if agent is None else agent.choose(full) % n
        obs = g.perform_action(ActionInput(id=mo[a]), raw=True)
        if obs is not None:
            maxlvl = max(maxlvl, obs.levels_completed or 0)
            if obs.levels_completed and obs.levels_completed > 0:
                won = True
                break
    return won, maxlvl


def main():
    print(f"FLAKY-WIN POOL (canonical stand-in)  seeds={SEEDS} budget={BUDGET}\n")
    print(f"{'game':6s} | " + " | ".join(f"{p:>10s}" for p in _POLICIES))
    print("-" * 44)
    totals = {p: 0.0 for p in _POLICIES}
    ngames = 0
    for game in GAMES:
        try:
            cls = load(game)
        except Exception as e:
            print(f"{game:6s} | load-error {e}"); continue
        ngames += 1
        cells = []
        for p in _POLICIES:
            wins = sum(play(cls, p, s, BUDGET)[0] for s in range(SEEDS))
            wr = wins / SEEDS
            totals[p] += wr
            cells.append(f"{wins:2d}/{SEEDS} {wr*100:3.0f}%")
        print(f"{game:6s} | " + " | ".join(f"{c:>10s}" for c in cells))
    print("-" * 44)
    print(f"{'MEAN':6s} | " + " | ".join(
        f"{totals[p]/max(1,ngames)*100:9.1f}%" for p in _POLICIES))
    print("\nRead: a column with wins concentrated in the SAME 1-2 games across")
    print("seeds = a stable floor; wins scattered/low = pure noise. Either way the")
    print("pool is small -> the leaderboard total is a few flaky wins + variance.")


if __name__ == "__main__":
    main()
