"""
games/re86/detector.py — Adaptive detector for re86 (ARC-AGI-3).

re86 appears to be a cursor-navigation puzzle with two single-pixel entities:
a moveable cursor (color 0) and a fixed target at the bottom-right corner
(color 1). The cursor must navigate to the target.

Observed frame constants (instance 8af5384d):
  CURSOR  = 0  — single pixel at (45, 33), interior position
  TARGET  = 1  — single pixel at (63, 63), bottom-right corner
  BOTTOM  = 15 — 63 cells along row 63 c0-62, boundary row
  bg      = 5  — background (assumed; computed via argmax if needed)

Large entities (v4=64, v9=56, v11=49): unknown role — may be walls or
decorative structure. Not incorporated into route (direct path assumed).

Action convention (shared with ls20/tu93 framework):
  0=UP  1=DOWN  2=LEFT  3=RIGHT

Route strategy: move RIGHT to align column with target, then DOWN to reach
target row. This keeps the cursor in the interior until the final DOWN moves,
avoiding the bottom boundary row (v15) until necessary.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Grid value constants
# ---------------------------------------------------------------------------

CURSOR = 0    # single-pixel moveable agent
TARGET = 1    # single-pixel destination (bottom-right corner)
BOTTOM = 15   # bottom boundary row (63 cells, row 63 c0-62)

UP    = 0
DOWN  = 1
LEFT  = 2
RIGHT = 3


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
    raw_sigs: dict


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


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
        # Fallback: any single-pixel entity not at an extreme corner
        for val, sig in sigs.items():
            if sig["count"] == 1:
                r1, r2, c1, c2 = sig["bbox"]
                # Exclude corner positions — those are likely the target
                if r1 < rows - 5 and c1 < cols - 5:
                    cursor_row, cursor_col = r1, c1
                    break

    # Locate target (primary: TARGET color, count=1)
    target_row = target_col = None
    if TARGET in sigs and sigs[TARGET]["count"] == 1:
        r1, r2, c1, c2 = sigs[TARGET]["bbox"]
        target_row, target_col = r1, c1
    else:
        # Fallback: any single-pixel entity at an extreme corner position
        for val, sig in sigs.items():
            if sig["count"] == 1:
                r1, r2, c1, c2 = sig["bbox"]
                if r1 >= rows - 5 or c1 >= cols - 5:
                    target_row, target_col = r1, c1
                    break

    return GameState(
        grid_shape=(rows, cols),
        cursor_row=cursor_row,
        cursor_col=cursor_col,
        target_row=target_row,
        target_col=target_col,
        raw_sigs=sigs,
    )


def compute_route(state: GameState, level_num: int = 1) -> list:
    if level_num != 1:
        return []

    if any(x is None for x in [
        state.cursor_row, state.cursor_col,
        state.target_row, state.target_col,
    ]):
        return []

    dr = state.target_row - state.cursor_row
    dc = state.target_col - state.cursor_col

    # Move horizontally first (avoids bottom boundary row until final segment)
    route = []
    if dc > 0:
        route += [RIGHT] * dc
    elif dc < 0:
        route += [LEFT] * (-dc)

    if dr > 0:
        route += [DOWN] * dr
    elif dr < 0:
        route += [UP] * (-dr)

    return route


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    before_state = detect_state(before)
    after_state  = detect_state(after)

    if before_state.cursor_row is None or after_state.cursor_row is None:
        return StepResult(success=False, reason="cursor not found", delta={})

    dr = after_state.cursor_row - before_state.cursor_row
    dc = after_state.cursor_col - before_state.cursor_col

    expected = {UP: (-1, 0), DOWN: (1, 0), LEFT: (0, -1), RIGHT: (0, 1)}.get(action)
    if expected is None:
        return StepResult(success=False, reason=f"unknown action {action}", delta={})

    if (dr, dc) == expected:
        return StepResult(success=True, reason="cursor moved correctly",
                          delta={"dr": dr, "dc": dc})

    if dr == 0 and dc == 0:
        return StepResult(success=False, reason="cursor blocked (wall?)",
                          delta={"expected": expected, "actual": (dr, dc)})

    return StepResult(success=False,
                      reason=f"unexpected move {(dr,dc)} for action {action}",
                      delta={"expected": expected, "actual": (dr, dc)})


def format_companion_block(state: GameState, route: list) -> str:
    lines = [
        "[strategy game=re86 level=1 type=cursor-nav]",
        f"cursor: ({state.cursor_row}, {state.cursor_col})",
        f"target: ({state.target_row}, {state.target_col})",
        f"route_len: {len(route)}",
        f"route: RIGHT×{route.count(3)} DOWN×{route.count(1)} LEFT×{route.count(2)} UP×{route.count(0)}",
        "[/strategy]",
    ]
    return "\n".join(lines)
