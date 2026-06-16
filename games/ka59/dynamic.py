"""
games/ka59/dynamic.py — ka59 as a Dynamic (ARC-RFC-0001 §3, candidate port).

ka59 = push-and-contain. The selected container (color-14 border, color-0 center)
must be navigated so its 3×3 lands at (target.row+1, target.col+1) inside a 5×5
color-4 target. Navigation-style → re-derive per frame (detect selected, BFS to
the nearest reachable target slot, emit one move). The container nests INSIDE the
target so it does not occlude the target border → re-derivation stays valid.

Known limit (memory): only ~1/6 of levels are winnable without click-select
(ACTION6) to switch containers — the de-risk gate decides whether this instance's
L1 is solvable by the directly-movable container.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.ka59 import detector as K


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Ka59Dynamic(Dynamic):
    id = "ka59"

    def reset(self) -> None:
        pass

    def recognize(self, frame) -> float:
        st = K.detect_state(np.asarray(frame))
        if st.selected is None or not st.targets:
            return 0.0
        return 1.0 if K.compute_route(st, 1) else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        st = K.detect_state(f)
        if st.selected is None or not st.targets:
            return None
        route = K.compute_route(st, 1)
        if not route:
            return None
        a = int(route[0])
        return SolverStep(a, _expect_changed(f), f"ka59 move {a}")
