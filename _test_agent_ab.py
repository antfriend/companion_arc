"""A/B: GeneralAgent vs uniform-random, head-to-head, all local games.

Local canonical instances are NOT the scored hidden set, so absolute numbers
don't predict the leaderboard. But the RELATIVE comparison (does loss-averse
count-based exploration beat uniform random?) is a property of the agent logic
that should transfer. If general > random here, it should beat random's 0.15.

Plays each game as the competition does: one env, full step budget, count
levels completed. Averaged over SEEDS. Reports total levels completed per
policy across all games.

Usage: python _test_agent_ab.py [--seeds N] [--budget N] [game ...]
"""
import importlib.util
import io
import random
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.general_agent import GeneralAgent

ROOT = Path(__file__).parent
ENV_DIR = ROOT / "environment_files"
ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
           GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
_END_LOSE = ("GameState.GAME_OVER", "game_over")
_END_WIN = ("GameState.WIN", "win")

SEEDS = 5
BUDGET = 600
if "--seeds" in sys.argv:
    i = sys.argv.index("--seeds"); SEEDS = int(sys.argv[i+1]); del sys.argv[i:i+2]
if "--budget" in sys.argv:
    i = sys.argv.index("--budget"); BUDGET = int(sys.argv[i+1]); del sys.argv[i:i+2]
GAMES = sys.argv[1:] or ["ls20","cd82","sp80","re86","tu93","wa30","ar25","g50t","sk48","cn04","ka59"]


def load(game):
    inst = next((ENV_DIR/game).iterdir())
    spec = importlib.util.spec_from_file_location("ab_"+game, inst/f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    cls = next(v for v in vars(mod).values() if isinstance(v,type) and issubclass(v,ARCBaseGame) and v is not ARCBaseGame)
    return cls


def play(cls, policy: str, seed: int, budget: int):
    """Return (levels_completed, distinct_states, noop_fraction, steps_taken)."""
    from core.general_agent import board_signature
    g = cls()
    rng = random.Random(seed)
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    avail = [a for a in list(getattr(g, "_available_actions", [1,2,3,4,5])) if a != 6]
    act_objs = [ACTIONS[a-1] for a in avail]
    n = len(act_objs)
    agent = GeneralAgent(n, seed=seed) if policy == "general" else None
    best_levels = prev_levels = 0
    seen = set()
    noops = steps = 0
    prev_sig = None
    for step in range(budget):
        if obs is None or str(obs.state) in _END_LOSE or str(obs.state) in _END_WIN:
            break
        frame = np.asarray(obs.frame[-1]) if obs.frame else None
        if frame is None:
            break
        sig = board_signature(frame)
        seen.add(sig)
        if prev_sig is not None and sig == prev_sig:
            noops += 1
        prev_sig = sig
        a = rng.randrange(n) if policy == "random" else agent.choose(frame) % n
        obs = g.perform_action(ActionInput(id=act_objs[a]), raw=True)
        steps += 1
        if obs.levels_completed > prev_levels:
            prev_levels = best_levels = obs.levels_completed
            seen.clear(); prev_sig = None
            if agent is not None:
                agent.reset_level()
    noop_frac = noops / steps if steps else 0.0
    return best_levels, len(seen), noop_frac, steps


def avg(cls, policy):
    L = C = N = 0.0
    for s in range(SEEDS):
        lv, cov, noop, _ = play(cls, policy, s, BUDGET)
        L += lv; C += cov; N += noop
    return L/SEEDS, C/SEEDS, N/SEEDS


def main():
    print(f"A/B GeneralAgent vs random  seeds={SEEDS} budget={BUDGET}")
    print(f"{'game':6s} | {'lvls r/g':>11s} | {'coverage r/g':>15s} | {'noop% r/g':>13s}")
    tL_r=tL_g=tC_r=tC_g=tN_r=tN_g=0.0
    for game in GAMES:
        try:
            cls = load(game)
        except Exception as e:
            print(f"{game:6s} load-error {e}"); continue
        lr,cr,nr = avg(cls,"random")
        lg,cg,ng = avg(cls,"general")
        tL_r+=lr;tL_g+=lg;tC_r+=cr;tC_g+=cg;tN_r+=nr;tN_g+=ng
        win = "*" if cg>cr else " "
        print(f"{game:6s} | {lr:4.1f}/{lg:<4.1f}  | {cr:6.0f}/{cg:<6.0f} {win} | {nr*100:4.0f}/{ng*100:<4.0f}")
    G=len(GAMES)
    print(f"{'TOTAL':6s} | {tL_r:4.1f}/{tL_g:<4.1f}  | {tC_r:6.0f}/{tC_g:<6.0f}   | {tN_r/G*100:4.0f}/{tN_g/G*100:<4.0f}")
    print(f"\ncoverage gain: general/random = {tC_g/tC_r:.2f}x   (higher = more state explored)")
    print(f"noop rate:     random={tN_r/G*100:.0f}%  general={tN_g/G*100:.0f}%   (lower general = less wasted budget)")


if __name__ == "__main__":
    main()
