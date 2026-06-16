"""
games/sp80/dynamic.py — sp80 as a Dynamic (ARC-RFC-0001 §3, first port).

sp80 = liquid-spill-covers-obstacles. The selected piece (frame pixel 9, or a
>=20px pixel-8 before auto-select) must reach a spill position expressed RELATIVE
to the color-11 obstacle cluster, then a short spill choreography wets every
obstacle.

This re-derives the NAVIGATION every frame from the current piece/obstacle
positions (self-correcting, translation-invariant — the upgrade over
detector.compute_route()'s precomputed list), and emits ONE action at a time with
a directional EXPECTATION so the supervisor can abort if the piece doesn't move
as commanded (a wall, or a hidden variant where the mapping differs). The spill
sub-sequence is the canonical choreography but is likewise abortable: each spill
action must change the board or the supervisor bails.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep

_CELL = 4
_SELECTED = 9
_PIECE8_MIN = 20            # a >=20px pixel-8 blob is the moveable piece pre-select
_OBSTACLE = 11
_ANCHOR_TO_PIECE = (-1, -9)   # (dx, dy) game-coords: piece offset from obstacle bbox-min
_SPILL_ROUTE = [4, 3, 3, 3, 4, 2, 2, 1]
UP, DOWN, LEFT, RIGHT, SPILL = 0, 1, 2, 3, 4


def _piece_game(frame):
    """(game_x, game_y) of the selected piece, or None."""
    pos = np.argwhere(frame == _SELECTED)
    if len(pos) == 0:
        p8 = np.argwhere(frame == 8)
        if len(p8) >= _PIECE8_MIN:
            pos = p8
    if len(pos) == 0:
        return None
    return (int(pos[:, 1].min()) // _CELL, int(pos[:, 0].min()) // _CELL)


def _obstacle_anchor(frame):
    """(game_x, game_y) of the color-11 obstacle bbox-min, or None."""
    p = np.argwhere(frame == _OBSTACLE)
    if len(p) == 0:
        return None
    return (int(p[:, 1].min()) // _CELL, int(p[:, 0].min()) // _CELL)


def _block_uniform_frac(frame, c=_CELL):
    """Fraction of c×c blocks that are single-valued. sp80 renders a 16×16
    logical grid at 4px, so this is ~0.94; games at other pitches are <0.8.
    Palette-INDEPENDENT (structure, not color) → robust to hidden recoloring."""
    h, w = frame.shape
    if h % c or w % c:
        return 0.0
    b = frame.reshape(h // c, c, w // c, c)
    return float((b == b[:, :1, :, :1]).all(axis=(1, 3)).mean())


def _expect_moved(cur, axis, sign):
    """Predicate: the piece moved along `axis` (0=x,1=y) in `sign` direction."""
    p0 = _piece_game(cur)

    def ok(f):
        p1 = _piece_game(np.asarray(f))
        return p0 is not None and p1 is not None and (p1[axis] - p0[axis]) * sign > 0
    return ok


def _expect_changed(cur):
    """Predicate: the board changed (the action was not a no-op)."""
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Sp80Dynamic(Dynamic):
    id = "sp80"

    def reset(self) -> None:
        self._spill_i = -1            # -1 = still navigating; >=0 = spill index

    def recognize(self, frame) -> float:
        # PRECISION-first fingerprint (calibrated on the §6.1 confusion matrix):
        #   (1) 4px-block render structure — excludes ls20/re86/ar25 (pitch ≠ 4),
        #       palette-independent so hidden recolorings still match;
        #   (2) a compact selected piece (pixel-9, or ≥20px pixel-8) that is NOT
        #       the background — excludes ar25 (pixel-9 is its background);
        #   (3) a color-11 obstacle cluster that is NOT the background.
        frame = np.asarray(frame)
        if _block_uniform_frac(frame) < 0.85:
            return 0.0
        vals, counts = np.unique(frame, return_counts=True)
        bg = int(vals[int(np.argmax(counts))])
        has_piece = ((np.count_nonzero(frame == _SELECTED) > 0 and _SELECTED != bg)
                     or (np.count_nonzero(frame == 8) >= _PIECE8_MIN and 8 != bg))
        has_obstacle = np.count_nonzero(frame == _OBSTACLE) > 0 and _OBSTACLE != bg
        return 1.0 if (has_piece and has_obstacle) else 0.0

    def next_action(self, frame, n_actions):
        frame = np.asarray(frame)
        piece = _piece_game(frame)
        anchor = _obstacle_anchor(frame)
        if piece is None or anchor is None:
            return None                       # can't solve now → defer to explorer
        gx, gy = piece
        tx, ty = anchor[0] + _ANCHOR_TO_PIECE[0], anchor[1] + _ANCHOR_TO_PIECE[1]

        # Phase A — navigation, re-derived from the CURRENT piece position.
        if self._spill_i < 0:
            dx, dy = tx - gx, ty - gy
            if dx > 0:
                return SolverStep(RIGHT, _expect_moved(frame, 0, +1), "nav→R")
            if dx < 0:
                return SolverStep(LEFT, _expect_moved(frame, 0, -1), "nav→L")
            if dy > 0:
                return SolverStep(DOWN, _expect_moved(frame, 1, +1), "nav→D")
            if dy < 0:
                return SolverStep(UP, _expect_moved(frame, 1, -1), "nav→U")
            self._spill_i = 0                 # arrived at spill-1 position

        # Phase B — spill choreography, abortable (each action must change board).
        if 0 <= self._spill_i < len(_SPILL_ROUTE):
            a = _SPILL_ROUTE[self._spill_i]
            self._spill_i += 1
            return SolverStep(a, _expect_changed(frame), f"spill[{self._spill_i-1}]={a}")

        return None                           # choreography done → hand back to explorer
