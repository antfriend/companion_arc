"""
games/re86/dynamic.py — re86 as a Dynamic (ARC-RFC-0001 §3, fifth port).

re86 = piece-placement-match-target. N pieces of arbitrary shape/colour (cross,
saltire, diamond) must each be moved onto their target markers. The ACTIVE piece
is marked by a single colour-0 centre pixel; ACTION5 cycles which piece is active;
ACTION1-4 move it 3px (UP/DOWN/LEFT/RIGHT). Win = every target marker is covered
by its piece (games/re86/detector.py jeiavrvavi / win footprint).

CLOSED-LOOP, level-agnostic (clears L1 AND L2; L3 stacks two same-colour pieces,
out of scope → defers there). Target markers are captured once at level start
(before any piece occludes a target); each frame we then re-derive the ACTIVE
piece's pixel set and the 3px displacement that lands its markers — emit one move
toward it, or CYCLE to the next piece once the active one is on target. Every step
carries a "board changed" expectation so a blocked move aborts to the floor.

Generalises the old 2-cross/colour-9+11 detector (which made L2 recognise()=0.0):
detector.detect_pieces bridges the colour-0 centre hole via connectivity and reads
markers shape-agnostically; detector.required_disp aligns any shape to its markers.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.re86 import detector as R

UP, DOWN, LEFT, RIGHT, CYCLE = 0, 1, 2, 3, 4


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Re86Dynamic(Dynamic):
    id = "re86"

    def reset(self) -> None:
        self._marks = None          # {color: [marker (r,c), ...]} captured at level start

    def _capture(self, f):
        pieces = R.detect_pieces(f)
        self._marks = {p["color"]: (p["marks"] or []) for p in pieces}

    def recognize(self, frame) -> float:
        # PRECISION gate: a unique colour-0 active centre inside a real piece blob,
        # every piece colour carries small target markers, and the active piece's
        # markers are FULLY coverable by a 3px placement of its own shape. This
        # structural+solvability gate is strong enough to stay off hidden decoys.
        f = np.asarray(frame)
        color, pix = R.active_piece(f)
        if color is None:
            return 0.0
        pieces = R.detect_pieces(f)
        if not pieces or any(not p["marks"] for p in pieces):
            return 0.0
        marks = next((p["marks"] for p in pieces if p["color"] == color), None)
        if not marks:
            return 0.0
        _D, full = R.required_disp(pix, marks)
        return 1.0 if full else 0.0

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        if self._marks is None:                 # capture targets once, at level start
            self._capture(f)
        color, pix = R.active_piece(f)
        if color is None or color not in self._marks:
            return None
        marks = self._marks[color]
        D, _full = R.required_disp(pix, marks)   # best-effort each frame; recognize()
        if D is None:                            # already gated full coverage of a fresh piece
            return None
        if D == (0, 0):
            return SolverStep(CYCLE, _expect_changed(f), "cycle→next piece")
        if abs(D[0]) >= abs(D[1]) and D[0] != 0:
            a = DOWN if D[0] > 0 else UP
        else:
            a = RIGHT if D[1] > 0 else LEFT
        return SolverStep(a, _expect_changed(f), f"place c{color} D={D} a={a}")
