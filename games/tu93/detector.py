"""
games/tu93/detector.py — Adaptive detector for tu93 (ARC-AGI-3).

tu93 is a MAZE navigation puzzle. A 3×3 probe sprite navigates through a maze
to reach a 3×3 exit sprite. Source game: tu93-0768757b.

Game mechanics (from source analysis):
  hwthhtvyki = 3   — sprite step size (one "half-step" in pixels)
  hcgctulqhn = 6   — alignment unit = 2 * hwthhtvyki
  Probe moves 1 pixel per game tick during animation, completing when
  (probe.y - maze.y) % 6 == 0 and (probe.x - maze.x) % 6 == 0.

  Passability check before action fires:
    ACTION1 (UP):    maze.pixels[y_rel - 3, x_rel] == 2
    ACTION2 (DOWN):  maze.pixels[y_rel + 3, x_rel] == 2
    ACTION3 (LEFT):  maze.pixels[y_rel, x_rel - 3] == 2
    ACTION4 (RIGHT): maze.pixels[y_rel, x_rel + 3] == 2
  where y_rel = probe.y - maze.y,  x_rel = probe.x - maze.x.

  The checked pixel is 3 pixels (CELL_SIZE) ahead of the probe's current
  aligned position in the direction of movement. This is the PASSAGE pixel
  between the current logical cell and the adjacent logical cell.

Logical cell layout (size 6×6 pixels):
  maze.pixels has 0 (room) and 2 (passage) and -1 (void).
  Room cell (r,c) occupies sprite rows r*6..r*6+5 and cols c*6..c*6+5.
  Room pixel (at r*6, c*6) = 0 (not color 2).
  Passage pixel between (r,c) and (r,c+1) = sprite[r*6][c*6+3].
  Passage pixel between (r,c) and (r+1,c) = sprite[r*6+3][c*6].

  Level 1: maze at game (3,3) → frame TL (15,15) (camera offset = 12).
           probe at game (3,3) → logical cell (0,0).
           exit  at game (33,33) → frame TL (45,45) → logical cell (5,5).

Frame signatures for Level 1:
  v4:n=1,r16-16,c17-17 — cursor color-4 pixel at [1][2] of 3×3 sprite
  v9:n=8,r15-17,c15-17 — remaining cursor pixels (9 total in 3×3 sprite)
  Cursor sprite TL = (r4-1, c4-2). v4 at (16,17) → TL (15,15) → cell (0,0).
  v14:n=9,r45-47,c45-47 — exit sprite (3×3 solid color-14 block) → cell (5,5).

Win condition: probe.x == exit.x AND probe.y == exit.y (game coordinates).
  Level 1: probe needs game position (33,33) = logical cell (5,5). ✓

Route is BFS from cursor logical cell to target logical cell, checking
passage pixels (frame[MAZE_ORIGIN_R + r*6 + dr*3, MAZE_ORIGIN_C + c*6 + dc*3] == 2)
for each proposed move direction.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Maze constants (confirmed from game source tu93-0768757b)
# ---------------------------------------------------------------------------

MAZE_ORIGIN_R = 15   # canonical maze origin — fallback only; detect_state derives
MAZE_ORIGIN_C = 15   # the actual origin from the frame (hidden variants shift layouts)
CELL_SIZE = 3        # hwthhtvyki — step size in pixels (passage pixel offset)
LOGICAL_CELL_SIZE = CELL_SIZE * 2  # hcgctulqhn=6 — pixels per logical cell (room-to-room)

# Frame color constants
CURSOR_COLOR = 4   # color-4 marker pixel in the cursor sprite
CURSOR_BODY  = 9   # cursor sprite body color (cursor-only; used for TL anchor)
TARGET_COLOR = 14  # exit sprite fill color
CORRIDOR_COLOR = 2  # passage pixel color — maze.pixels[i,c]==2 allows movement

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
    cursor_cell:  Optional[Tuple[int, int]]   # logical cell (cell_r, cell_c)
    target_pixel: Optional[Tuple[int, int]]   # (row, col) of v14 top-left
    target_cell:  Optional[Tuple[int, int]]   # logical cell (cell_r, cell_c)
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

def _derive_origin(grid: np.ndarray, cursor_tl: Tuple[int, int]) -> Tuple[int, int]:
    """Derive the maze origin from the frame.

    The corridor (color 2) bbox min sits at the maze origin plus 0 or 3 px
    (horizontal vs vertical passage). The cursor sprite TL is always on the
    6px cell lattice, so snapping the corridor bbox min down to the cursor's
    lattice phase recovers the true origin under any whole-scene shift.
    """
    pos = np.argwhere(grid == CORRIDOR_COLOR)
    if len(pos) == 0:
        return (MAZE_ORIGIN_R, MAZE_ORIGIN_C)
    cb_r = int(pos[:, 0].min())
    cb_c = int(pos[:, 1].min())
    phase_r = cursor_tl[0] % LOGICAL_CELL_SIZE
    phase_c = cursor_tl[1] % LOGICAL_CELL_SIZE
    origin_r = cb_r - ((cb_r - phase_r) % LOGICAL_CELL_SIZE)
    origin_c = cb_c - ((cb_c - phase_c) % LOGICAL_CELL_SIZE)
    return (origin_r, origin_c)


def _pixel_to_cell(pixel_row: int, pixel_col: int,
                   origin: Tuple[int, int]) -> Tuple[int, int]:
    """Convert frame pixel (top-left of sprite) to logical cell coordinates."""
    return (
        (pixel_row - origin[0]) // LOGICAL_CELL_SIZE,
        (pixel_col - origin[1]) // LOGICAL_CELL_SIZE,
    )


def _passage_open(grid: np.ndarray, from_r: int, from_c: int,
                  to_r: int, to_c: int, origin: Tuple[int, int]) -> bool:
    """Check if the passage from logical cell (from_r,from_c) to (to_r,to_c) is open.

    The game checks maze.pixels[y_rel + dr*CELL_SIZE, x_rel + dc*CELL_SIZE] == 2
    before allowing movement. In frame coordinates, the passage pixel is at
    (origin_r + from_r*6 + dr*3, origin_c + from_c*6 + dc*3).
    """
    dr = to_r - from_r
    dc = to_c - from_c
    pr = origin[0] + from_r * LOGICAL_CELL_SIZE + dr * CELL_SIZE
    pc = origin[1] + from_c * LOGICAL_CELL_SIZE + dc * CELL_SIZE
    max_r, max_c = grid.shape
    if pr < 0 or pc < 0 or pr >= max_r or pc >= max_c:
        return False
    return int(grid[pr, pc]) == CORRIDOR_COLOR


def _bfs(grid: np.ndarray, start: Tuple[int, int], target: Tuple[int, int],
         origin: Tuple[int, int]) -> list:
    if start == target:
        return []
    # Cell-space bounds from the corridor (color-2) extent relative to the
    # cursor-anchored origin. Cells may be negative (target up/left of cursor).
    pos = np.argwhere(grid == CORRIDOR_COLOR)
    if len(pos) == 0:
        return []
    min_r = (int(pos[:, 0].min()) - origin[0]) // LOGICAL_CELL_SIZE - 1
    max_r = (int(pos[:, 0].max()) - origin[0]) // LOGICAL_CELL_SIZE + 1
    min_c = (int(pos[:, 1].min()) - origin[1]) // LOGICAL_CELL_SIZE - 1
    max_c = (int(pos[:, 1].max()) - origin[1]) // LOGICAL_CELL_SIZE + 1
    queue: deque = deque([(start[0], start[1], [])])
    visited = {start}
    while queue:
        r, c, path = queue.popleft()
        for action, (dr, dc) in _DELTAS.items():
            nr, nc = r + dr, c + dc
            if nr < min_r or nc < min_c or nr > max_r or nc > max_c:
                continue
            # Check passage pixel BEFORE treating as target — only return if the
            # actual game move is allowed (passage color == 2).
            if not _passage_open(grid, r, c, nr, nc, origin):
                continue
            nxt = (nr, nc)
            if nxt == target:
                return path + [action]
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nr, nc, path + [action]))
    return []  # maze has no valid path to target from start


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

    # Cursor = the 3×3 sprite carrying the single color-4 marker. Derive its
    # top-left from the FULL sprite extent (color 4 marker + color 9 body),
    # which is rotation-independent — the marker's offset within the 3×3
    # varies per level with sprite rotation, so it must not be used as anchor.
    cursor_pixel = cursor_cell = None
    origin = (MAZE_ORIGIN_R, MAZE_ORIGIN_C)
    cur_tl = None
    if CURSOR_COLOR in sigs:
        c4 = np.argwhere(grid == CURSOR_COLOR)
        body = np.argwhere(grid == CURSOR_BODY)  # cursor body (cursor-only)
        allc = np.vstack([c4, body]) if len(body) else c4
        cur_tl = (int(allc[:, 0].min()), int(allc[:, 1].min()))
        cursor_pixel = (int(c4[:, 0].min()), int(c4[:, 1].min()))
        # The cursor sprite fully fills a room cell, so its TL is a room TL
        # on the 6px logical lattice. Use it directly as the lattice anchor.
        origin = cur_tl
        cursor_cell = (0, 0)

    # Target: color 14, solid 3×3 exit; TL → logical cell relative to cursor.
    target_pixel = target_cell = None
    if TARGET_COLOR in sigs and cur_tl is not None:
        r1, r2, c1, c2 = sigs[TARGET_COLOR]["bbox"]
        target_pixel = (r1, c1)
        target_cell = (round((r1 - cur_tl[0]) / LOGICAL_CELL_SIZE),
                       round((c1 - cur_tl[1]) / LOGICAL_CELL_SIZE))

    route = []
    if cursor_cell is not None and target_cell is not None:
        route = _bfs(grid, cursor_cell, target_cell, origin)

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
    # Maze navigation is the same mechanic at every level (levels differ only
    # in grid size and wall layout, both read from the frame). No level guard.
    return list(state.route)


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    bs = detect_state(before)
    as_ = detect_state(after)

    if bs.cursor_pixel is None or as_.cursor_pixel is None:
        return StepResult(success=False, reason="cursor not found", delta={})

    dr_px = as_.cursor_pixel[0] - bs.cursor_pixel[0]
    dc_px = as_.cursor_pixel[1] - bs.cursor_pixel[1]

    # Each action moves the cursor LOGICAL_CELL_SIZE pixels (one full cell traversal).
    expected_dr, expected_dc = _DELTAS.get(action, (0, 0))
    expected_dr_px = expected_dr * LOGICAL_CELL_SIZE
    expected_dc_px = expected_dc * LOGICAL_CELL_SIZE

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
