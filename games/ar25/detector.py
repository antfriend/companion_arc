"""
games/ar25/detector.py — Adaptive L1 solver for ar25 (reflection puzzle).

Mechanics (L1):
  - One moveable piece "0007arvfmhagbj" (shape [[5,5,5],[-1,-1,5],[-1,-1,5]], 5 pixels)
  - Vertical mirror "0055nwhypaamix" at game x=10 → reflects pixels as: reflected_x = 20 - pixel_x
  - 5 target markers (color 11) at (17,15),(18,15),(19,15),(17,16),(17,17)
  - WIN: piece reflections cover all 5 markers
  - Solution: place piece at (1,15) → reflections land exactly on all 5 markers

Frame layout (64×64, scale=3, game=21×21):
  - game (gx,gy) → frame col=gx*3, row=gy*3 (top-left aligned)
  - Letterbox color=5 at frame row 63 and col 63 (game padding)
  - Piece color=5 in interior rows 0-62, cols 0-62

Route: LEFT×(piece_x−1) + DOWN×(15−piece_y)  →  16 total steps for L1 win
  (15 moves + 1 extra action from framework to trigger level transition)
"""

from dataclasses import dataclass

import numpy as np


SCALE = 3
GAME_W = 21
GAME_H = 21
PIECE_COLOR = 5
PIECE_TARGET_X = 1
PIECE_TARGET_Y = 15

# Action indices into the available_actions list (order: ACTION1-4 + ACTION5 + ACTION7)
IDX_UP = 0    # ACTION1
IDX_DOWN = 1  # ACTION2
IDX_LEFT = 2  # ACTION3
IDX_RIGHT = 3 # ACTION4


@dataclass
class GameState:
    piece_x: int
    piece_y: int


def detect_state(grid: np.ndarray) -> GameState:
    """Find piece position from 64×64 frame."""
    game_area = grid[:GAME_H * SCALE, :GAME_W * SCALE]
    positions = np.argwhere(game_area == PIECE_COLOR)
    if len(positions) == 0:
        # Fallback to known level-1 start position
        return GameState(piece_x=6, piece_y=5)
    min_row = int(positions[:, 0].min())
    min_col = int(positions[:, 1].min())
    return GameState(piece_x=min_col // SCALE, piece_y=min_row // SCALE)


def compute_route(state: GameState, level_num: int = 1) -> list[int]:
    """Return action-index list to move piece to (1,15) and win L1."""
    if level_num != 1:
        return []
    dx = state.piece_x - PIECE_TARGET_X   # steps LEFT needed
    dy = PIECE_TARGET_Y - state.piece_y   # steps DOWN needed
    if dx < 0 or dy < 0:
        return []
    return [IDX_LEFT] * dx + [IDX_DOWN] * dy
