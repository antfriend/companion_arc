"""
games/ar25/dynamic.py — ar25 as a Dynamic (ARC-RFC-0001 §3, sixth port).

ar25 = reflection-covers-markers. A color-5 piece moves; its reflection through a
color-10 vertical mirror must cover 5 color-11 markers. The detector solves the
target placement from the constraint {reflect(piece)} == {markers} (frame-derived,
translation-robust).

Re-derives per frame: detect piece/markers/mirror, solve the target placement,
emit ONE move toward it. Piece (color-5) and markers (color-11) never occlude each
other, so re-derivation stays valid throughout. Recognition requires the placement
to be SOLVABLE — a strong, structure-specific gate.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.ar25 import detector as A


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Ar25Dynamic(Dynamic):
    id = "ar25"

    def reset(self) -> None:
        pass                                       # fully re-derived each frame

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: piece(5) + markers(11) + mirror(10) all present
        # AND the reflection placement is actually solvable for THIS frame.
        st = A.detect_state(np.asarray(frame))
        if st.piece_x < 0:
            return 0.0
        return 1.0 if A._solve_placement(st) is not None else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        st = A.detect_state(f)
        if st.piece_x < 0:
            return None
        route = A.compute_route(st, 1)
        if not route:
            return None                            # placed or unsolvable → defer
        a = int(route[0])
        return SolverStep(a, _expect_changed(f), f"ar25 move {a}")
