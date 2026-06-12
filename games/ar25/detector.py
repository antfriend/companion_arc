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
