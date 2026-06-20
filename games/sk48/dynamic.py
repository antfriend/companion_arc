"""
games/sk48/dynamic.py — sk48 as a Dynamic (ARC-RFC-0001 §3).

sk48 = snake/sokoban hybrid: a horizontal snake (colour-6 head box at game-x=11 +
colour-1/2 body segments) pushes coloured blocks so the first segments spell a target
sequence shown in a bottom HUD. ACTION1/2 = slide UP/DOWN along a colour-3 rail;
ACTION3 = retract (push blocks left); ACTION4 = extend (push blocks right). See
games/sk48/detector.py (frame reader) and games/sk48/bfs_solver.py (forward model).

PLAN-ONCE + ABORTABLE REPLAY (like ls20/wa30/re86): the block layout and goal order
are READ off the pixels at level start (detector.read_state), a winning action path is
planned once by BFS over the exact push model (bfs_solver.solve), then replayed one
action at a time. Each step carries a "board changed" expectation, so a blocked/no-op
move diverges and the supervisor aborts back to the explorer floor. Because the route
is frame-derived (not the old hardcoded 14-step replay), it re-plans per instance.

recognize() gates on read_state succeeding — a colour-6 6×6 head box anchored at
x=11, a tall 2-col colour-3 rail, real 4×4 blocks, and a 3-colour HUD goal. That
structural signature is far off the hidden-decoy distribution (_test_falsefire.py).
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.sk48 import detector as D
from games.sk48 import bfs_solver as B

# Action indices into the movement-action list (ACTION1..4 → 0..3): slide/retract/extend.
_IDX = {"U": 0, "D": 1, "L": 2, "R": 3}


def _expect_changed(cur):
    b = np.asarray(cur).tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Sk48Dynamic(Dynamic):
    id = "sk48"

    def reset(self) -> None:
        self._plan = None       # planned action path (['U','R',...]); [] = planned, no win
        self._i = 0

    def _plan_from(self, f):
        st = D.read_state(f)
        if st is None:
            return None
        row, ncols, blocks, win = st
        return B.solve(row, ncols, dict(blocks), win)

    def recognize(self, frame) -> float:
        # Structural gate only (cheap, precise) — the BFS plan is deferred to
        # next_action so dispatch stays fast across all games.
        return 1.0 if D.read_state(np.asarray(frame)) is not None else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        if self._plan is None:                  # plan once, at level start
            self._plan = self._plan_from(f) or []
            self._i = 0
        if self._i >= len(self._plan):
            return None                          # route exhausted (or unsolvable) → floor
        a = self._plan[self._i]
        self._i += 1
        return SolverStep(_IDX[a] % n_actions, _expect_changed(f),
                          f"sk48 {a} {self._i}/{len(self._plan)}")
