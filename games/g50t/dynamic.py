"""
games/g50t/dynamic.py — g50t as a Dynamic (ARC-RFC-0001 §3, sixth port).

g50t = record-replay-ghost-holds-door. A goal cursor records a path to a button
(ACTION5 submits); a ghost replays it holding the button open while the goal,
reset to start, navigates to the win tracker. Inherently SEQUENTIAL + stateful
(record stage → submit → replay stage), so plan-once + abortable replay (the
detector's adaptive multi-stage route, frame-derived). The "board changed"
expectation is lenient enough to tolerate the replay animation; it only aborts on
a true no-op.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.g50t import detector as G


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class G50tDynamic(Dynamic):
    id = "g50t"

    def reset(self) -> None:
        self._route = None
        self._i = 0

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: detector finds all three structural sprites —
        # goal (color-5 ringed by 9), tracker (color-9 ringed by 5), and an
        # isolated 3×3 color-8 button. re86 has colors 5/9 but no color-8 button.
        st = G.detect_state(np.asarray(frame))
        return 1.0 if (st.goal and st.button and st.tracker) else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        if self._route is None:
            st = G.detect_state(f)
            self._route = G.compute_route(st, 1)
            self._i = 0
        if not self._route or self._i >= len(self._route):
            return None
        a = int(self._route[self._i])
        self._i += 1
        return SolverStep(a, _expect_changed(f), f"g50t[{self._i - 1}]={a}")
