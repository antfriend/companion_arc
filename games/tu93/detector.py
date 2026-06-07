"""
games/tu93/detector.py — Adaptive detector for tu93 (ARC-AGI-3).

tu93 is a MAZE navigation puzzle. A 3×3 cursor sprite must navigate
through a maze to reach a 3×3 target sprite.

Source analysis (tu93-0768757b):
  Cursor sprite (0000npnrdhvwvh):
    pixels = [[9,9,9],[9,9,4],[9,9,9]]
    color 4 at sprite [1][2] = mid-right of 3×3 sprite (NOT top-center)
    v4:n=1 in the frame is this single pixel
    v9:n=8,r15-17,c15-17 are the remaining 8 sprite pixels

  Proof from v9 bounding box:
    v4 at (16,17) → sprite top-left must be (r-1, c-2) = (15,15)
    v9 bounding box r15-17,c15-17 spans the full 3×3 sprite ✓
    (If v4 were at [0,1], v9 bounding box would start at row 16, not 15)

  Target sprite (0014mzhhvzrazi):
    pixels = [[14,14,14],[14,14,14],[14,14,14]]
    3×3 solid block of color 14
    v14:n=9,r45-47,c45-47

  Maze walls: colors 0 and 2 (from backdrop sprites)
  Floor (passable): color 5 (background)
  Maze cell size: 3×3 pixels per logical cell
  Maze origin: row=15, col=15 (cursor sprite aligns with cell (0,0))

Each action moves the cursor 3 pixels (1 maze cell):
  0=UP  1=DOWN  2=LEFT  3=RIGHT

Cursor at cell (0,0): _pixel_to_cell(15,15) = (0,0).
Target at cell (10,10): _pixel_to_cell(45,45) = (10,10).
BFS distance ≤ 20 steps in open grid. Budget = 50 steps.

Frame variant robustness:
  v4 at col 17 → sprite_top_c = 17-2 = 15 → cell_c = (15-15)//3 = 0 ✓
  v4 at col 18 → sprite_top_c = 18-2 = 16 → cell_c = (16-15)//3 = 0 ✓

Route strategy: BFS over maze cells from cursor cell to target cell,
treating any cell that contains color 0 or 2 as a wall.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Maze constants (confirmed from sprite analysis)
# ---------------------------------------------------------------------------

MAZE_ORIGIN_R = 15   # pixel row where maze cell (0,0) starts
MAZE_ORIGIN_C = 15   # pixel col where maze cell (0,0) starts
CELL_SIZE = 3        # pixels per maze cell edge

# Grid value constants
CURSOR_COLOR = 4              # mid-right pixel of cursor sprite ([1][2])
CURSOR_SPRITE_ROW_OFFSET = 1  # color-4 is 1 row below sprite top-left
CURSOR_SPRITE_COL_OFFSET = 2  # color-4 is 2 cols right of sprite top-left
TARGET_COLOR = 14             # target sprite fill color
WALL_COLORS = frozenset({2})   # v0 (color 0) is maze floor, not wall

UP    = 0
DOWN  = 1
LEFT  = 2
RIGHT = 3

_DELTAS = {
    UP:    (-1,  0),
    DOWN:  ( 1,  0),
    LEFT:  ( 0, -1),
    RIGHT: ( 0,  1),
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    grid_shape: tuple
    cursor_pixel: Optional[Tuple[int, int]]   # (row, col) of the color-4 pixel
    cursor_cell:  Optional[Tuple[int, int]]   # maze cell (cell_r, cell_c)
    target_pixel: Optional[Tuple[int, int]]   # (row, col) of v14 top-left
    target_cell:  Optional[Tuple[int, int]]   # maze cell (cell_r, cell_c)
    route: list = field(default_factory=list) # BFS route computed in detect_state
    raw_sigs: dict = field(default_factory=dict)


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


# ---------------------------------------------------------------------------
# Maze helpers
# ---------------------------------------------------------------------------

def _pixel_to_cell(pixel_row: int, pixel_col: int) -> Tuple[int, int]:
    return (
        (pixel_row - MAZE_ORIGIN_R) // CELL_SIZE,
        (pixel_col - MAZE_ORIGIN_C) // CELL_SIZE,
    )


def _cell_passable(grid: np.ndarray, cell_r: int, cell_c: int) -> bool:
    pr = MAZE_ORIGIN_R + cell_r * CELL_SIZE
    pc = MAZE_ORIGIN_C + cell_c * CELL_SIZE
    max_r, max_c = grid.shape
    for dr in range(CELL_SIZE):
        for dc in range(CELL_SIZE):
            r, c = pr + dr, pc + dc
            if r >= max_r or c >= max_c:
                return False
            if grid[r, c] in WALL_COLORS:
                return False
    return True


def _bfs(grid: np.ndarray, start: Tuple[int, int], target: Tuple[int, int]) -> list:
    if start == target:
        return []
    max_r = (grid.shape[0] - MAZE_ORIGIN_R) // CELL_SIZE
    max_c = (grid.shape[1] - MAZE_ORIGIN_C) // CELL_SIZE
    queue: deque = deque([(start[0], start[1], [])])
    visited = {start}
    while queue:
        r, c, path = queue.popleft()
        for action, (dr, dc) in _DELTAS.items():
            nr, nc = r + dr, c + dc
            if nr < 0 or nc < 0 or nr >= max_r or nc >= max_c:
                continue
            nxt = (nr, nc)
            if nxt == target:
                return path + [action]
            if nxt not in visited and _cell_passable(grid, nr, nc):
                visited.add(nxt)
                queue.append((nr, nc, path + [action]))
    return []  # no path (maze unsolvable from this state)


# ---------------------------------------------------------------------------
# Interface functions
# ---------------------------------------------------------------------------

def detect_state(grid: np.ndarray) -> GameState:
    rows, cols = grid.shape
    bg = int(np.bincount(grid.flatten()).argmax())
    sigs: dict = {}
    for val in np.unique(grid):
        if int(val) == bg:
            continue
        pos = np.argwhere(grid == val)
        r1, c1 = int(pos[:, 0].min()), int(pos[:, 1].min())
        r2, c2 = int(pos[:, 0].max()), int(pos[:, 1].max())
        sigs[int(val)] = {"count": len(pos), "bbox": (r1, r2, c1, c2)}

    # Cursor: color 4, count=1 (mid-right pixel [1][2] of cursor sprite)
    cursor_pixel = cursor_cell = None
    if CURSOR_COLOR in sigs and sigs[CURSOR_COLOR]["count"] == 1:
        r1, r2, c1, c2 = sigs[CURSOR_COLOR]["bbox"]
        cursor_pixel = (r1, c1)
        # sprite top-left is 1 row up and 2 cols left of the color-4 pixel
        sprite_top_r = r1 - CURSOR_SPRITE_ROW_OFFSET
        sprite_top_c = c1 - CURSOR_SPRITE_COL_OFFSET
        cursor_cell = _pixel_to_cell(sprite_top_r, sprite_top_c)

    # Target: color 14, solid 3×3 block
    target_pixel = target_cell = None
    if TARGET_COLOR in sigs:
        r1, r2, c1, c2 = sigs[TARGET_COLOR]["bbox"]
        target_pixel = (r1, c1)
        target_cell = _pixel_to_cell(r1, c1)

    # BFS route computed here so compute_route doesn't need the grid
    route = []
    if cursor_cell is not None and target_cell is not None:
        route = _bfs(grid, cursor_cell, target_cell)

    return GameState(
        grid_shape=(rows, cols),
        cursor_pixel=cursor_pixel,
        cursor_cell=cursor_cell,
        target_pixel=target_pixel,
        target_cell=target_cell,
        route=route,
        raw_sigs=sigs,
    )


def compute_route(state: GameState, level_num: int = 1) -> list:
    if level_num != 1:
        return []
    return list(state.route)


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    bs = detect_state(before)
    as_ = detect_state(after)

    if bs.cursor_pixel is None or as_.cursor_pixel is None:
        return StepResult(success=False, reason="cursor not found", delta={})

    dr_px = as_.cursor_pixel[0] - bs.cursor_pixel[0]
    dc_px = as_.cursor_pixel[1] - bs.cursor_pixel[1]

    # Each action should move the cursor exactly CELL_SIZE pixels
    expected_dr, expected_dc = _DELTAS.get(action, (0, 0))
    expected_dr_px = expected_dr * CELL_SIZE
    expected_dc_px = expected_dc * CELL_SIZE

    if (dr_px, dc_px) == (expected_dr_px, expected_dc_px):
        return StepResult(success=True, reason="cursor moved one cell",
                          delta={"dr_px": dr_px, "dc_px": dc_px})

    if dr_px == 0 and dc_px == 0:
        return StepResult(success=False, reason="cursor blocked (wall?)",
                          delta={"expected": (expected_dr_px, expected_dc_px)})

    return StepResult(
        success=False,
        reason=f"unexpected move ({dr_px},{dc_px}) for action {action}",
        delta={"expected": (expected_dr_px, expected_dc_px), "actual": (dr_px, dc_px)},
    )


def format_companion_block(state: GameState, route: list) -> str:
    lines = [
        "[strategy game=tu93 level=1 type=maze-nav]",
        f"cursor_pixel: {state.cursor_pixel}  cursor_cell: {state.cursor_cell}",
        f"target_pixel: {state.target_pixel}  target_cell: {state.target_cell}",
        f"bfs_route_len: {len(route)}",
        f"route: {route}",
        "[/strategy]",
    ]
    return "\n".join(lines)
