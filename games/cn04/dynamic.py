"""
games/cn04/dynamic.py — cn04 as a Dynamic (ARC-RFC-0001 §3, seventh port).

cn04 = connector-rotate-translate-match. The selected sprite (body color-0, two
color-8 connector markers) must be rotated/translated so its markers overlap a
target piece's two markers. The detector enumerates rotation × marker-assignment
and chains the (≤2) geometrically-consistent candidates (the win fires mid-route
on the correct one) — all frame-derived.

Plan-once + abortable replay: the candidate chaining is a committed sequence and
matched markers occlude, so it does not re-derive cleanly per frame. Recognition
requires a SOLVABLE 2-marker/2-target configuration (a strong structure gate).
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.cn04 import detector as C


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Cn04Dynamic(Dynamic):
    id = "cn04"

    def reset(self) -> None:
        self._route = None
        self._i = 0

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: a selected sprite (color-0 body) with EXACTLY two
        # color-8 connector markers, a target with two markers, and a solvable
        # rotate+translate placement for this frame.
        st = C.detect_state(np.asarray(frame))
        if st.sel_pos is None or st.sel_size is None:
            return 0.0
        if len(st.sel_marks) != 2 or len(st.tgt_marks) != 2:
            return 0.0
        return 1.0 if C.compute_route(st, 1) else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        if self._route is None:
            st = C.detect_state(f)
            self._route = C.compute_route(st, 1)
            self._i = 0
        if not self._route or self._i >= len(self._route):
            return None
        a = int(self._route[self._i])
        self._i += 1
        return SolverStep(a, _expect_changed(f), f"cn04[{self._i - 1}]={a}")
