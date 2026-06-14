"""Does ACTION6 (click) support let the explorer solve click-games?

Compares three policies on the click-capable canonical games:
  moves      : uniform random over simple moves only (current baseline — blind to clicks)
  rnd+click  : uniform random over moves + foreground-click candidates
  explorer   : ClickExplorer (count-based novelty over moves + clicks)

Metric that matters: win-rate (fraction of seeds completing >=1 level) and
mean steps-to-first-win. The headline test is cn04 — solvable only WITH clicks.

Usage: python _test_click.py [--seeds N] [--budget N] [game ...]
"""
import importlib.util
import io
import random
import statistics
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.click_agent import ClickExplorer, _foreground_components
from core.general_agent import board_signature

ROOT = Path(__file__).parent
ENV_DIR = ROOT / "environment_files"
ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
           GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
_END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")

SEEDS = 8
BUDGET = 600
if "--seeds" in sys.argv:
    i = sys.argv.index("--seeds"); SEEDS = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
if "--budget" in sys.argv:
    i = sys.argv.index("--budget"); BUDGET = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
# default: the click-capable canonical games
GAMES = sys.argv[1:] or ["cd82", "sp80", "ar25", "sk48", "cn04", "ka59"]


def load(game):
    inst = next((ENV_DIR / game).iterdir())
    spec = importlib.util.spec_from_file_location("clk_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
                if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def to_action_input(spec, move_objs):
    kind = spec[0]
    if kind == "m":
        return ActionInput(id=move_objs[spec[1]])
    return ActionInput(id=GameAction.ACTION6, data={"x": spec[1], "y": spec[2]})


def play(cls, policy, seed, budget):
    g = cls()
    rng = random.Random(seed)
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    avail = list(getattr(g, "_available_actions", [1, 2, 3, 4, 5]))
    has_click = 6 in avail
    move_ids = [a for a in avail if a != 6]
    move_objs = [ACTIONS[a - 1] for a in move_ids]
    n = len(move_objs)

    agent = None
    if policy == "explorer":
        agent = ClickExplorer(n, allow_click=has_click, seed=seed)

    levels = 0
    first_win = None
    steps = 0
    for _ in range(budget):
        if obs is None or str(obs.state) in _END or not obs.frame:
            break
        frame = np.asarray(obs.frame[-1])
        if policy == "explorer":
            spec = agent.choose(frame)
        else:
            cands = [("m", i) for i in range(n)]
            if policy == "rnd+click" and has_click:
                cands += [("c", gx, gy) for gx, gy in _foreground_components(frame)]
            spec = rng.choice(cands)
        obs = g.perform_action(to_action_input(spec, move_objs), raw=True)
        steps += 1
        if obs is not None and obs.levels_completed > levels:
            levels = obs.levels_completed
            if first_win is None:
                first_win = steps
            if agent is not None:
                agent.reset_level()
    return levels, first_win


def summarize(cls, policy):
    wins, fw = 0, []
    for s in range(SEEDS):
        lv, f = play(cls, policy, s, BUDGET)
        if f is not None:
            wins += 1; fw.append(f)
    return wins / SEEDS, (statistics.mean(fw) if fw else None)


def main():
    print(f"CLICK test  moves vs rnd+click vs explorer   seeds={SEEDS} budget={BUDGET}\n")
    hdr = f"{'game':6s} | {'win%  m / r+c / exp':>22s} | {'first-win m / r+c / exp':>26s}"
    print(hdr); print("-" * len(hdr))
    tot = {"moves": 0.0, "rnd+click": 0.0, "explorer": 0.0}
    for game in GAMES:
        try:
            cls = load(game)
        except Exception as e:
            print(f"{game:6s} load-error {e}"); continue
        r = {}
        for p in ("moves", "rnd+click", "explorer"):
            r[p] = summarize(cls, p)
            tot[p] += r[p][0]
        fw = lambda v: f"{v:.0f}" if v is not None else "-"
        print(f"{game:6s} | "
              f"{r['moves'][0]*100:5.0f}/{r['rnd+click'][0]*100:5.0f}/{r['explorer'][0]*100:<5.0f} | "
              f"{fw(r['moves'][1]):>6s}/{fw(r['rnd+click'][1]):>6s}/{fw(r['explorer'][1]):<6s}")
    G = len(GAMES)
    print("-" * len(hdr))
    print(f"{'TOTAL':6s} | "
          f"{tot['moves']/G*100:5.0f}/{tot['rnd+click']/G*100:5.0f}/{tot['explorer']/G*100:<5.0f} |")
    print(f"\nwin-rate: moves={tot['moves']/G*100:.0f}%  "
          f"rnd+click={tot['rnd+click']/G*100:.0f}%  explorer={tot['explorer']/G*100:.0f}%")
    print("(moves = current baseline, blind to clicks. Higher r+c/explorer = clicks unlock wins.)")


if __name__ == "__main__":
    main()
