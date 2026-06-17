"""Instrument ls20 L2: drive the level-aware solver and log the observable state.

ls20 L2 is the known open problem (timers/rings/oscillation). Before building a
closed-loop solver we OBSERVE the mechanics empirically: play to L1 completion,
switch to L2, then log per step — levels_completed, block_pos, entity1_state,
ring notch orientation, and whether the frame changed — to see how far the
existing L2 route gets and exactly where it desyncs.
"""
import importlib.util
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.solve_agent import SupervisedAgent
from games.ls20.dynamic import Ls20Dynamic
from games.ls20 import detector as L

ACT = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
       GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
ENV = Path(__file__).parent / "environment_files"
_NAMES = {0: "UP", 1: "DOWN", 2: "LEFT", 3: "RIGHT", 4: "ACT5"}


def load(game="ls20"):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("pl_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def _snap(frame):
    st = L.detect_state(frame)
    notch = st.entity2_notch_orientation
    ring = st.entity2_ring
    rtag = f"r{ring['top']}-{ring['bot']}c{ring['left']}-{ring['right']}" if ring else "none"
    return f"block={st.block_pos} ent1={st.entity1_state} notch={notch} ring={rtag}"


def main():
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    g = load()()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    raw = list(getattr(g, "_available_actions", [1, 2, 3, 4, 5]))
    mo = [ACT[a - 1] for a in raw if a != 6]; n = len(mo)
    # Drive the ls20 dynamic alone (single-dynamic supervisor) for clean attribution.
    agent = SupervisedAgent(n, seed=0, dynamics=[Ls20Dynamic()])
    prev_levels = 0
    l2_steps = 0
    print(f"n_actions={n}\n--- L1 (brief) ---")
    for step in range(budget):
        if obs is None or str(obs.state) in END or not obs.frame:
            print(f"[end] state={str(obs.state) if obs else None} levels={prev_levels} l2_steps={l2_steps}")
            break
        full = np.asarray(obs.frame[-1])
        prev_bytes = full.tobytes()
        a = agent.choose(full) % n
        obs = g.perform_action(ActionInput(id=mo[a]), raw=True)
        lvl = obs.levels_completed if obs else prev_levels
        if lvl > prev_levels:
            prev_levels = lvl
            agent.reset_level(level=prev_levels + 1)   # tell solver it's on the next level
            print(f"\n*** LEVEL {prev_levels} COMPLETE at step {step} → now on L{prev_levels+1} ***")
            print("--- L2 trace (action | changed | state) ---")
        if prev_levels >= 1:
            l2_steps += 1
            nf = np.asarray(obs.frame[-1]) if (obs and obs.frame) else None
            changed = "chg" if (nf is not None and nf.tobytes() != prev_bytes) else "NOOP"
            if l2_steps <= 80:
                print(f"  L2[{l2_steps:3d}] {_NAMES.get(a,a):5s} {changed:4s} | "
                      f"{_snap(nf) if nf is not None else 'no-frame'}")
    print(f"\nSUMMARY: max level={prev_levels}, L2 steps taken={l2_steps}")


if __name__ == "__main__":
    main()
