"""
games/ls20/dynamic.py — ls20 as a Dynamic (ARC-RFC-0001 §3, eighth port).

ls20 = block-navigation-through-corridor. A color-12 block (cursor) must navigate
fixed maze corridors to the goal. The detector's L1 route is column-adaptive
(normalize to the clear x=34 corridor, ascend, trigger the rotation changer,
ascend to goal) — frame-derived from the block's start position.

Choreography through fixed corridors → plan-once + abortable replay. The canonical
flow takes a probe action (initial_action) before the route proper, so this emits
that probe first, then plans from the post-probe frame (mirrors practice_offline).

Recognition must distinguish ls20's SMALL color-12 block from sp80's color-12
BACKGROUND — gated on a small color-12 count.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.ls20 import detector as L


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Ls20Dynamic(Dynamic):
    id = "ls20"

    def reset(self) -> None:
        self._probed = False
        self._route = None
        self._i = 0

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: a SMALL color-12 block (≤50 px) — excludes sp80
        # where color-12 is the background (~3500 px) — AND the block is detected.
        f = np.asarray(frame)
        n12 = np.count_nonzero(f == L.BLOCK)
        if not (0 < n12 <= 50):
            return 0.0
        return 1.0 if L.detect_block(f) is not None else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        lvl = getattr(self, "_level", 1)
        if not self._probed:                       # canonical probe before the route
            self._probed = True
            return SolverStep(int(L.initial_action(lvl)), lambda x: True, "probe")
        if self._route is None:                    # plan once, from the post-probe frame
            st = L.detect_state(f)
            self._route = L.compute_route(st, lvl)
            self._i = 0
        if not self._route or self._i >= len(self._route):
            return None
        a = int(self._route[self._i])
        self._i += 1
        return SolverStep(a, _expect_changed(f), f"ls20[{self._i - 1}]={a}")
