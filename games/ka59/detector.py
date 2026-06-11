"""
games/ka59/detector.py — Detector for ka59 (ARC-AGI-3).

ka59 mechanic: "push and contain" puzzle.
- Player controls a selected container sprite (color-14 border, color-0 center).
- Win: for each "0010xzmuziohuf" target (color-4 bordered), a "0022vrxelxosfy"
  container must satisfy dujiampjkx(outer=target, inner=container):
    container.row = target.row + 1
    container.col = target.col + 1
    container.height = target.height - 2
    container.width  = target.width  - 2
  i.e. the 3×3 container top-left must land at (target.row+1, target.col+1)
  inside a 5×5 target.
- Actions: ACTION1=UP, ACTION2=DOWN, ACTION3=LEFT, ACTION4=RIGHT (step=3px)
- ACTION6 (click-select other container) is not a simple action — only one
  container can be moved directly per run.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np

# Color constants from ka59.py
CONTAINER_BORDER = 14   # izokdsdgdo: container border color
CONTAINER_SELECTED = 0  # gkaipxrkmo: center pixel of selected container
TARGET_BORDER = 4        # target piece border color ("0010xzmuziohuf" sprites)
WALL_COLOR = 15          # "0015qniapgwsvb" wall sprite color
FLOOR_BOUND = 2          # camera letter_box / floor-boundary color

STEP = 3   # zsqdfmgyjo: movement step in pixels

ACTION_UP    = 0
ACTION_DOWN  = 1
ACTION_LEFT  = 2
ACTION_RIGHT = 3

# Cross entities (11), fill blocks (12,13) also block player movement via wspfaiigqs
_BLOCKED_COLORS = frozenset({FLOOR_BOUND, CONTAINER_BORDER, WALL_COLOR, 11, 12, 13})


@dataclass
class SpriteBox:
    row: int        # top-left row in frame coordinates
    col: int        # top-left col in frame coordinates
    height: int
    width: int
    selected: bool = False


@dataclass
class GameState:
    grid_shape: tuple
    containers: List[SpriteBox] = field(default_factory=list)
    targets: List[SpriteBox] = field(default_factory=list)
    selected: Optional[SpriteBox] = None
    blocked: Optional[np.ndarray] = field(default=None, repr=False)


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


# ---------------------------------------------------------------------------
# Frame parsing helpers
# ---------------------------------------------------------------------------

def _find_bordered_sprites(grid: np.ndarray, border_color: int,
                            min_size: int = 3) -> List[tuple]:
    """
    Return (row, col, height, width) for each rectangular cluster of border_color.

    Scans top-left corners: pixels with border_color whose cell above and to
    the left are NOT border_color.  From each corner, measures height along the
    left column and width along the top row.
    """
    rows, cols = grid.shape
    mask = (grid == border_color)
    # Top-left: border_color AND (no border_color above) AND (no border_color left)
    above = np.zeros_like(mask)
    above[1:] = mask[:-1]
    left = np.zeros_like(mask)
    left[:, 1:] = mask[:, :-1]
    corners = np.argwhere(mask & ~above & ~left)

    result = []
    visited = np.zeros((rows, cols), dtype=bool)
    for r, c in corners:
        r, c = int(r), int(c)
        if visited[r, c]:
            continue
        h = 0
        while r + h < rows and mask[r + h, c]:
            h += 1
        w = 0
        while c + w < cols and mask[r, c + w]:
            w += 1
        if h >= min_size and w >= min_size:
            result.append((r, c, h, w))
        visited[r:r + h, c:c + w] = True
    return result


def _find_containers(grid: np.ndarray) -> List[SpriteBox]:
    """Find all container sprites (color-14 border, color-0/4 center)."""
    boxes = _find_bordered_sprites(grid, CONTAINER_BORDER, min_size=3)
    out = []
    for r, c, h, w in boxes:
        cr, cc = r + h // 2, c + w // 2
        selected = (int(grid[cr, cc]) == CONTAINER_SELECTED)
        out.append(SpriteBox(row=r, col=c, height=h, width=w, selected=selected))
    return out


def _find_targets(grid: np.ndarray) -> List[SpriteBox]:
    """
    Find target pieces: color-4 bordered rectangles ≥5×5 with non-solid interior.

    Distinguishes from unselected-container color-4 centers (which are ≤2×2 pixels)
    by requiring min_size=5 and a non-all-4 interior.
    """
    boxes = _find_bordered_sprites(grid, TARGET_BORDER, min_size=5)
    out = []
    for r, c, h, w in boxes:
        if h >= 5 and w >= 5 and h >= 2 and w >= 2:
            interior = grid[r + 1:r + h - 1, c + 1:c + w - 1]
            if not np.all(interior == TARGET_BORDER):
                out.append(SpriteBox(row=r, col=c, height=h, width=w))
    return out


# ---------------------------------------------------------------------------
# Standard interface: detect_state
# ---------------------------------------------------------------------------

def detect_state(grid: np.ndarray) -> GameState:
    """Extract containers, targets and selected container from the first frame."""
    rows, cols = grid.shape
    containers = _find_containers(grid)
    targets = _find_targets(grid)

    selected = next((c for c in containers if c.selected), None)
    if selected is None and containers:
        selected = containers[0]   # fallback: first container

    # Pre-compute blocked mask.  Erase the selected container's own cells first
    # so the container doesn't block its own BFS traversal.
    blocked = None
    if selected is not None:
        bg = grid.copy().astype(np.int32)
        sr, sc = selected.row, selected.col
        sh, sw = selected.height, selected.width
        bg[sr:sr + sh, sc:sc + sw] = 1   # replace with background
        blocked = np.zeros((rows, cols), dtype=bool)
        for color in _BLOCKED_COLORS:
            blocked |= (bg == color)

    state = GameState(
        grid_shape=(rows, cols),
        containers=containers,
        targets=targets,
        selected=selected,
        blocked=blocked,
    )
    return state


# ---------------------------------------------------------------------------
# BFS route finder
# ---------------------------------------------------------------------------

def _bfs(blocked: np.ndarray, start_r: int, start_c: int,
         goal_r: int, goal_c: int, sel_h: int, sel_w: int,
         rows: int, cols: int) -> List[int]:
    """
    BFS from (start_r, start_c) to (goal_r, goal_c) for a sel_h×sel_w container.
    Moves in STEP-pixel increments.  Returns action list, or [] if unreachable.
    """
    if start_r == goal_r and start_c == goal_c:
        return []

    queue: deque = deque([(start_r, start_c, [])])
    visited: set = {(start_r, start_c)}

    directions = [
        (ACTION_UP,    -STEP, 0),
        (ACTION_DOWN,  +STEP, 0),
        (ACTION_LEFT,  0,    -STEP),
        (ACTION_RIGHT, 0,    +STEP),
    ]

    while queue:
        r, c, path = queue.popleft()

        for action, dr, dc in directions:
            nr, nc = r + dr, c + dc
            if (nr, nc) in visited:
                continue
            if nr < 0 or nc < 0 or nr + sel_h > rows or nc + sel_w > cols:
                continue
            if blocked[nr:nr + sel_h, nc:nc + sel_w].any():
                continue
            new_path = path + [action]
            if nr == goal_r and nc == goal_c:
                return new_path
            if len(new_path) < 100:
                visited.add((nr, nc))
                queue.append((nr, nc, new_path))

    return []


# ---------------------------------------------------------------------------
# Standard interface: compute_route
# ---------------------------------------------------------------------------

def compute_route(state: GameState, level_num: int = 1) -> list:
    """
    Compute route for selected container to its win position inside a target.

    Win position: container top-left at (target.row+1, target.col+1).
    Picks the nearest reachable target if multiple exist.
    """
    if state.selected is None or not state.targets or state.blocked is None:
        return []

    sel = state.selected
    rows, cols = state.grid_shape
    best: Optional[List[int]] = None

    for target in state.targets:
        goal_r = target.row + 1
        goal_c = target.col + 1
        route = _bfs(state.blocked, sel.row, sel.col, goal_r, goal_c,
                     sel.height, sel.width, rows, cols)
        if route and (best is None or len(route) < len(best)):
            best = route

    return best or []


# ---------------------------------------------------------------------------
# Standard interface: verify_step
# ---------------------------------------------------------------------------

def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    """Check whether the selected container moved as expected."""
    before_containers = _find_containers(before)
    after_containers = _find_containers(after)

    before_sel = next((c for c in before_containers if c.selected), None)
    after_sel = next((c for c in after_containers if c.selected), None)

    if before_sel is None or after_sel is None:
        return StepResult(success=True, reason="ka59: container not detected", delta={})

    dr = after_sel.row - before_sel.row
    dc = after_sel.col - before_sel.col
    expected = {
        ACTION_UP:    (-STEP, 0),
        ACTION_DOWN:  (+STEP, 0),
        ACTION_LEFT:  (0, -STEP),
        ACTION_RIGHT: (0, +STEP),
    }.get(action)

    if expected and (dr, dc) == expected:
        return StepResult(success=True, reason=f"ka59: moved ({dr},{dc})",
                          delta={"dr": dr, "dc": dc})
    if dr == 0 and dc == 0:
        return StepResult(success=False, reason="ka59: container did not move",
                          delta={"dr": 0, "dc": 0})
    return StepResult(success=True, reason=f"ka59: moved ({dr},{dc}) — may have pushed",
                      delta={"dr": dr, "dc": dc})


# ---------------------------------------------------------------------------
# Standard interface: format_companion_block
# ---------------------------------------------------------------------------

def format_companion_block(state: GameState, route: list) -> str:
    sel = state.selected
    sel_str = f"({sel.row},{sel.col}) h={sel.height} w={sel.width}" if sel else "none"
    tgt_str = " | ".join(f"({t.row},{t.col}) h={t.height} w={t.width}"
                         for t in state.targets)
    route_str = ",".join(str(a) for a in route)
    names = {0: "UP", 1: "DOWN", 2: "LEFT", 3: "RIGHT"}
    route_named = " ".join(names.get(a, str(a)) for a in route)
    return (
        f"[strategy game=ka59 level=1 type=adaptive steps={len(route)}]\n"
        f"selected_container: {sel_str}\n"
        f"targets: {tgt_str}\n"
        f"route_indices: {route_str}\n"
        f"route_named: {route_named}\n"
        f"[/strategy]"
    )
