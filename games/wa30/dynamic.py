"""
games/wa30/dynamic.py — wa30 as a Dynamic (ARC-RFC-0001 §3, fourth port).

wa30 = pick-up-and-deliver. A 4×4 cursor (color-0 direction edge + color-14 body)
picks up color-4 items and carries them to a color-2 drop zone (ACTION5 =
pickup/drop). Multi-phase (approach → face → pickup → carry → drop), so unlike
the navigation dynamics it does NOT re-derive cleanly per frame — once an item is
being carried it still reads as a loose color-4, which would confuse a fresh BFS.

So wa30 PLANS ONCE per level (the detector's adaptive multi-item BFS route, which
is itself frame-derived and translation-robust) and replays it one action at a
time, each guarded by a "the board changed" expectation. If a step is a no-op the
plan has desynced from reality and the supervisor aborts back to the explorer —
the same downside cap as the re-derivation dynamics, just with a coarser check.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.wa30 import detector as W


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Wa30Dynamic(Dynamic):
    id = "wa30"

    def reset(self) -> None:
        self._route = None
        self._i = 0

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: small color-0 cursor edge + small color-2 drop
        # zone + color-14 body (count caps exclude cd82's large color-0 and sk48's
        # large color-2), AND the detector finds both items and a drop zone.
        f = np.asarray(frame)
        p0 = np.count_nonzero(f == 0)
        p2 = np.count_nonzero(f == 2)
        p14 = np.count_nonzero(f == 14)
        if not (0 < p0 <= 40 and 0 < p2 <= 40 and 0 < p14 <= 40):
            return 0.0
        st = W.detect_state(f)
        if not st or not st.get("items") or not st.get("dz_valid"):
            return 0.0
        return 1.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        if self._route is None:                 # plan once, on the first frame
            st = W.detect_state(f)
            if not st:
                return None
            self._route = W.compute_route(st, 1)
            self._i = 0
        if self._i >= len(self._route):
            return None                          # route exhausted → hand back to explorer
        a = int(self._route[self._i])
        self._i += 1
        return SolverStep(a, _expect_changed(f), f"wa30[{self._i - 1}]={a}")
