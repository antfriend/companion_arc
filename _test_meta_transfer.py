"""Does cross-game action knowledge transfer within one rerun? (dream @LAT30LON55)

Controlled experiment, NOT a leaderboard proxy. The hidden-set SCORE can't be
validated locally (one-sided proxy, @LAT82LON55), but the meta-explorer's core
MECHANISM can: when the same explorer carries its action-id prior across a
sequence of games, do the LATER games start better than from a cold reset?

  warm : ONE MetaExplorer for the whole game sequence (prior accumulates)
  cold : a FRESH MetaExplorer per game (prior never carries over)

Same seed and same game order for both, so the only difference is carryover.
We randomize the order across runs and measure, on the LATER HALF of each
sequence (where warm has a prior and cold doesn't), the no-op rate in the FIRST
50 steps of each game — the warm-start window. Lower warm = transfer is real.

Usage: python _test_meta_transfer.py [--orders N] [--seeds N] [--budget N]
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

from core.meta_agent import MetaExplorer
from core.general_agent import board_signature

ROOT = Path(__file__).parent
ENV_DIR = ROOT / "environment_files"
ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
           GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
_END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")

ORDERS = 5
SEEDS = 3
BUDGET = 400
WARM_WINDOW = 50
for flag, name in (("--orders", "ORDERS"), ("--seeds", "SEEDS"), ("--budget", "BUDGET")):
    if flag in sys.argv:
        i = sys.argv.index(flag); globals()[name] = int(sys.argv[i + 1]); del sys.argv[i:i + 2]

GAMES = sys.argv[1:] or ["ls20", "cd82", "sp80", "re86", "tu93", "wa30",
                         "ar25", "g50t", "sk48", "cn04", "ka59"]


def load(game):
    inst = next((ENV_DIR / game).iterdir())
    spec = importlib.util.spec_from_file_location("mt_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
                if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


CLASSES = {}
for g in GAMES:
    try:
        CLASSES[g] = load(g)
    except Exception as e:
        print(f"{g} load-error {e}")


def play(cls, agent, budget):
    """Play one game with an already-configured MetaExplorer. Returns
    (noop_first_window, steps_first_window, noop_all, steps_all, won)."""
    g = cls()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    avail = [a for a in list(getattr(g, "_available_actions", [1, 2, 3, 4, 5])) if a != 6]
    agent.new_game(avail)
    obj = {a: ACTIONS[a - 1] for a in avail}
    won = False
    prev_sig = None
    nf = sf = na = sa = 0
    for step in range(budget):
        if obs is None or str(obs.state) in _END or not obs.frame:
            break
        frame = np.asarray(obs.frame[-1])
        sig = board_signature(frame)
        if prev_sig is not None:
            noop = 1 if sig == prev_sig else 0
            na += noop; sa += 1
            if step <= WARM_WINDOW:
                nf += noop; sf += 1
        prev_sig = sig
        aid = agent.choose(frame)
        obs = g.perform_action(ActionInput(id=obj.get(aid, ACTIONS[avail[0] - 1])), raw=True)
        if obs is not None and obs.levels_completed > 0:
            won = True
            agent.level_completed()
            prev_sig = None
    return nf, sf, na, sa, won


def run():
    print(f"META transfer  warm vs cold   orders={ORDERS} seeds={SEEDS} "
          f"budget={BUDGET} warm-window={WARM_WINDOW}\n")
    names = [g for g in GAMES if g in CLASSES]
    half = len(names) // 2
    # accumulators for LATER-half positions
    warm_nf = warm_sf = cold_nf = cold_sf = 0
    warm_wins = cold_wins = 0
    early_warm_nf = early_warm_sf = early_cold_nf = early_cold_sf = 0
    for o in range(ORDERS):
        for s in range(SEEDS):
            order = names[:]
            random.Random(o * 100 + s).shuffle(order)
            warm_agent = MetaExplorer(seed=s)
            for pos, game in enumerate(order):
                cls = CLASSES[game]
                nf, sf, na, sa, won = play(cls, warm_agent, BUDGET)
                cold_agent = MetaExplorer(seed=s)
                cnf, csf, cna, csa, cwon = play(cls, cold_agent, BUDGET)
                later = pos >= half
                if later:
                    warm_nf += nf; warm_sf += sf; cold_nf += cnf; cold_sf += csf
                    warm_wins += int(won); cold_wins += int(cwon)
                else:
                    early_warm_nf += nf; early_warm_sf += sf
                    early_cold_nf += cnf; early_cold_sf += csf

    def rate(n, d):
        return 100.0 * n / d if d else 0.0

    print("First-%d-step no-op rate (lower = better warm-start):" % WARM_WINDOW)
    print(f"  EARLY-half positions : warm {rate(early_warm_nf, early_warm_sf):5.1f}%   "
          f"cold {rate(early_cold_nf, early_cold_sf):5.1f}%   "
          f"(both ~cold here; warm has little prior yet)")
    wl = rate(warm_nf, warm_sf); cl = rate(cold_nf, cold_sf)
    print(f"  LATER-half positions : warm {wl:5.1f}%   cold {cl:5.1f}%   "
          f"delta {cl - wl:+.1f}pp")
    print()
    if cl - wl > 0.5:
        print(f"--> TRANSFER CONFIRMED: warm starts later games {cl - wl:.1f}pp fewer "
              f"no-ops than cold. Cross-game action prior carries real information.")
    elif wl - cl > 0.5:
        print(f"--> NEGATIVE: warm is WORSE by {wl - cl:.1f}pp — the prior misleads. "
              f"Do not pursue meta-explorer.")
    else:
        print("--> NULL: no measurable transfer. Action-id semantics may not be "
              "consistent enough across these games.")
    print(f"\nLater-half wins: warm={warm_wins}  cold={cold_wins} "
          f"(of {ORDERS*SEEDS*(len(names)-half)} game-plays)")


if __name__ == "__main__":
    run()
