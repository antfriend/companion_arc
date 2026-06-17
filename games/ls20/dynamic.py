"""
games/ls20/dynamic.py — ls20 as a Dynamic (ARC-RFC-0001 §3).

ls20 is ONE "transform-and-deliver" mechanic at every level: a block carries (shape,
color, rotation); changer tiles cycle each; rings reset a move-timer; a target admits the
block only when all three attrs match; WIN = deliver to every target matching. Levels are
just configurations (L1 = +1 rotation visit; L2 = +3 + 2 ring resets), so ONE frame-driven
solver (games/ls20/solver.py) clears them — superseding the old per-level fixed routes.

Per level: read the spec from the frame, plan transform-and-deliver with timer-aware ring
interleaving, then emit the plan one action at a time. Abortable: each step expects the
frame to change (every planned move moves the block or flips a tile); ABORT_K consecutive
no-ops latch back to the explorer floor. If the frame can't be read or planned (e.g. a
target needs a shape/colour change not yet decoded, L3+), defer to the floor (return None).

Recognition: ls20's SMALL color-12 block (≤50 px) — excludes sp80 where color-12 is the
~3500-px background.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.ls20 import solver as S


def _expect_changed(cur):
    b = np.asarray(cur).tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Ls20Dynamic(Dynamic):
    id = "ls20"

    def reset(self) -> None:
        self._route = None
        self._planned = False
        self._i = 0

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: a SMALL color-12 block (≤50 px) — excludes sp80 where
        # color-12 is the background (~3500 px).
        f = np.asarray(frame)
        n12 = int(np.count_nonzero(f == S.BLOCK))
        return 1.0 if 0 < n12 <= 50 else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        if not self._planned:                      # plan once per level, from the frame
            self._planned = True
            spec = S.read_spec(f, getattr(self, "_level", 1))
            self._route = S.plan(spec) if spec is not None else None
            self._i = 0
        if not self._route or self._i >= len(self._route):
            return None                            # nothing to drive → defer to the floor
        a = int(self._route[self._i])              # solver is 1-indexed (1=UP..4=RIGHT)
        self._i += 1
        return SolverStep((a - 1) % n_actions, _expect_changed(f), f"ls20[{self._i - 1}]={a}")
