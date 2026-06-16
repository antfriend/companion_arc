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


def _find_button(g):
    """Robust button finder: the most ISOLATED 3×3 solid color-8 block.

    The detector's _find_button needs the button as a separate connected cluster,
    but on this instance the 3×3 button is joined to the door's color-8 region by
    a 1px bar → it returns None. Instead, scan every 3×3 all-color-8 window and
    pick the one with the FEWEST color-8 neighbours in its surrounding ring (a
    protrusion button has ~1 neighbour via its bar; the door's 3×3 sub-blocks are
    embedded with many). Returns (min_row, min_col) of the button, or None.
    """
    eight = (np.asarray(g) == 8)
    h, w = eight.shape
    best, best_ring = None, None
    for r in range(h - 2):
        for c in range(w - 2):
            if eight[r:r + 3, c:c + 3].all():
                r0, r1 = max(0, r - 1), min(h, r + 4)
                c0, c1 = max(0, c - 1), min(w, c + 4)
                ring = int(eight[r0:r1, c0:c1].sum()) - 9      # 5×5 minus the 3×3
                if best is None or ring < best_ring:
                    best, best_ring = (r, c), ring
    return best


def _detect(frame):
    """detect_state, with the button backfilled by the robust finder when the
    detector's connectivity-based one misses it."""
    f = np.asarray(frame)
    st = G.detect_state(f)
    if st.button is None:
        b = _find_button(f)
        if b is not None:
            st.button = (b[1] - 2, b[0] - 2)       # detector's (x, y) convention
    return st


class G50tDynamic(Dynamic):
    id = "g50t"

    def reset(self) -> None:
        self._route = None
        self._i = 0

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: goal (color-5 ringed by 9), tracker (color-9
        # ringed by 5), and a 3×3 color-8 button (robust finder). re86 has colors
        # 5/9 but no color-8 → no button → excluded.
        st = _detect(frame)
        return 1.0 if (st.goal and st.button and st.tracker) else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        if self._route is None:
            self._route = G.compute_route(_detect(f), 1)
            self._i = 0
        if not self._route or self._i >= len(self._route):
            return None
        a = int(self._route[self._i])
        self._i += 1
        return SolverStep(a, _expect_changed(f), f"g50t[{self._i - 1}]={a}")
