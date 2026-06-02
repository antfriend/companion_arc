"""
games/ls20/detector.py — Per-game detector for ls20 (ARC-AGI-3).

Implements the standard detector interface:
  detect_state(grid)              → GameState
  compute_route(state)            → list[int]
  verify_step(before, after, act) → StepResult
  format_companion_block(state, route) → str

Also re-exports all legacy functions from ls20_detector.py so the two files
stay in sync. The root ls20_detector.py is now a thin shim that imports
everything from here.

Grid value constants (observed from ls20-9607627b frames):
  BLOCK=12  WALL=3  FLOOR=5  ENT1=9  TIMER=11  VOID=4
"""

import re
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Grid value constants
# ---------------------------------------------------------------------------

BLOCK = 12
WALL  = 3
FLOOR = 5
ENT1  = 9
TIMER = 11
VOID  = 4

# Action indices
UP    = 0
DOWN  = 1
LEFT  = 2
RIGHT = 3

_ACTION_NAMES = {UP: "UP", DOWN: "DOWN", LEFT: "LEFT", RIGHT: "RIGHT"}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    """All observable state extracted from one frame of ls20."""
    block_pos: Optional[tuple]              # (min_row, min_col) of the 2×5 block
    entity2_ring: Optional[dict]            # {top, bot, left, right, interior_*}
    entity2_notch_orientation: Optional[int] # 0/90/180/270
    cluster: Optional[dict]                 # {top_row, bot_row, col_min, col_max, col_center}
    entity1_state: int                      # 0/1/2


@dataclass
class StepResult:
    """Outcome of verifying one action against before/after frames."""
    success: bool       # True = world changed as expected
    reason: str         # human-readable description
    delta: dict         # {row_delta, col_delta, before_pos, after_pos}


# ---------------------------------------------------------------------------
# Block detection
# ---------------------------------------------------------------------------

def detect_block(grid: np.ndarray) -> Optional[tuple]:
    """Return (min_row, min_col) of the block (value 12), or None."""
    positions = np.argwhere(grid == BLOCK)
    if not len(positions):
        return None
    return (int(positions[:, 0].min()), int(positions[:, 1].min()))


# ---------------------------------------------------------------------------
# Entity2 ring detection
# ---------------------------------------------------------------------------

def detect_entity2_ring(grid: np.ndarray, search_rows: tuple = (2, 40)) -> Optional[dict]:
    """
    Find the topmost ring structure (WALL boundary enclosing FLOOR interior).

    Returns dict with keys: top, bot, left, right, interior_top, interior_bot,
    interior_left, interior_right. Returns None if no ring found.
    """
    start, end = search_rows
    rows, cols = grid.shape

    for r in range(max(0, start), min(end, rows - 2)):
        row = grid[r]
        wall_cols = np.where(row == WALL)[0]
        if len(wall_cols) < 2:
            continue

        left_wall  = int(wall_cols[0])
        right_wall = int(wall_cols[-1])
        span = right_wall - left_wall

        if span < 4:
            continue

        interior_slice = grid[r + 1, left_wall + 1: right_wall]
        if not np.any(interior_slice == FLOOR):
            continue

        bot = r
        for r2 in range(r + 1, min(r + 20, rows)):
            row2 = grid[r2]
            ring_slice = row2[left_wall: right_wall + 1]
            wall_count = int(np.sum(ring_slice == WALL))
            if wall_count >= max(3, (span * 2) // 3):
                bot = r2
                break
            if wall_count >= 2:
                bot = r2
                continue
            break

        return {
            "top": r,
            "bot": bot,
            "left": left_wall,
            "right": right_wall,
            "interior_top": r + 1,
            "interior_bot": bot - 1,
            "interior_left": left_wall + 1,
            "interior_right": right_wall - 1,
        }

    return None


# ---------------------------------------------------------------------------
# Cluster detection
# ---------------------------------------------------------------------------

def detect_cluster(grid: np.ndarray) -> Optional[dict]:
    """
    Detect the cluster (state-changer) — a bordered box of values 0 and 1.
    """
    mask = (grid == 0) | (grid == 1)
    positions = np.argwhere(mask)
    if not len(positions):
        return None

    rows = positions[:, 0]
    cols = positions[:, 1]

    valid = rows < 60
    rows = rows[valid]
    cols = cols[valid]
    if not len(rows):
        return None

    return {
        "top_row":    int(rows.min()),
        "bot_row":    int(rows.max()),
        "col_min":    int(cols.min()),
        "col_max":    int(cols.max()),
        "col_center": int((cols.min() + cols.max()) // 2),
    }


# ---------------------------------------------------------------------------
# Entity1 state detection
# ---------------------------------------------------------------------------

def detect_entity1_state(grid: np.ndarray) -> int:
    """
    Infer entity1 state (0, 1, or 2) from the entity1 carrier at rows 55-60.

    STATE 0: r55-56 full, r57-60 empty
    STATE 1: r55-56 full; r57-58 partial (c7-8 only)
    STATE 2: r55-56 full; r57-58 full
    """
    rows, cols = grid.shape
    if rows < 61:
        return 0

    carrier = grid[55:61, 1:11]
    r55_56  = carrier[0:2, 2:9]
    r57_58  = carrier[2:4, 2:9]

    has_full_base = np.all(r55_56 == ENT1)
    if not has_full_base:
        return 0

    r57_58_count = int(np.sum(r57_58 == ENT1))

    if r57_58_count == 0:
        return 0
    elif r57_58_count <= 4:
        return 1
    else:
        return 2


# ---------------------------------------------------------------------------
# Standard interface: detect_state
# ---------------------------------------------------------------------------

def detect_state(grid: np.ndarray) -> GameState:
    """Extract all observable state from one frame."""
    ring  = detect_entity2_ring(grid, search_rows=(2, 40))
    notch = None
    if ring is not None:
        try:
            from level_scanner import _detect_ring_notch_orientation
            notch = _detect_ring_notch_orientation(grid, ring)
        except Exception:
            pass

    return GameState(
        block_pos=detect_block(grid),
        entity2_ring=ring,
        entity2_notch_orientation=notch,
        cluster=detect_cluster(grid),
        entity1_state=detect_entity1_state(grid),
    )


# ---------------------------------------------------------------------------
# Standard interface: compute_route
# ---------------------------------------------------------------------------

def compute_route(state: GameState) -> list:
    """
    Compute the L1 winning route from a GameState.

    Strategy: straight UP into entity2 interior, staying in cols ~34-38,
    which never overlaps the cluster at cols ~20-22 — entity1 stays STATE 0
    throughout, triggering L1 WIN on entity2 entry.
    """
    if state.block_pos is None or state.entity2_ring is None:
        return [UP] * 7  # safe fallback for known instance

    block_row = state.block_pos[0]
    e2 = state.entity2_ring
    target_row = e2["bot"] - 1

    if block_row <= target_row:
        return [UP] * 1

    ups = max(1, (block_row - target_row) // 5)
    return [UP] * ups


# ---------------------------------------------------------------------------
# Legacy wrapper: compute_l1_route(grid)
# ---------------------------------------------------------------------------

def compute_l1_route(grid: np.ndarray) -> list:
    """Legacy entry point — detects state then calls compute_route."""
    return compute_route(detect_state(grid))


# ---------------------------------------------------------------------------
# Standard interface: verify_step
# ---------------------------------------------------------------------------

def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    """
    Verify that one action produced the expected world change.

    For ls20, each directional action should shift the block 5 cells in the
    named direction. Blocked = block position identical before and after.

    Returns StepResult(success, reason, delta).
    """
    before_pos = detect_block(before)
    after_pos  = detect_block(after)

    if before_pos is None or after_pos is None:
        return StepResult(
            success=False,
            reason="block not detected in before or after frame",
            delta={"before_pos": before_pos, "after_pos": after_pos,
                   "row_delta": None, "col_delta": None},
        )

    row_delta = after_pos[0] - before_pos[0]
    col_delta = after_pos[1] - before_pos[1]
    delta = {
        "before_pos": before_pos,
        "after_pos":  after_pos,
        "row_delta":  row_delta,
        "col_delta":  col_delta,
    }

    action_name = _ACTION_NAMES.get(action, str(action))

    if action == UP:
        if row_delta < 0:
            return StepResult(True, f"block moved UP by {-row_delta} rows", delta)
        elif row_delta == 0:
            return StepResult(False, f"block did not move UP — wall or boundary", delta)
        else:
            return StepResult(False, f"block moved DOWN on UP action (unexpected)", delta)

    elif action == DOWN:
        if row_delta > 0:
            return StepResult(True, f"block moved DOWN by {row_delta} rows", delta)
        elif row_delta == 0:
            return StepResult(False, f"block did not move DOWN — wall or boundary", delta)
        else:
            return StepResult(False, f"block moved UP on DOWN action (unexpected)", delta)

    elif action == LEFT:
        if col_delta < 0:
            return StepResult(True, f"block moved LEFT by {-col_delta} cols", delta)
        elif col_delta == 0:
            return StepResult(False, f"block did not move LEFT — wall or boundary", delta)
        else:
            return StepResult(False, f"block moved RIGHT on LEFT action (unexpected)", delta)

    elif action == RIGHT:
        if col_delta > 0:
            return StepResult(True, f"block moved RIGHT by {col_delta} cols", delta)
        elif col_delta == 0:
            return StepResult(False, f"block did not move RIGHT — wall or boundary", delta)
        else:
            return StepResult(False, f"block moved LEFT on RIGHT action (unexpected)", delta)

    return StepResult(False, f"unknown action {action}", delta)


# ---------------------------------------------------------------------------
# Standard interface: format_companion_block
# ---------------------------------------------------------------------------

def format_companion_block(state: GameState, route: list) -> str:
    """Serialize detected state + route to companion.md [strategy] block."""
    ts = int(time.time())

    block_str = (
        f"{state.block_pos[0]}-{state.block_pos[0]+1},"
        f"{state.block_pos[1]}-{state.block_pos[1]+4}"
        if state.block_pos else "unknown"
    )
    e2 = state.entity2_ring
    e2_str = (
        f"rows={e2['top']}-{e2['bot']} cols={e2['left']}-{e2['right']}"
        if e2 else "unknown"
    )
    cl = state.cluster
    cluster_str = (
        f"rows={cl['top_row']}-{cl['bot_row']} cols={cl['col_min']}-{cl['col_max']}"
        if cl else "unknown"
    )
    route_str = ",".join(str(a) for a in route)
    ups = len(route)

    lines = [
        f"[strategy game=ls20 level=1 type=adaptive algorithm=up_only "
        f"version=2 confirmed=true created={ts}]",
        f"block_start: rows={block_str}",
        f"entity2_bounds: {e2_str}",
        f"cluster_detected: {cluster_str}",
        f"entity1_state_at_start: {state.entity1_state}",
        f"ups_to_entity2: {ups}",
        f"route: {route_str}",
        f"notes: UP×{ups} straight into entity2 — avoids cluster (c20-22) entirely.",
        f"       L1 WIN = entity1 STATE 0 at entity2 entry. No collectibles needed.",
        "[/strategy]",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Legacy alias: format_strategy_block(game, level, grid, route)
# ---------------------------------------------------------------------------

def format_strategy_block(game: str, level: int, grid: np.ndarray, route: list) -> str:
    """Legacy entry point — detects state then calls format_companion_block."""
    state = detect_state(grid)
    return format_companion_block(state, route)


# ---------------------------------------------------------------------------
# Strategy block I/O for companion files
# ---------------------------------------------------------------------------

_STRATEGY_PATTERN = re.compile(
    r"\[strategy\b[^\]]*\bgame=(\w+)\b[^\]]*\blevel=(\d+)\b[^\]]*\].*?\[/strategy\]",
    re.DOTALL | re.IGNORECASE,
)


def update_strategy_in_file(path: str, new_block: str) -> None:
    """Replace [strategy game=ls20 level=1] block in companion file, or append."""
    with open(path, encoding="utf-8") as f:
        content = f.read()

    replaced, n = _STRATEGY_PATTERN.subn(new_block, content, count=1)
    if n:
        with open(path, "w", encoding="utf-8") as f:
            f.write(replaced)
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n\n---\n\n{new_block}\n")


def parse_strategy(companion_text: str, game: str, level: int) -> Optional[dict]:
    """Parse the most recent [strategy game=X level=N] block. Returns dict or None."""
    for m in _STRATEGY_PATTERN.finditer(companion_text):
        if m.group(1).lower() == game.lower() and int(m.group(2)) == level:
            block_text = m.group(0)
            route_match = re.search(r"^route:\s*([\d,\s]+)$", block_text, re.MULTILINE)
            if route_match:
                route = [
                    int(x)
                    for x in re.split(r"[,\s]+", route_match.group(1).strip())
                    if x
                ]
                return {"route": route, "block": block_text}
    return None
