"""How far past L1 does each current dynamic get?  (ls20 pilot, step 0)

The de-risk harness stops at the first level. But the score rewards higher levels
(RHAE weights them more), and a hidden L1 may use an L2-flavoured mechanic. This
plays each game MULTI-LEVEL with the full solver library, resetting the agent on
each level transition (so the dynamic re-plans), and reports the max level reached.

Re-derivation dynamics (level-agnostic, e.g. tu93's per-frame BFS) may clear L2+
for free; plan-once dynamics (ls20/wa30/re86/cn04/g50t — fixed L1 route) should
stall at L1, flagging where closed-loop / level-aware work is needed.

Usage: python _test_multilevel.py [--budget N] [game ...]
"""
import importlib.util
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.solve_agent import SupervisedAgent
from core.click_agent import spec_to_action_input
from core.dynamics import library  # noqa: F401 — registers the dynamics

ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
           GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
ENV = Path(__file__).parent / "environment_files"
GAMES = ["ls20", "sp80", "tu93", "cd82", "re86", "wa30", "ar25", "cn04", "g50t", "sk48"]

BUDGET = 600
if "--budget" in sys.argv:
    i = sys.argv.index("--budget"); BUDGET = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
if len(sys.argv) > 1:
    GAMES = sys.argv[1:]


def load(game):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("ml_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def play(cls, seed=0):
    """Return (max_level_completed, end_state, steps)."""
    g = cls()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    raw = list(getattr(g, "_available_actions", [1, 2, 3, 4, 5]))
    mo = [ACTIONS[a - 1] for a in raw if a != 6]; n = len(mo)
    agent = SupervisedAgent(n, seed=seed)          # default v1 floor + full library
    prev_levels = 0
    steps = 0
    for _ in range(BUDGET):
        if obs is None or str(obs.state) in END or not obs.frame:
            break
        full = np.asarray(obs.frame[-1])
        agent.choose(full)                         # sets agent.spec (move or click)
        obs = g.perform_action(spec_to_action_input(agent.spec, mo), raw=True)
        steps += 1
        if obs is not None and (obs.levels_completed or 0) > prev_levels:
            prev_levels = obs.levels_completed
            agent.reset_level()                    # re-plan the dynamic for the new level
    state = str(obs.state) if obs is not None else "None"
    return prev_levels, state, steps


def main():
    print(f"MULTI-LEVEL REACH (full solver library, v1 floor)  budget={BUDGET}\n")
    print(f"{'game':6s} | {'max level':>9s} | {'end state':>22s} | steps")
    print("-" * 56)
    for game in GAMES:
        try:
            cls = load(game)
        except Exception as e:
            print(f"{game:6s} | load-error {e}"); continue
        lvl, state, steps = play(cls)
        print(f"{game:6s} | {lvl:9d} | {state:>22s} | {steps}")
    print("-" * 56)
    print("max level 0 = didn't clear L1; ≥2 = solver advanced past L1 (free score / "
          "level-agnostic re-derivation). L1-only stalls flag closed-loop targets.")


if __name__ == "__main__":
    main()
