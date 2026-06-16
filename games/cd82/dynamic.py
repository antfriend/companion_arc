"""
games/cd82/dynamic.py — cd82 as a Dynamic (ARC-RFC-0001 §3, second port).

cd82 = basket-selection-route. A pixel-2 "ActiveBasket" selector sits on one of 8
baskets arranged on a ring around a 3×3 nav grid (center (1,1) forbidden).
ACTION1-4 move the selector by one grid cell; ACTION5 fires, painting the canvas.
L1 win: fire from basket 4 at grid (2,1).

Re-derivation: each frame, detect WHICH basket the selector is on (pixel-2
bbox-min → known basket position), then emit ONE step toward (2,1) avoiding the
center, or FIRE when there. Self-correcting (re-detects every step), so a blocked
move just re-plans next frame; the directional expectation (the selector must
move to a new grid cell) aborts if a move is a no-op.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep

# pixel-2 bbox-min (r,c) → 3×3 nav-grid (row,col). Canonical basket positions.
_BASKET_BY_FRAME_POS = {
    (24, 25): (0, 1), (21, 33): (0, 2), (32, 38): (1, 2), (40, 33): (2, 2),
    (45, 25): (2, 1), (40, 14): (2, 0), (32, 17): (1, 0), (21, 14): (0, 0),
}
# minimal center-avoiding path from each grid cell to basket 4 (2,1).
# actions: 0=row-1, 1=row+1, 2=col-1, 3=col+1
_NAV_TO_B4 = {
    (0, 0): [1, 1, 3], (0, 1): [3, 1, 1, 2], (0, 2): [1, 1, 2], (1, 0): [1, 3],
    (1, 2): [1, 2], (2, 0): [3], (2, 1): [], (2, 2): [2],
}
_TARGET = (2, 1)
FIRE = 4
_TOL = 16          # squared-px tolerance for matching a basket position


def _active_basket(frame):
    """3×3 nav-grid (row,col) of the pixel-2 selector, or None."""
    p = np.argwhere(frame == 2)
    if len(p) == 0:
        return None
    r1, c1 = int(p[:, 0].min()), int(p[:, 1].min())
    best_d, best = float("inf"), None
    for (kr, kc), g in _BASKET_BY_FRAME_POS.items():
        d = (r1 - kr) ** 2 + (c1 - kc) ** 2
        if d < best_d:
            best_d, best = d, g
    return best if best_d <= _TOL else None


def _expect_basket_moved(cur):
    """Predicate: the selector moved to a different grid cell (not a no-op)."""
    p0 = _active_basket(np.asarray(cur))
    return lambda f: _active_basket(np.asarray(f)) not in (None, p0)


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Cd82Dynamic(Dynamic):
    id = "cd82"

    def reset(self) -> None:
        self._fired = False

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: a pixel-2 selector whose bbox-min sits on a known
        # basket ring position. Unique to cd82 on the practice set (tu93/wa30/
        # sk48/ka59 also have pixel-2 but never at a basket position).
        return 1.0 if _active_basket(np.asarray(frame)) is not None else 0.0

    def next_action(self, frame, n_actions):
        frame = np.asarray(frame)
        pos = _active_basket(frame)
        if pos is None:
            return None
        if pos == _TARGET:
            if self._fired:
                return None                      # already fired → hand back to explorer
            self._fired = True
            return SolverStep(FIRE, _expect_changed(frame), "fire@(2,1)")
        nav = _NAV_TO_B4.get(pos)
        if not nav:
            return None
        return SolverStep(nav[0], _expect_basket_moved(frame), f"nav {pos}->{_TARGET}")
