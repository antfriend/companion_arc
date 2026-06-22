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
_PIECE_MIN = 20            # a real selected piece is substantial (real sp80: ~80px pixel-9),
                           # NOT a stray pixel — the size floor kills hidden false fires
_OBSTACLE = 11
_OBSTACLE_MIN = 40         # the spill obstacle is a real cluster (real sp80: ~160px color-11)
_ANCHOR_TO_PIECE = (-1, -9)   # (dx, dy) game-coords: piece offset from obstacle bbox-min
_SPILL_ROUTE = [4, 3, 3, 3, 4, 2, 2, 1]
UP, DOWN, LEFT, RIGHT, SPILL = 0, 1, 2, 3, 4

# --- L2+ (multi-piece deflector) -----------------------------------------------
# L1 is a single deflector. From L2 on, the level seeds MULTIPLE movable pieces
# (color-8 unselected / color-9 selected) that must be arranged into a staircase
# of deflectors so the single rising spill splits to wet EVERY color-11 target.
# A single spill must cover all targets at once (coverage resets between failed
# spills), so the final arrangement is what matters — NOT the path to it.
#
# Found by searching the real (deterministic) engine: the winning L2 board places
# the 5-wide piece and the two (interchangeable) 3-wide pieces at fixed slots,
# expressed as game-cell (row, col) of the piece TOP-LEFT relative to the color-11
# target-cluster anchor (bbox top-left). The solver is CLOSED-LOOP: it re-detects
# the pieces every frame, click-selects an unplaced one, walks it toward its slot,
# and spills once all are seated — so it is robust to the selected piece's
# history-dependent L2 start cell (which varies with how L1 was won).
_PIECE_BLOB_MIN = 3            # a movable piece is >=3 game cells (kills liquid/noise)
_L2_LARGE_MIN = 5             # the 5-wide deflector; smaller blobs are the 3-wide ones
_L2_SLOTS_LARGE = [(10, 3)]                 # (drow, dcol) from target anchor
_L2_SLOTS_SMALL = [(5, 2), (7, 6)]          # two interchangeable 3-wide slots


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


def _blobs_of(frame, color):
    """4-connected components (>= _PIECE_BLOB_MIN game cells) of one color."""
    pts = np.argwhere(frame == color)
    if len(pts) == 0:
        return []
    cells = {(int(r) // _CELL, int(c) // _CELL) for r, c in pts}
    seen = set()
    out = []
    for start in list(cells):
        if start in seen:
            continue
        stack = [start]
        comp = []
        while stack:
            cur = stack.pop()
            if cur in seen or cur not in cells:
                continue
            seen.add(cur)
            comp.append(cur)
            r, c = cur
            stack += [(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)]
        if len(comp) >= _PIECE_BLOB_MIN:
            rs = [p[0] for p in comp]
            cs = [p[1] for p in comp]
            out.append((min(rs), min(cs), max(cs) - min(cs) + 1))
    return out


def _pieces(frame):
    """Movable pieces as dicts {top, left, w, sel}. The SELECTED piece is color-9
    (taken as ONE piece); unselected pieces are color-8 components. Detecting the
    two colours separately keeps a moving (selected) piece from being merged with
    an adjacent stationary one by 4-connectivity."""
    out = []
    sel = _blobs_of(frame, _SELECTED)
    if sel:                                   # the selected piece spans all color-9 cells
        rs = [b[0] for b in sel]
        tops = min(rs)
        lefts = min(b[1] for b in sel)
        right = max(b[1] + b[2] - 1 for b in sel)
        out.append({"top": tops, "left": lefts, "w": right - lefts + 1, "sel": True})
    for top, left, w in _blobs_of(frame, 8):
        out.append({"top": top, "left": left, "w": w, "sel": False})
    return out


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
        self._l2 = False             # latched once the multi-piece arranger engages

    def recognize(self, frame) -> float:
        # PRECISION-first fingerprint (calibrated on the §6.1 confusion matrix AND the
        # hidden-decoy fuzzer _test_falsefire.py):
        #   (1) 4px-block render structure — excludes ls20/re86/ar25 (pitch ≠ 4),
        #       palette-independent so hidden recolorings still match. NOTE this is
        #       NECESSARY-but-weak: a mostly-uniform hidden frame also passes it;
        #   (2) a SUBSTANTIAL selected piece (≥20px pixel-9, or ≥20px pixel-8) that is
        #       NOT the background — excludes ar25 (pixel-9 is its background);
        #   (3) a SUBSTANTIAL color-11 obstacle cluster (≥40px) that is NOT the background.
        # The size floors (2)+(3) are the fuzzer fix: "uniform + a stray 9 + a stray 11"
        # fired on 8.85% of hidden-like decoys; real sp80 carries ~80px-9 + ~160px-11.
        frame = np.asarray(frame)
        if _block_uniform_frac(frame) < 0.85:
            return 0.0
        vals, counts = np.unique(frame, return_counts=True)
        bg = int(vals[int(np.argmax(counts))])
        has_piece = ((np.count_nonzero(frame == _SELECTED) >= _PIECE_MIN and _SELECTED != bg)
                     or (np.count_nonzero(frame == 8) >= _PIECE8_MIN and 8 != bg))
        has_obstacle = np.count_nonzero(frame == _OBSTACLE) >= _OBSTACLE_MIN and _OBSTACLE != bg
        return 1.0 if (has_piece and has_obstacle) else 0.0

    def next_action(self, frame, n_actions):
        frame = np.asarray(frame)
        anchor = _obstacle_anchor(frame)

        # Phase L2+ — multi-piece deflector arrangement, anchored to the color-11
        # target cluster. Engaged once we see >1 movable piece; the single-deflector
        # L1 logic below handles the 1-piece case. Closed-loop: re-derive each frame.
        if anchor is not None and (self._l2 or len(_pieces(frame)) > 1):
            self._l2 = True
            return self._arrange(frame, anchor)

        piece = _piece_game(frame)
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

    def _arrange(self, frame, anchor):
        """Closed-loop multi-piece deflector arranger: drive each piece to its
        slot (relative to the color-11 target anchor), then spill once seated.

        Slots are filled BOTTOM-UP (largest target row first) and each piece moves
        VERTICALLY before horizontally, so a piece reaches its target row — clearing
        the rows above — before any piece is walked sideways into a shared row. This
        keeps two pieces from ever overlapping mid-move (which would hide one piece
        and make the arranger spill prematurely)."""
        ax, ay = anchor                       # anchor = (game_x=col, game_y=row)
        # slot kinds: 'L' wants the 5-wide piece, 'S' the (interchangeable) 3-wide.
        slots = [(ay + dr, ax + dc, "L") for dr, dc in _L2_SLOTS_LARGE]
        slots += [(ay + dr, ax + dc, "S") for dr, dc in _L2_SLOTS_SMALL]
        slots.sort(key=lambda s: -s[0])       # bottom-up

        pieces = _pieces(frame)
        used = [False] * len(pieces)
        plan = []                             # (slot_row, slot_col, piece_index)
        for sr, sc, kind in slots:
            cands = [i for i, p in enumerate(pieces) if not used[i]
                     and (p["w"] >= _L2_LARGE_MIN) == (kind == "L")]
            if not cands:
                continue
            i = min(cands, key=lambda i: abs(pieces[i]["top"] - sr)
                    + abs(pieces[i]["left"] - sc))
            used[i] = True
            plan.append((sr, sc, i))

        # The active task is the first (bottom-up) slot whose piece isn't seated.
        task = next(((sr, sc, i) for sr, sc, i in plan
                     if (pieces[i]["top"], pieces[i]["left"]) != (sr, sc)), None)
        if task is None:                      # all seated → fire the spill
            return SolverStep(SPILL, _expect_changed(frame), "l2-spill")

        sr, sc, i = task
        p = pieces[i]
        if not p["sel"]:                      # select it first (click its centroid)
            x = (p["left"] + p["w"] // 2) * _CELL + 1
            y = p["top"] * _CELL + 1
            return SolverStep(0, _expect_changed(frame),
                              f"l2-select({x},{y})", click=(x, y))
        if p["top"] != sr:                    # vertical first
            d = DOWN if sr > p["top"] else UP
            return SolverStep(d, _expect_changed(frame), f"l2-move y->{sr}")
        d = RIGHT if sc > p["left"] else LEFT
        return SolverStep(d, _expect_changed(frame), f"l2-move x->{sc}")
