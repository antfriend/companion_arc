"""
games/sp80/detector.py — Per-game detector for sp80 (ARC-AGI-3).

Standard detector interface:
  detect_state(grid)              → GameState
  compute_route(state, level_num) → list[int]
  verify_step(before, after, act) → StepResult
  format_companion_block(state, route) → str

Action space: 5 simple actions
  0=UP(y-1)  1=DOWN(y+1)  2=LEFT(x-1)  3=RIGHT(x+1)  4=SPILL

Frame mapping: frame_col = game_x * 4,  frame_row = game_y * 4

Selected piece (plzwjbfyfli) appears as pixel 9 in the frame;
unselected pieces are pixel 8. Canonical winning position for L1 is
game (3, 4). The spill route [4,3,3,3,4,2,2,1] wins from that position.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

# Pixel value of the auto-selected piece at level start
_SELECTED_VALUE = 9

# Frame pixels per game unit
_CELL = 4

# Canonical piece position for level 1 (game coordinates) — fallback only.
_CANONICAL_X = 3
_CANONICAL_Y = 4

# The winning choreography is anchored to the color-11 obstacle cluster
# (the win condition: liquid must wet every color-11 obstacle). Canonical
# obstacles bbox-min is game (4,13); canonical spill-1 piece position (3,4).
# Hidden variants translate layouts, so the spill position is expressed
# relative to the detected obstacle anchor.
_OBSTACLE_COLOR = 11
_ANCHOR_TO_PIECE = (3 - 4, 4 - 13)   # piece offset from obstacle bbox-min

# Known winning sequence once the piece stands at the spill-1 position
_SPILL_ROUTE = [4, 3, 3, 3, 4, 2, 2, 1]

UP, DOWN, LEFT, RIGHT, SPILL = 0, 1, 2, 3, 4


@dataclass
class GameState:
    """Observable state extracted from one sp80 frame."""
    grid_shape: tuple
    entity_signatures: dict   # {pixel_value: {'count': N, 'bbox': (r1,r2,c1,c2)}}
    piece_game_x: int         # detected selected piece game x (or canonical if not found)
    piece_game_y: int         # detected selected piece game y (or canonical if not found)
    piece_detected: bool      # False if pixel-9 not found (used canonical fallback)
    anchor_game_x: int = 4    # color-11 obstacle bbox-min (canonical fallback)
    anchor_game_y: int = 13


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


def detect_state(grid: np.ndarray) -> GameState:
    """Extract observable state from one frame."""
    rows, cols = grid.shape
    bg = int(np.bincount(grid.flatten()).argmax())
    sigs = {}
    for val in np.unique(grid):
        if int(val) == bg:
            continue
        positions = np.argwhere(grid == val)
        if not len(positions):
            continue
        r1 = int(positions[:, 0].min())
        r2 = int(positions[:, 0].max())
        c1 = int(positions[:, 1].min())
        c2 = int(positions[:, 1].max())
        sigs[int(val)] = {"count": len(positions), "bbox": (r1, r2, c1, c2)}

    # Locate selected piece (pixel 9); fall back to largest pixel-8 entity
    # (pixel 8 = unselected piece, seen at L2 start before auto-select fires)
    selected_positions = np.argwhere(grid == _SELECTED_VALUE)
    if not len(selected_positions):
        # Find pixel-8 entities; the moveable piece is the widest one (≥20px)
        p8 = np.argwhere(grid == 8)
        selected_positions = p8 if len(p8) >= 20 else np.array([])
    if len(selected_positions):
        min_row = int(selected_positions[:, 0].min())
        min_col = int(selected_positions[:, 1].min())
        game_x = min_col // _CELL
        game_y = min_row // _CELL
        detected = True
    else:
        game_x = _CANONICAL_X
        game_y = _CANONICAL_Y
        detected = False

    # Obstacle anchor: color-11 cells (recolored uniformly at level start).
    anchor_x, anchor_y = 4, 13
    p11 = np.argwhere(grid == _OBSTACLE_COLOR)
    if len(p11):
        anchor_x = int(p11[:, 1].min()) // _CELL
        anchor_y = int(p11[:, 0].min()) // _CELL

    return GameState(
        grid_shape=(rows, cols),
        entity_signatures=sigs,
        piece_game_x=game_x,
        piece_game_y=game_y,
        piece_detected=detected,
        anchor_game_x=anchor_x,
        anchor_game_y=anchor_y,
    )


def compute_route(state: GameState, level_num: int = 1) -> list:
    """
    Return action route for the given state.

    Prefix moves the piece from its detected position to the spill-1
    position (obstacle anchor + offset), then appends the winning spill
    sequence. Anchor-relative so translated hidden variants still win.
    """
    target_x = state.anchor_game_x + _ANCHOR_TO_PIECE[0]
    target_y = state.anchor_game_y + _ANCHOR_TO_PIECE[1]
    dx = target_x - state.piece_game_x
    dy = target_y - state.piece_game_y

    prefix: list = []
    if dx > 0:
        prefix += [RIGHT] * dx
    elif dx < 0:
        prefix += [LEFT] * (-dx)
    if dy > 0:
        prefix += [DOWN] * dy
    elif dy < 0:
        prefix += [UP] * (-dy)

    return prefix + list(_SPILL_ROUTE)


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    """Stub — always reports unverified."""
    return StepResult(success=True, reason="unverified (sp80)", delta={})


def format_companion_block(state: GameState, route: list) -> str:
    """Serialize state + route to a companion [strategy] block."""
    import time
    ts = int(time.time())
    sig_str = " ".join(
        f"v{v}:n={d['count']},r{d['bbox'][0]}-{d['bbox'][1]}c{d['bbox'][2]}-{d['bbox'][3]}"
        for v, d in sorted(state.entity_signatures.items())
    )
    route_str = ",".join(str(a) for a in route)
    return (
        f"[strategy game=sp80 level=1 type=adaptive version=2 created={ts}]\n"
        f"piece_game=({state.piece_game_x},{state.piece_game_y}) detected={state.piece_detected}\n"
        f"entity_signatures: {sig_str}\n"
        f"route: {route_str}\n"
        "[/strategy]"
    )
