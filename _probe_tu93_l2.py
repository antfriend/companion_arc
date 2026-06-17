"""Instrument tu93 L2: drive the level-aware solver and log the observable state.

tu93 L2 introduces TURRETS (color-8/12/13 sprites with a color-15 marker). A
turret activates when the cursor is aligned in the turret's facing direction at a
trigger distance (6px color-8, 12px color-13), then a projectile travels along
that axis and kills the cursor on center-overlap. The existing dynamic runs a
pure maze-BFS (turret-blind) and dies ~4 steps in. Before building a dodging
solver we OBSERVE empirically: play to L1 completion, switch to L2, and log per
step — cursor cell/pixel, exit, route head, every turret (color/pos/rotation/
active-marker), and whether the frame changed — to see exactly how/where it dies.
"""
import importlib.util
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.solve_agent import SupervisedAgent
from games.tu93.dynamic import Tu93Dynamic
from games.tu93 import detector as D

ACT = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
       GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
ENV = Path(__file__).parent / "environment_files"
_NAMES = {0: "UP", 1: "DOWN", 2: "LEFT", 3: "RIGHT"}
# Turret body colors and their color-15 "armed" marker.
TURRET_COLORS = (8, 12, 13)


def load(game="tu93"):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("pl_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def _turrets(frame):
    """List (color, top-left, has-armed-marker) for each turret body component."""
    f = np.asarray(frame)
    out = []
    for col in TURRET_COLORS:
        pos = np.argwhere(f == col)
        if not len(pos):
            continue
        # may be several turrets of one color — cluster by simple bbox split is
        # overkill here; report the merged bbox + count (instances are sparse).
        out.append((col, (int(pos[:, 0].min()), int(pos[:, 1].min())),
                    int(pos[:, 0].max()), int(pos[:, 1].max()), len(pos)))
    return out


def _snap(frame):
    f = np.asarray(frame)
    st = D.detect_state(f)
    # color-11 = active projectile marker (ziedssriec); count tells us armed turrets
    armed = int(np.count_nonzero(f == 11))
    p4 = int(np.count_nonzero(f == D.CURSOR_COLOR))
    p9 = int(np.count_nonzero(f == D.CURSOR_BODY))
    turr = " ".join(f"c{c}@{tl}+{n}px" for c, tl, _, _, n in _turrets(f))
    return (f"cur={st.cursor_pixel} cell={st.cursor_cell} tgt={st.target_cell} "
            f"route={st.route[:6]} armed11={armed} cur(p4={p4},p9={p9}) | {turr}")


def main():
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    g = load()()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    raw = list(getattr(g, "_available_actions", [1, 2, 3, 4]))
    mo = [ACT[a - 1] for a in raw if a != 6]; n = len(mo)
    agent = SupervisedAgent(n, seed=0, dynamics=[Tu93Dynamic()])
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
            agent.reset_level(level=prev_levels + 1)
            print(f"\n*** LEVEL {prev_levels} COMPLETE at step {step} → now on L{prev_levels+1} ***")
            print("--- L2 trace (action | changed | state) ---")
            if obs and obs.frame:
                print(f"  L2[  0] (start)      | {_snap(np.asarray(obs.frame[-1]))}")
        if prev_levels >= 1:
            l2_steps += 1
            nf = np.asarray(obs.frame[-1]) if (obs and obs.frame) else None
            changed = "chg" if (nf is not None and nf.tobytes() != prev_bytes) else "NOOP"
            if l2_steps <= 120:
                print(f"  L2[{l2_steps:3d}] {_NAMES.get(a,a):5s} {changed:4s} | "
                      f"{_snap(nf) if nf is not None else 'no-frame'}")
    print(f"\nSUMMARY: max level={prev_levels}, L2 steps taken={l2_steps}")


if __name__ == "__main__":
    main()
