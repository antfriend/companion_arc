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

Everything is derived from the frame — no canonical coordinates. The
competition rerun plays hidden layout variants, so the win position must be
computed from the detected target piece, not assumed.

Display: 20x20 grid, scale 3 px/cell, letterbox offset 2.

Route construction:
  1. Detect selected piece: position, cell size, connector-cell offsets.
  2. Detect target piece: its two connector world cells (color 8 adjacent to
     the non-selected body cluster).
  3. The 13→8 display remap hides connector identity, so enumerate
     rotation (0-3 presses) x marker assignment; geometry leaves exactly two
     consistent (rotation, position) candidates. Execute candidate A's route,
     then chain candidate B's from A's end state — the win check fires at A
     if A was the correct pairing, and B costs only the extra steps otherwise
     (budget 75, each candidate ~15).

Action indices (simple actions [1,2,3,4,5] → indices 0-4):
  0=UP(ACTION1), 1=DOWN(ACTION2), 2=LEFT(ACTION3), 3=RIGHT(ACTION4), 4=ROTATE(ACTION5)
"""

from dataclasses import dataclass, field

import numpy as np

_SCALE = 3      # display pixels per grid cell (64 // 20)
_OFFSET = 2     # letterbox offset ((64 - 20*3) // 2)


@dataclass
class GameState:
    grid_shape: tuple
    sel_pos: tuple | None = None      # (gx, gy) top-left of selected sprite extent
    sel_size: tuple | None = None     # (w, h) in cells, markers included
    sel_marks: list = field(default_factory=list)   # marker offsets [(ox, oy), ...]
    tgt_marks: list = field(default_factory=list)   # target marker world cells [(x, y), ...]
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
    body_cells = {_to_cell(int(r), int(c)) for r, c in body}

    # All connector markers render as color 8 (13 remapped). Split them into
    # the selected piece's (adjacent to the 0-body bbox) and the target's.
    marks = np.argwhere(g == 8)
    marks = marks[marks[:, 0] > 0]
    sel_mark_cells, tgt_mark_cells = set(), set()
    for r, c in marks:
        near_sel = (r1 - _SCALE <= r <= r2 + _SCALE) and (c1 - _SCALE <= c <= c2 + _SCALE)
        cell = _to_cell(int(r), int(c))
        (sel_mark_cells if near_sel else tgt_mark_cells).add(cell)

    if not sel_mark_cells:
        return GameState(grid_shape=(rows, cols), sel_pos=_to_cell(r1, c1))

    all_cells = body_cells | sel_mark_cells
    gx = min(x for x, _ in all_cells)
    gy = min(y for _, y in all_cells)
    w = max(x for x, _ in all_cells) - gx + 1
    h = max(y for _, y in all_cells) - gy + 1

    return GameState(
        grid_shape=(rows, cols),
        sel_pos=(gx, gy),
        sel_size=(w, h),
        sel_marks=sorted((mx - gx, my - gy) for mx, my in sel_mark_cells),
        tgt_marks=sorted(tgt_mark_cells),
    )


def _rot_offsets(marks: list, w: int, h: int) -> tuple:
    """Rotate marker offsets +90° within a w x h cell extent.

    arcengine render: (x, y) -> (h-1-y, x); extent becomes h x w.
    """
    return [(h - 1 - oy, ox) for ox, oy in marks], h, w


def compute_route(state: GameState, level_num: int = 1) -> list:
    if level_num != 1:
        return []
    if (state.sel_pos is None or state.sel_size is None
            or len(state.sel_marks) != 2 or len(state.tgt_marks) != 2):
        return []

    gx, gy = state.sel_pos
    gw = gh = 20   # logical grid (20x20 for all cn04 levels)
    t1, t2 = state.tgt_marks

    # Enumerate rotation count x target-marker assignment; keep geometrically
    # consistent placements (both selected markers land on target markers).
    candidates = []
    marks, w, h = list(state.sel_marks), *state.sel_size
    for k in range(4):
        (o1, o2) = marks
        for ta, tb in ((t1, t2), (t2, t1)):
            px, py = ta[0] - o1[0], ta[1] - o1[1]
            if (px + o2[0], py + o2[1]) == tb and 0 <= px <= gw - w and 0 <= py <= gh - h:
                candidates.append((k, px, py))
        marks, w, h = _rot_offsets(marks, w, h)

    if not candidates:
        return []

    # Execute candidates in sequence; win fires mid-route on the correct one.
    route: list[int] = []
    cur_k, cur_x, cur_y = 0, gx, gy
    for k, px, py in candidates[:2]:
        route.extend([4] * ((k - cur_k) % 4))
        dx, dy = px - cur_x, py - cur_y
        route.extend([3] * dx if dx > 0 else [2] * (-dx))
        route.extend([1] * dy if dy > 0 else [0] * (-dy))
        cur_k, cur_x, cur_y = k, px, py
    return route


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    # Deterministic route with no collision hazards: report the observed
    # selected-sprite extent but never fail (recovery injection would desync
    # the remaining route — same convention as g50t/sk48).
    bs = detect_state(np.asarray(before))
    as_ = detect_state(np.asarray(after))
    return StepResult(
        success=True,
        reason=f"sel {bs.sel_pos} -> {as_.sel_pos}",
        delta={"before_pos": bs.sel_pos, "after_pos": as_.sel_pos},
    )


def format_companion_block(state: GameState, route: list) -> str:
    return (
        f"[strategy game=cn04 level={state.level_num} type=connector-match]\n"
        f"selected: pos={state.sel_pos} size={state.sel_size} marks={state.sel_marks}\n"
        f"target_marks: {state.tgt_marks}\n"
        f"route_len: {len(route)}\n"
        f"[/strategy]"
    )
