"""Probe: can we detect monotone in-grid scalars (dream spark @LAT38LON53)?

The HUD we learned to MASK may be a dense REWARD we can READ. A progress bar
filling, items accumulating, or a budget depleting all show up generically as a
COLOR whose cell-count trends monotonically over the trajectory — no per-game
code, just count cells per color each step and measure directional consistency.

Metric per color c with count series x_0..x_T:
  net   = x_T - x_0                      (total change)
  act   = sum |x_{t+1}-x_t|              (total activity; ignore near-static colors)
  mono  = net / act   in [-1, +1]        (+1 = perfectly monotone RISING,
                                          -1 = perfectly monotone FALLING,
                                           0 = noisy / oscillating)

A |mono| near 1 with meaningful |net| is a clean monotone scalar. Sign tells us
reward (rising) vs budget (falling). This part only DETECTS; the reward-shaped
agent (part 2) is built only if clean signals exist.

Usage: python _test_scalar_detect.py [--seeds N] [--budget N] [game ...]
"""
import importlib.util
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.general_agent_dyn import GeneralAgentDyn
from core.dyn_signature import _core

ROOT = Path(__file__).parent
ENV_DIR = ROOT / "environment_files"
ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
           GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
_END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")

SEEDS = 3
BUDGET = 300
MIN_ACT = 4        # ignore colors with less total activity than this
CLEAN_MONO = 0.6   # |mono| >= this counts as a clean monotone scalar
MIN_NET = 4        # ...with at least this much net change
if "--seeds" in sys.argv:
    i = sys.argv.index("--seeds"); SEEDS = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
if "--budget" in sys.argv:
    i = sys.argv.index("--budget"); BUDGET = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
GAMES = sys.argv[1:] or ["ls20", "cd82", "sp80", "re86", "tu93", "wa30",
                         "ar25", "g50t", "sk48", "cn04", "ka59"]


def load(game):
    inst = next((ENV_DIR / game).iterdir())
    spec = importlib.util.spec_from_file_location("sc_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
                if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def trajectory(cls, seed, budget):
    g = cls()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    avail = [a for a in list(getattr(g, "_available_actions", [1, 2, 3, 4, 5])) if a != 6]
    mo = [ACTIONS[a - 1] for a in avail]
    n = len(mo)
    ag = GeneralAgentDyn(n, seed=seed)
    series = []
    for _ in range(budget):
        if obs is None or str(obs.state) in _END or not obs.frame:
            break
        full = np.asarray(obs.frame[-1])
        core = _core(full)
        vals, counts = np.unique(core, return_counts=True)
        series.append(dict(zip(vals.tolist(), counts.tolist())))
        a = ag.choose(full) % n
        obs = g.perform_action(ActionInput(id=mo[a]), raw=True)
    return series


def analyze(series):
    if len(series) < 5:
        return []
    colors = set().union(*[set(s.keys()) for s in series])
    out = []
    for c in colors:
        x = np.array([s.get(c, 0) for s in series], dtype=float)
        d = np.diff(x)
        act = float(np.abs(d).sum())
        if act < MIN_ACT:
            continue
        net = float(x[-1] - x[0])
        mono = net / (act + 1e-9)
        out.append((c, net, mono, act))
    out.sort(key=lambda t: -abs(t[2]) * abs(t[1]))
    return out


def main():
    print(f"SCALAR DETECT  seeds={SEEDS} budget={BUDGET}  "
          f"(clean = |mono|>={CLEAN_MONO} & |net|>={MIN_NET})\n")
    print(f"{'game':6s} | {'top monotone color (net, mono, dir)':42s} | clean?")
    print("-" * 70)
    n_clean = 0
    for game in GAMES:
        try:
            cls = load(game)
        except Exception as e:
            print(f"{game:6s} load-error {e}"); continue
        # aggregate the strongest candidate across seeds
        best = None
        for s in range(SEEDS):
            cands = analyze(trajectory(cls, s, BUDGET))
            if cands:
                top = cands[0]
                if best is None or abs(top[2]) * abs(top[1]) > abs(best[2]) * abs(best[1]):
                    best = top
        if best is None:
            print(f"{game:6s} | {'(no active colors)':42s} | -")
            continue
        c, net, mono, act = best
        direction = "RISING" if net > 0 else "FALLING"
        clean = abs(mono) >= CLEAN_MONO and abs(net) >= MIN_NET
        n_clean += int(clean)
        desc = f"color {int(c):2d}: net={net:+6.0f} mono={mono:+.2f} {direction}"
        print(f"{game:6s} | {desc:42s} | {'YES' if clean else 'no'}")
    print("-" * 70)
    print(f"\n{n_clean}/{len(GAMES)} games have a CLEAN monotone scalar.")
    print("RISING = candidate dense reward (bias toward increasing).")
    print("FALLING = candidate budget/timer (do not force depletion).")


if __name__ == "__main__":
    main()
