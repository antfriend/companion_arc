"""
games/tu93/detector.py — Adaptive detector for tu93 (ARC-AGI-3).

tu93 is a cursor-navigation puzzle. A single-pixel cursor starts inside a
hollow 3×3 start zone and must reach a solid 3×3 target zone.

Observed frame constants (instance 1):
  CURSOR = 4   — single pixel, the agent
  START  = 9   — hollow 3×3 border (8 cells) — start zone
  TARGET = 14  — solid 3×3 block (9 cells) — target zone
  BG     = 5   — background

Action convention (shared with ls20 framework):
  0=UP  1=DOWN  2=LEFT  3=RIGHT

Route strategy (L1): navigate cursor to the nearest corner of the target
zone via a two-segment path (vertical then horizontal). No wall avoidance —
assumes open field between start and target. If walls are discovered on
gateway, route will need obstacle-aware logic.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Grid value constants
# ---------------------------------------------------------------------------

CURSOR = 4    # single-pixel agent
START  = 9    # hollow 3×3 start zone border
TARGET = 14   # solid 3×3 target zone
BG     = 5    # background

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
    target_r1: Optional[int]    # top row of target bbox
    target_r2: Optional[int]
    target_c1: Optional[int]    # left col of target bbox
    target_c2: Optional[int]
    raw_sigs: dict              # value → {count, bbox} for debug


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

    # Build entity signatures (same as stub, kept for debug)
    bg = BG
    sigs = {}
    for val in np.unique(grid):
        if int(val) == bg:
            continue
        pos = np.argwhere(grid == val)
        r1, c1 = int(pos[:, 0].min()), int(pos[:, 1].min())
        r2, c2 = int(pos[:, 0].max()), int(pos[:, 1].max())
        sigs[int(val)] = {"count": len(pos), "bbox": (r1, r2, c1, c2)}

    # Locate cursor (primary: CURSOR color; fallback: any single-pixel non-BG)
    cursor_row = cursor_col = None
    if CURSOR in sigs and sigs[CURSOR]["count"] == 1:
        r1, r2, c1, c2 = sigs[CURSOR]["bbox"]
        cursor_row, cursor_col = r1, c1
    else:
        for val, sig in sigs.items():
            if sig["count"] == 1:
                r1, r2, c1, c2 = sig["bbox"]
                cursor_row, cursor_col = r1, c1
                break

    # Locate target (primary: TARGET color; fallback: solid 3×3 cluster far from cursor)
    target_r1 = target_r2 = target_c1 = target_c2 = None
    if TARGET in sigs:
        r1, r2, c1, c2 = sigs[TARGET]["bbox"]
        target_r1, target_r2, target_c1, target_c2 = r1, r2, c1, c2
    else:
        # Find a filled 3×3 block (count=9) that is not near the cursor
        for val, sig in sigs.items():
            if sig["count"] == 9:
                r1, r2, c1, c2 = sig["bbox"]
                if cursor_row is not None:
                    if abs(r1 - cursor_row) < 5 and abs(c1 - cursor_col) < 5:
                        continue  # too close — probably start zone
                target_r1, target_r2, target_c1, target_c2 = r1, r2, c1, c2
                break

    return GameState(
        grid_shape=(rows, cols),
        cursor_row=cursor_row,
        cursor_col=cursor_col,
        target_r1=target_r1,
        target_r2=target_r2,
        target_c1=target_c1,
        target_c2=target_c2,
        raw_sigs=sigs,
    )


def compute_route(state: GameState, level_num: int = 1) -> list:
    if level_num != 1:
        return []

    if any(x is None for x in [
        state.cursor_row, state.cursor_col,
        state.target_r1, state.target_c1,
    ]):
        return []

    # Navigate to the nearest corner of the target zone
    # Choose target corner closest to cursor to minimise steps
    corners = [
        (state.target_r1, state.target_c1),
        (state.target_r1, state.target_c2),
        (state.target_r2, state.target_c1),
        (state.target_r2, state.target_c2),
    ]
    best_corner = min(
        corners,
        key=lambda rc: abs(rc[0] - state.cursor_row) + abs(rc[1] - state.cursor_col),
    )
    goal_row, goal_col = best_corner

    dr = goal_row - state.cursor_row
    dc = goal_col - state.cursor_col

    route = []
    if dr > 0:
        route += [DOWN] * dr
    elif dr < 0:
        route += [UP] * (-dr)

    if dc > 0:
        route += [RIGHT] * dc
    elif dc < 0:
        route += [LEFT] * (-dc)

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

    return StepResult(success=False, reason=f"unexpected move {(dr,dc)} for action {action}",
                      delta={"expected": expected, "actual": (dr, dc)})


def format_companion_block(state: GameState, route: list) -> str:
    lines = [
        "[strategy game=tu93 level=1 type=cursor-nav]",
        f"cursor: ({state.cursor_row}, {state.cursor_col})",
        f"target: r{state.target_r1}-{state.target_r2} c{state.target_c1}-{state.target_c2}",
        f"route_len: {len(route)}",
        f"route: {route}",
        "[/strategy]",
    ]
    return "\n".join(lines)
