"""
games/re86/detector.py — Adaptive detector for re86 (ARC-AGI-3).

re86 is a single-pixel cursor navigation puzzle.

Observed frame (instance 8af5384d):
  CURSOR  = 0  — single pixel, interior position (e.g., (42,36))
  TARGET  = 1  — single pixel, bottom-right corner at (63,63)
  BOTTOM  = 15 — 63-cell floor along row 63 c0-62
  v4 (color 4), v9 (color 9), v11 (color 11) — obstacle structures

BFS passability: treat colors {4, 9, 11, 15} as obstacles (impassable).
All other pixels (background, color 0 corridors, etc.) are passable.
This is safer than background-only BFS because re86 may use non-background
colors for open corridors (e.g., color 0 as dark floor tiles).

The target (63,63) is approached from (62,63) — a DOWN move triggers win.
v15 covers row 63 cols 0-62, so left-side approach to (63,63) is blocked.

Action convention:  0=UP  1=DOWN  2=LEFT  3=RIGHT
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Grid value constants
# ---------------------------------------------------------------------------

CURSOR = 0    # single-pixel moveable agent
TARGET = 1    # single-pixel destination (bottom-right corner)

# Colors that block movement (obstacle structures + floor border)
OBSTACLE_COLORS = frozenset({4, 9, 11, 15})

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
    cursor_row: Optional[int]
    cursor_col: Optional[int]
    target_row: Optional[int]
    target_col: Optional[int]
    route: list = field(default_factory=list)
    raw_sigs: dict = field(default_factory=dict)


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


# ---------------------------------------------------------------------------
# BFS helpers
# ---------------------------------------------------------------------------

def _bfs(grid: np.ndarray, start: Tuple[int, int], target: Tuple[int, int]) -> list:
    if start == target:
        return []
    rows, cols = grid.shape
    queue: deque = deque([(start[0], start[1], [])])
    visited = {start}
    while queue:
        r, c, path = queue.popleft()
        for action, (dr, dc) in _DELTAS.items():
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                nxt = (nr, nc)
                if nxt == target:
                    return path + [action]
                if nxt not in visited and grid[nr, nc] not in OBSTACLE_COLORS:
                    visited.add(nxt)
                    queue.append((nr, nc, path + [action]))
    return []  # no path found


# ---------------------------------------------------------------------------
# Interface functions
# ---------------------------------------------------------------------------

def detect_state(grid: np.ndarray) -> GameState:
    rows, cols = grid.shape

    bg = int(np.bincount(grid.flatten()).argmax())
    sigs = {}
    for val in np.unique(grid):
        if int(val) == bg:
            continue
        pos = np.argwhere(grid == val)
        r1, c1 = int(pos[:, 0].min()), int(pos[:, 1].min())
        r2, c2 = int(pos[:, 0].max()), int(pos[:, 1].max())
        sigs[int(val)] = {"count": len(pos), "bbox": (r1, r2, c1, c2)}

    # Locate cursor (primary: CURSOR color, count=1)
    cursor_row = cursor_col = None
    if CURSOR in sigs and sigs[CURSOR]["count"] == 1:
        r1, r2, c1, c2 = sigs[CURSOR]["bbox"]
        cursor_row, cursor_col = r1, c1
    else:
        for val, sig in sigs.items():
            if sig["count"] == 1:
                r1, r2, c1, c2 = sig["bbox"]
                if r1 < rows - 5 and c1 < cols - 5:
                    cursor_row, cursor_col = r1, c1
                    break

    # Locate target (primary: TARGET color, count=1)
    target_row = target_col = None
    if TARGET in sigs and sigs[TARGET]["count"] == 1:
        r1, r2, c1, c2 = sigs[TARGET]["bbox"]
        target_row, target_col = r1, c1
    else:
        for val, sig in sigs.items():
            if sig["count"] == 1:
                r1, r2, c1, c2 = sig["bbox"]
                if r1 >= rows - 5 or c1 >= cols - 5:
                    target_row, target_col = r1, c1
                    break

    # BFS computed in detect_state (compute_route needs the grid)
    route = []
    if cursor_row is not None and target_row is not None:
        start = (cursor_row, cursor_col)
        target = (target_row, target_col)
        route = _bfs(grid, start, target)

    return GameState(
        grid_shape=(rows, cols),
        cursor_row=cursor_row,
        cursor_col=cursor_col,
        target_row=target_row,
        target_col=target_col,
        route=route,
        raw_sigs=sigs,
    )


def compute_route(state: GameState, level_num: int = 1) -> list:
    if level_num != 1:
        return []
    return list(state.route)


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    before_state = detect_state(before)
    after_state  = detect_state(after)

    if before_state.cursor_row is None or after_state.cursor_row is None:
        return StepResult(success=False, reason="cursor not found", delta={})

    dr = after_state.cursor_row - before_state.cursor_row
    dc = after_state.cursor_col - before_state.cursor_col

    expected_dr, expected_dc = _DELTAS.get(action, (0, 0))
    if (dr, dc) == (expected_dr, expected_dc):
        return StepResult(success=True, reason="cursor moved correctly",
                          delta={"dr": dr, "dc": dc})

    if dr == 0 and dc == 0:
        return StepResult(success=False, reason="cursor blocked (wall?)",
                          delta={"expected": (expected_dr, expected_dc)})

    return StepResult(success=False,
                      reason=f"unexpected move {(dr,dc)} for action {action}",
                      delta={"expected": (expected_dr, expected_dc), "actual": (dr, dc)})


def format_companion_block(state: GameState, route: list) -> str:
    lines = [
        "[strategy game=re86 level=1 type=cursor-nav-bfs]",
        f"cursor: ({state.cursor_row}, {state.cursor_col})",
        f"target: ({state.target_row}, {state.target_col})",
        f"bfs_route_len: {len(route)}",
        f"route_sample: {route[:10]}{'...' if len(route)>10 else ''}",
        "[/strategy]",
    ]
    return "\n".join(lines)
