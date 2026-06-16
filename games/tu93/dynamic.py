"""
games/tu93/dynamic.py — tu93 as a Dynamic (ARC-RFC-0001 §3, third port).

tu93 = corridor-BFS-navigation. A 3×3 cursor sprite (color-4 marker + color-9
body) navigates color-2 corridors of a maze to a 3×3 color-14 exit.

Re-derivation: each frame, run the detector's adaptive BFS (origin derived from
the frame, so translation-independent) from the current cursor cell to the exit,
and emit ONE move. Self-correcting — re-BFS every step, so a blocked/missed move
just re-plans; the directional expectation (cursor marker must shift in the
commanded direction) aborts if a move is a no-op.

Reuses games/tu93/detector.py (detect_state + _bfs) — the adaptive logic is
already frame-derived; this wraps it in the abortable, one-step-at-a-time
Dynamic protocol.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.tu93 import detector as D


def _cursor_pos(frame):
    p = np.argwhere(np.asarray(frame) == D.CURSOR_COLOR)
    return (int(p[:, 0].min()), int(p[:, 1].min())) if len(p) else None


def _expect_moved(cur, action):
    """Predicate: the cursor marker shifted in the commanded direction."""
    p0 = _cursor_pos(cur)
    dr, dc = D._DELTAS.get(action, (0, 0))

    def ok(f):
        p1 = _cursor_pos(f)
        if p0 is None or p1 is None:
            return False
        return (p1[0] - p0[0]) * dr > 0 or (p1[1] - p0[1]) * dc > 0
    return ok


class Tu93Dynamic(Dynamic):
    id = "tu93"

    def reset(self) -> None:
        pass                                   # fully re-derived each frame

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: small fixed 3×3 cursor (color-4 marker + color-9
        # body) AND a small 3×3 color-14 exit AND substantial color-2 corridor.
        # The size caps exclude sk48 (color-4 count ~1384, a major element); the
        # corridor floor excludes cd82 (color-2 selector ~30, no maze).
        f = np.asarray(frame)
        p4 = np.count_nonzero(f == D.CURSOR_COLOR)
        p9 = np.count_nonzero(f == D.CURSOR_BODY)
        p14 = np.count_nonzero(f == D.TARGET_COLOR)
        p2 = np.count_nonzero(f == D.CORRIDOR_COLOR)
        has_cursor = 0 < p4 <= 16 and 0 < p9 <= 16
        has_target = 0 < p14 <= 16
        has_corridor = p2 > 50
        return 1.0 if (has_cursor and has_target and has_corridor) else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        state = D.detect_state(f)
        if state.cursor_cell is None or state.target_cell is None or not state.route:
            return None                        # no cursor/target/path → defer
        a = int(state.route[0])
        return SolverStep(a, _expect_moved(f, a), f"bfs step {a}")
