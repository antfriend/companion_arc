"""
games/ar25/dynamic.py — ar25 as a Dynamic (ARC-RFC-0001 §3, sixth port).

ar25 = reflection-covers-markers. A color-5 piece's reflection through a color-10
vertical mirror must cover the color-11 markers. The detector solves the placement
from the constraint {reflect(piece)} == {markers} (frame-derived, translation-robust).

LEVEL-GENERAL (L1 + L2). L1: the mirror is fixed and the piece moves directly. L2:
BOTH the piece and the mirror are moveable and ACTION5 CYCLES which one is selected
(mirror↔piece); the selected entity moves with the directional actions. So a single
placement may need the mirror moved AND the piece moved, switching selection between.

We re-derive the target (mirror_x, px, py) each frame (solve_placement_2d, which
prefers the CURRENT mirror so L1 is solved piece-only — byte-identical to before),
then drive ONE entity one step toward it. The selection state isn't directly
readable, so it's LEARNED closed-loop: emit a move; if the entity we aimed at did
NOT move on the next frame (wrong entity selected, or blocked), emit ACTION5 to
cycle selection and retry. A cap on consecutive cycles latches back to the floor
(additive-safe). Recognition requires a solvable placement — a strong, structure-
specific gate.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.ar25 import detector as A

# action indices (== detector IDX_*): ACTION1..5 → 0..4
UP, DOWN, LEFT, RIGHT, CYCLE = 0, 1, 2, 3, 4


def _expect_changed(cur):
    b = np.asarray(cur).tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Ar25Dynamic(Dynamic):
    id = "ar25"
    MAX_CYCLES = 8          # consecutive selection-cycles before latching to the floor

    def reset(self) -> None:
        self._prev = None      # (mirror_x, px, py) snapshot before the last move
        self._await = None     # entity the last move aimed at ('mirror'/'piece')
        self._cycles = 0

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: piece(5) + markers(11) + mirror(10) present AND a
        # solvable (reachable) reflection placement exists for THIS frame.
        st = A.detect_state(np.asarray(frame))
        if st.piece_x < 0:
            return 0.0
        return 1.0 if A.solve_placement_2d(st) is not None else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        st = A.detect_state(f)
        if st.piece_x < 0:
            return None
        cur = (st.mirror_x, st.piece_x, st.piece_y)

        # Verify the previous move: did the entity we aimed at actually move?
        if self._await is not None and self._prev is not None:
            moved_mirror = cur[0] != self._prev[0]
            moved_piece = (cur[1], cur[2]) != (self._prev[1], self._prev[2])
            intended_moved = moved_mirror if self._await == "mirror" else moved_piece
            if intended_moved:
                self._cycles = 0
            else:
                # wrong entity selected (or blocked) → cycle selection and retry (capped).
                self._await = None
                self._cycles += 1
                if self._cycles > self.MAX_CYCLES:
                    return None                         # stuck → defer to the floor
                self._prev = None
                return SolverStep(CYCLE, _expect_changed(f), "ar25 cycle-sel")

        target = A.solve_placement_2d(st)
        if target is None:
            return None
        Mt, pxt, pyt = target

        if st.mirror_x != Mt:
            ent = "mirror"
            a = RIGHT if Mt > st.mirror_x else LEFT
        elif (st.piece_x, st.piece_y) != (pxt, pyt):
            ent = "piece"
            if st.piece_x != pxt:
                a = RIGHT if pxt > st.piece_x else LEFT
            else:
                a = DOWN if pyt > st.piece_y else UP
        else:
            return None                                 # placed → win imminent, hand back

        self._prev = cur
        self._await = ent
        return SolverStep(a % n_actions, _expect_changed(f), f"ar25 {ent} {a}")
