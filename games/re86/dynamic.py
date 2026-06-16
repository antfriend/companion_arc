"""
games/re86/dynamic.py — re86 as a Dynamic (ARC-RFC-0001 §3, fifth port).

re86 = piece-placement-match-target. Two cross pieces (color-9, color-11) must be
moved onto their target markers. The ACTIVE piece is marked by a single color-0
center pixel; ACTION5 cycles which piece is active; ACTION1-4 move it 3px.

Does NOT re-derive per frame: a piece placed on its target OCCLUDES the same-color
target markers, so mid-solve detect_state loses the target and bails. So re86
PLANS ONCE (the detector's adaptive route, computed while all markers are visible)
and replays it one action at a time, each guarded by a "board changed" expectation
→ abort on a no-op. Same shape as wa30.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.re86 import detector as R


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Re86Dynamic(Dynamic):
    id = "re86"

    def reset(self) -> None:
        self._route = None
        self._i = 0

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: re86's detect_state succeeds only with EXACTLY one
        # color-0 active-center pixel whose neighbor is a piece color (9/11), both
        # pieces carrying valid target markers, and a big inactive cluster. ka59
        # also has 1 color-0 pixel but no color-9 piece → not detected.
        return 1.0 if R.detect_state(np.asarray(frame)).detected else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        if self._route is None:                    # plan once, all markers visible
            st = R.detect_state(f)
            if not st.detected:
                return None
            self._route = R.compute_route(st, 1)
            self._i = 0
        if self._i >= len(self._route):
            return None
        a = int(self._route[self._i])
        self._i += 1
        return SolverStep(a, _expect_changed(f), f"re86[{self._i - 1}]={a}")
