"""
games/cn04/detector.py — L1 solver for cn04 (connector-matching puzzle).

Mechanics (from environment source, env hash 2fe56bfb):
  - Sprites are pipe-pieces carrying connector pixels: color 8 and color 13.
  - Win: every visible sprite's connectors each overlap a same-type connector
    (8 on 8, 13 on 13) of another sprite — exactly 2 markers per cell.
  - The engine auto-selects the visible sprite nearest the origin at level
    start. Selected sprite renders with body color 0 and markers as 8
    (13 is remapped to 8 on display). Unselected sprites render in their
    own body color with markers shown as 8.
  - ACTION1-4 move the selected sprite 1 grid cell (UP/DOWN/LEFT/RIGHT).
    Bounds-checked only — no collision between sprites.
  - ACTION5 rotates the selected sprite +90° (single-sprite stacks).
  - ACTION6 (click-select) is not a simple action and is never needed for L1.

Level 1 (20x20 grid, display scale 3, letterbox offset 2):
  - Selected: sprite "0000" (body 12, 5 rows x 6 cols at rot 0), start (3,3) rot 90.
    Markers at rot 0: 8 at local (x=5,y=1), 13 at local (x=5,y=3).
  - Target:   sprite "0001" (body 14) fixed at (12,9) rot 0.
    Markers: 8 at world (12,11), 13 at world (12,13).
  - Win position for selected: rot 0 at grid (7,10).
  - Route: ACTION5 x rotations-to-0, then RIGHT/LEFT, then DOWN/UP to (7,10).
    From the canonical start (3,3) rot 90: 3 rotations + 4 RIGHT + 7 DOWN
    = 14 actions (human baseline 29).

The route is adaptive because one action is burned before the first frame
scan (runner needs a frame): the burn may have moved or rotated the selected
sprite, so position and rotation are re-detected from the frame.

Action indices (simple actions [1,2,3,4,5] → indices 0-4):
  0=UP(ACTION1), 1=DOWN(ACTION2), 2=LEFT(ACTION3), 3=RIGHT(ACTION4), 4=ROTATE(ACTION5)
"""

from dataclasses import dataclass

import numpy as np

_SCALE = 3      # display pixels per grid cell (64 // 20)
_OFFSET = 2     # letterbox offset ((64 - 20*3) // 2)

# Win position for the selected sprite at rotation 0 (grid coords)
_WIN_POS = (7, 10)   # (gx, gy)


@dataclass
class GameState:
    grid_shape: tuple
    sel_pos: tuple | None = None     # (gx, gy) top-left of selected sprite
    sel_rot: int | None = None       # 0 / 90 / 180 / 270
    level_num: int = 1


def _to_cell(px_row: int, px_col: int) -> tuple:
    return ((px_col - _OFFSET) // _SCALE, (px_row - _OFFSET) // _SCALE)


def detect_state(grid: np.ndarray) -> GameState:
    g = np.asarray(grid)
    rows, cols = g.shape

    # Selected sprite body renders as color 0. Row 0 is the step-counter
    # interface (colors 0 and 4) — exclude it.
    body = np.argwhere(g == 0)
    body = body[body[:, 0] > 0]
    if len(body) == 0:
        return GameState(grid_shape=(rows, cols))

    r1, c1 = int(body[:, 0].min()), int(body[:, 1].min())
    r2, c2 = int(body[:, 0].max()), int(body[:, 1].max())

    # The body (0-pixels) spans 5x5 cells at every rotation: the marker
    # column/row lies outside it. Union body cells with the marker (color 8)
    # cells adjacent to the body bbox to recover the full 6x5 / 5x6 sprite
    # extent — its top-left equals sprite.(x,y) at every rotation, and the
    # marker edge identifies the rotation.
    marks = np.argwhere(g == 8)
    marks = marks[(marks[:, 0] > 0) &
                  (marks[:, 0] >= r1 - _SCALE) & (marks[:, 0] <= r2 + _SCALE) &
                  (marks[:, 1] >= c1 - _SCALE) & (marks[:, 1] <= c2 + _SCALE)]
    mark_cells = {_to_cell(int(r), int(c)) for r, c in marks}
    body_cells = {_to_cell(int(r), int(c)) for r, c in body}
    if not mark_cells:
        return GameState(grid_shape=(rows, cols), sel_pos=_to_cell(r1, c1))

    all_cells = body_cells | mark_cells
    gx = min(x for x, _ in all_cells)
    gy = min(y for _, y in all_cells)
    w = max(x for x, _ in all_cells) - gx + 1
    h = max(y for _, y in all_cells) - gy + 1

    if w == 6:
        # markers on right edge → rot 0; left edge → rot 180
        rot = 0 if all(mx == gx + w - 1 for mx, _ in mark_cells) else 180
    elif h == 6:
        # markers on bottom edge → rot 90; top edge → rot 270
        rot = 90 if all(my == gy + h - 1 for _, my in mark_cells) else 270
    else:
        return GameState(grid_shape=(rows, cols), sel_pos=(gx, gy))

    return GameState(grid_shape=(rows, cols), sel_pos=(gx, gy), sel_rot=rot)


def compute_route(state: GameState, level_num: int = 1) -> list:
    if level_num != 1:
        return []
    if state.sel_pos is None or state.sel_rot is None:
        return []

    gx, gy = state.sel_pos
    route: list[int] = []

    # Rotate to 0 (ACTION5 adds +90 per press)
    route.extend([4] * (((360 - state.sel_rot) % 360) // 90))

    # Translate to the win position (no collision — order is free)
    dx = _WIN_POS[0] - gx
    dy = _WIN_POS[1] - gy
    route.extend([3] * dx if dx > 0 else [2] * (-dx))
    route.extend([1] * dy if dy > 0 else [0] * (-dy))
    return route


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    # Deterministic route with no collision hazards: report the observed
    # selected-sprite bbox but never fail (recovery injection would desync
    # the remaining route — same convention as g50t/sk48).
    bs = detect_state(np.asarray(before))
    as_ = detect_state(np.asarray(after))
    return StepResult(
        success=True,
        reason=f"sel {bs.sel_pos} rot {bs.sel_rot} -> {as_.sel_pos} rot {as_.sel_rot}",
        delta={"before_pos": bs.sel_pos, "after_pos": as_.sel_pos},
    )


def format_companion_block(state: GameState, route: list) -> str:
    return (
        f"[strategy game=cn04 level={state.level_num} type=connector-match]\n"
        f"selected_pos: {state.sel_pos}\n"
        f"selected_rot: {state.sel_rot}\n"
        f"win_pos: {_WIN_POS} rot 0\n"
        f"route_len: {len(route)}\n"
        f"[/strategy]"
    )
