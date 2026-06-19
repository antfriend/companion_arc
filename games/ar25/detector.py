"""
games/ar25/detector.py — Adaptive L1 solver for ar25 (reflection puzzle).

Mechanics (L1):
  - One moveable 5-pixel piece (color 5)
  - Vertical mirror (color-10 line at game x=M) reflects pixels: x' = 2*M - x
  - 5 target markers (color 11)
  - WIN: piece reflections cover all 5 markers

Everything is derived from the frame — piece shape, marker set, and mirror
column — because the competition rerun plays hidden layout variants. The win
placement is solved from the constraint {reflect(piece pixels)} == {markers},
not assumed.

Frame layout (64×64, scale=3, game=21×21):
  - game (gx,gy) → frame col=gx*3, row=gy*3 (top-left aligned)
  - Letterbox color=5 at frame row/col 63 — game area is [:63, :63]
"""

from dataclasses import dataclass, field

import numpy as np


SCALE = 3
GAME_W = 21
GAME_H = 21
PIECE_COLOR = 5
MARKER_COLOR = 11
MIRROR_COLOR = 10

IDX_UP = 0    # ACTION1
IDX_DOWN = 1  # ACTION2
IDX_LEFT = 2  # ACTION3
IDX_RIGHT = 3 # ACTION4


@dataclass
class GameState:
    piece_x: int = -1
    piece_y: int = -1
    piece_shape: frozenset = frozenset()    # pixel offsets from piece TL
    markers: frozenset = frozenset()        # marker game cells
    mirror_x: int = -1


def _cells(game_area: np.ndarray, color: int) -> set:
    pos = np.argwhere(game_area == color)
    return {(int(c) // SCALE, int(r) // SCALE) for r, c in pos}


def detect_state(grid: np.ndarray) -> GameState:
    game_area = np.asarray(grid)[:GAME_H * SCALE, :GAME_W * SCALE]

    piece = _cells(game_area, PIECE_COLOR)
    markers = _cells(game_area, MARKER_COLOR)
    mirror = _cells(game_area, MIRROR_COLOR)
    if not piece or not markers or not mirror:
        return GameState()

    px = min(x for x, _ in piece)
    py = min(y for _, y in piece)
    shape = frozenset((x - px, y - py) for x, y in piece)

    # Mirror: dominant column of the color-10 cells
    xs = [x for x, _ in mirror]
    mirror_x = max(set(xs), key=xs.count)

    return GameState(piece_x=px, piece_y=py, piece_shape=shape,
                     markers=frozenset(markers), mirror_x=mirror_x)


def _solve_placement(state: GameState) -> tuple | None:
    """Find (px, py) where the piece's reflection covers all markers.

    reflect(px+ox) = 2*M - (px+ox). Anchor any marker to any piece pixel to
    get a candidate, then verify the full set matches.
    """
    M = state.mirror_x
    shape = sorted(state.piece_shape)
    markers = state.markers
    for mx, my in markers:
        for ox, oy in shape:
            px = 2 * M - mx - ox
            py = my - oy
            if px < 0 or py < 0 or px > GAME_W - 1 or py > GAME_H - 1:
                continue
            reflected = {(2 * M - (px + sx), py + sy) for sx, sy in shape}
            if reflected == markers:
                return (px, py)
    return None


def solve_placement_2d(state: GameState, mmin: int = 0, mmax: int = GAME_W - 1) -> tuple | None:
    """Level-general placement: find (mirror_x, px, py) such that the piece's
    reflection covers all markers AND the placement is reachable.

    L2+ makes the mirror moveable (selectable via ACTION5), so the solution space
    is (mirror_x, piece_x, piece_y), not just piece position. Geometry: a vertical
    mirror at M reflects (x,y)→(2M−x, y), so reflection-x of pixel sx is (2M−px−sx)
    = (q − sx) where q := 2M − px is a SINGLE free parameter. Thus q (and py) fully
    determine whether the reflected set equals the markers, INDEPENDENT of how q
    splits into (M, px). So: solve q,py from the marker/shape match, then pick any
    reachable (M, px) with 2M−px=q (piece fits in-bounds, mirror in range).

    Prefers M == the CURRENT mirror_x (piece-only, == the L1 mechanic) so L1 — where
    the mirror is fixed/unselectable — is solved without ever moving the mirror.
    Returns (mirror_x, px, py) or None (defer to the floor)."""
    shape = sorted(state.piece_shape)
    markers = set(state.markers)
    if not shape or not markers or len(markers) != len(shape):
        return None
    max_sx = max(sx for sx, _ in shape)
    max_sy = max(sy for _, sy in shape)

    # q, py: reflect(piece)=={(q−sx, py+sy)} must equal the marker set.
    qpy = None
    for mx0, my0 in markers:
        for sx0, sy0 in shape:
            q = mx0 + sx0
            py = my0 - sy0
            if py < 0 or py + max_sy > GAME_H - 1:
                continue
            if {(q - sx, py + sy) for sx, sy in shape} == markers:
                qpy = (q, py)
                break
        if qpy:
            break
    if qpy is None:
        return None
    q, py = qpy

    # reachable (M, px) with 2M−px=q; prefer the current mirror (no mirror move = L1).
    for M in sorted(range(mmin, mmax + 1), key=lambda m: abs(m - state.mirror_x)):
        px = 2 * M - q
        if 0 <= px and px + max_sx <= GAME_W - 1:
            return (M, px, py)
    return None


def compute_route(state: GameState, level_num: int = 1) -> list:
    if level_num != 1 or state.piece_x < 0:
        return []
    target = _solve_placement(state)
    if target is None:
        return []
    dx = target[0] - state.piece_x
    dy = target[1] - state.piece_y
    route = ([IDX_RIGHT] * dx if dx > 0 else [IDX_LEFT] * (-dx))
    route += ([IDX_DOWN] * dy if dy > 0 else [IDX_UP] * (-dy))
    return route
