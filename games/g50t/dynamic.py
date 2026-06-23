"""
games/g50t/dynamic.py — g50t as a Dynamic (ARC-RFC-0001 §3, sixth port).

g50t = record-replay-ghost-holds-door. A goal cursor records a path to a button
(ACTION5 submits); a ghost replays it holding the button open while the goal,
reset to start, navigates to the win tracker. Inherently SEQUENTIAL + stateful
(record stage → submit → replay stage), so plan-once + abortable replay (the
detector's adaptive multi-stage route, frame-derived). The "board changed"
expectation is lenient enough to tolerate the replay animation; it only aborts on
a true no-op.

L2 (2026-06-23): a TWO-GHOST / TWO-DOOR / THREE-STAGE variant. Two buttons each
gate a door; both must be held at once, and there are 3 recording stages (verified
from source): record ghost1→button-A (opens door-A, exposing button-B), submit;
record ghost2→button-B (opens door-B to the tracker room), submit; then in the
THIRD stage both ghosts replay IN SYNC with the player's moves — ghost1 reaches
button-A after 2 player moves, ghost2 reaches button-B after 12 — so the player
must spend ≥12 real moves (a no-op/wall-bump does NOT advance the ghosts) before
the door-B crossing. The winning route is a fixed sequence of RELATIVE moves
(U/D/L/R/SUBMIT), hence translation-invariant like the L1 route. L1 vs L2 is read
from the frame: L1 has ONE merged color-8 region (button welded to door), L2 has
TWO color-8 door regions. See games/g50t/companion.md.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.g50t import detector as G

# L2 winning route, RELATIVE moves as simple-action indices
# (0=UP/ACTION1, 1=DOWN, 2=LEFT, 3=RIGHT, 4=SUBMIT/ACTION5). Verified end-to-end on
# the real engine (level_index 1→2). Stage0: L,L→button-A, submit. Stage1:
# D×4,L×4,U×2,L×2→button-B, submit. Stage2 (both ghosts replaying): U×3,L×7,D×2 to
# crawl the perimeter (≥12 moves so ghost2 seats button-B), then R,R,R through both
# open doors into the tracker cell.
_L2_ROUTE = [2, 2, 4,
             1, 1, 1, 1, 2, 2, 2, 2, 0, 0, 2, 2, 4,
             0, 0, 0, 2, 2, 2, 2, 2, 2, 2, 1, 1, 3, 3, 3]


def _door_components(frame):
    """Count color-8 connected components of >=9px (8-connectivity). L1 → 1 (the
    button welded to the single door); L2 → 2 (two separate doors)."""
    g = np.asarray(frame)
    eight = (g == 8)
    h, w = eight.shape
    seen = np.zeros_like(eight, dtype=bool)
    n = 0
    for r in range(h):
        for c in range(w):
            if eight[r, c] and not seen[r, c]:
                stack = [(r, c)]; size = 0
                while stack:
                    y, x = stack.pop()
                    if y < 0 or x < 0 or y >= h or x >= w or seen[y, x] or not eight[y, x]:
                        continue
                    seen[y, x] = True; size += 1
                    stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1),
                              (y + 1, x + 1), (y - 1, x - 1), (y + 1, x - 1), (y - 1, x + 1)]
                if size >= 9:
                    n += 1
    return n


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
        # PRECISION fingerprint: goal (color-5 ringed by 9) + tracker (color-9
        # ringed by 5), plus the g50t door signature in color-8. re86 has colors
        # 5/9 but no color-8 → excluded.
        #   L2: goal + tracker + exactly TWO color-8 door regions (the 2-door
        #       variant) — no isolated button needed (buttons render welded/hidden).
        #   L1: goal + tracker + a 3×3 color-8 button (robust finder), 1 door.
        st = _detect(frame)
        if st.goal and st.tracker and _door_components(frame) == 2:
            return 1.0
        return 1.0 if (st.goal and st.button and st.tracker) else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        if self._route is None:
            # L2 (two doors) → the fixed two-ghost route; else the L1 detector route.
            st = _detect(f)
            if st.goal and st.tracker and _door_components(f) == 2:
                self._route = list(_L2_ROUTE)
            else:
                self._route = G.compute_route(_detect(f), 1)
            self._i = 0
        if not self._route or self._i >= len(self._route):
            return None
        a = int(self._route[self._i])
        self._i += 1
        return SolverStep(a, _expect_changed(f), f"g50t[{self._i - 1}]={a}")
