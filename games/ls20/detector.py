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
# Known multi-step routes (level 2)
# ---------------------------------------------------------------------------
# Full L2 route starting from r40,c29 (traditional training start position).
# Structure: UP×6+RIGHT×3 preamble to reach r10,c49, then ring B approach
# and win sequence. Produced by compute_route; the trailing [RIGHT] acts as
# the level_step=0 probe that moves the block from c29 to c34 before the
# main route starts.
# 0=UP  1=DOWN  2=LEFT  3=RIGHT
_L2_ROUTE = [
    # HYPOTHESIS: cross collectible ("+" at r45,c49) ROTATES the inner ring entity1
    # pattern on each landing. The DOWN from r35,c14 requires the correct rotation.
    # cross ×1 (DC31 default): inner ring at 90°  → DOWN still blocked (confirmed)
    # cross ×2: inner ring at 180° → try DOWN
    # cross ×3: inner ring at 270° → try DOWN (needs oscillation cycle)
    # cross ×4: inner ring back to start orientation
    #
    # Timer budget: ring B gives ~21 steps. DC31 ring B→ring A = 18 steps (timer=3 at ring A).
    # Adding DOWN+UP (2 extra) for cross ×2: 18+2=20 steps (timer=1 at ring A). Safe!

    # Phase 1: Ring B + cross ×1+×2 + ring A + first DOWN test (confirmed FAIL at ×2)
    0, 0, 0, 0, 0, 0,               # UP×6 → r10,c34
    3, 3, 3,                        # RIGHT×3 → r10,c49
    1, 1, 1, 1, 1, 1,               # DOWN×6 → r40,c49
    2, 1, 1, 2,                     # L,D,D,L → r50,c39 [ring B; STATE 2; timer reset]
    3, 3,                           # RIGHT×2 → r50,c49
    0,                              # UP → r45,c49 [cross ×1]
    1, 0,                           # DOWN + UP → cross ×2 (if immediate respawn)
    0, 0, 0, 0, 0, 0, 0,            # UP×7 → r10,c49
    2, 2, 2, 2, 2, 2, 2,            # LEFT×7 → r10,c14
    1,                              # DOWN → r15,c14 [ring A; timer reset]
    1, 1, 1, 1,                     # DOWN×4 → r35,c14 [deadlock]
    1,                              # DOWN [10A test ×1: cross ×2 — FAIL expected]

    # Phase 2: oscillation (timer=0 → ring A+B+cross respawn; block resets)
    0, 0, 0, 0,                     # UP×4 → r15,c14 (timer: →13)
    0,                              # UP → r10,c14 (wide connector; timer: →12)
    2, 3, 2, 3, 2, 3,               # LEFT-RIGHT×3 (timer: 12→6)
    2, 3, 2, 3, 2, 3,               # LEFT-RIGHT×3 (timer: 6→0 → RESET; cross respawns)

    # Phase 3: post-oscillation → cross ×3 → ring B ×2 → ring A ×2 → DOWN test
    # Pattern: last-osc-RIGHT(timer=0) | UP-buffer(r40→r35,c29) | RIGHT(r35,c34) | UP×5(r10) | ...
    3,                              # transition buffer (last oscillation fires timer=0)
    0,                              # UP buffer: block appears at r40,c29 → moves to r35,c29
    3,                              # RIGHT → r35,c34 (first real nav step)
    0, 0, 0, 0, 0,                  # UP×5 → r10,c34
    3, 3, 3,                        # RIGHT×3 → r10,c49
    1, 1, 1, 1, 1, 1, 1,            # DOWN×7 → r45,c49 [cross ×3! timer=5 remaining]
    1,                              # DOWN → r50,c49
    2, 2,                           # LEFT×2 → r50,c39 [ring B ×2; timer reset=21]
    3, 3,                           # RIGHT×2 → r50,c49
    0,                              # UP → r45,c49 [cross ×4 — 360°, back to start?] (timer=18)
    1,                              # DOWN → r50,c49 (timer=17)
    0, 0, 0, 0, 0, 0, 0, 0,         # UP×8 → r10,c49 (timer=9)
    2, 2, 2, 2, 2, 2, 2,            # LEFT×7 → r10,c14 (timer=2)
    1,                              # DOWN → r15,c14 [ring A ×2; timer reset=17] (timer=1→reset)
    1, 1, 1, 1,                     # DOWN×4 → r35,c14 (timer=13)
    1,                              # DOWN [10A TEST: after cross ×4 (0°/360°)]
]

# Alias: _L2_ROUTE_FROM_TOP is the same route starting from r10,c49
# (skipping the UP×6+RIGHT×3 preamble that gets the block from r40,c34 to r10,c49).
# Used by compute_route to build adaptive L2 routes for any block starting position.
_L2_ROUTE_FROM_TOP = _L2_ROUTE[9:]

_L2_ROUTE_DC31_CONTINUATION = [
    # Ascend to wide connector (7 steps)
    0, 0, 0, 0, 0, 0, 0,            # UP×7 → r10-11 c49-53
    # Traverse wide connector to c14-18 (7 steps)
    2, 2, 2, 2, 2, 2, 2,            # LEFT×7 → r10-11 c14-18
    # Collect ring A (timer reset)
    1,                              # DOWN → r15-16 c14-18 [ring A]
    # Descend to deadlock
    1, 1, 1, 1,                     # DOWN×4 → r35-36 c14-18
    # Ring A second cycle: UP×5 + micro-oscillation ×12 (timer expiry)
    0, 0, 0, 0,                     # UP×4 → r15-16 c14-18
    0,                              # UP×1 → r10-11 c14-18 (wide connector)
    2, 3, 2, 3, 2, 3,               # LEFT-RIGHT×3 (timer: 12→6)
    2, 3, 2, 3, 2, 3,               # LEFT-RIGHT×3 (timer: 6→0; ring respawn; block resets to r40-41 c29-33)
    # DC31 post-reset: approach ring A second collection
    # Timer expires at end of the 6th oscillation pair (route[57]=RIGHT).
    # The very next frame is a reset-animation frame: the block is temporarily
    # invisible (BLOCK=12 absent). Any action on that frame is a no-op.
    # Buffer step absorbs the transition; RIGHT fires when block reappears.
    0,                              # buffer: UP no-op on reset-animation frame
    3,                              # RIGHT → r40-41 c34-38 [block visible at r40,c29]
    0, 0, 0, 0, 0, 0,               # UP×6 → r10-11 c34-38
    2, 2, 2, 2,                     # LEFT×4 → r10-11 c14-18
    1,                              # DOWN → r15-16 c14-18 [ring A x2; timer reset]
    1, 1, 1, 1,                     # DOWN×4 → r35-36 c14-18 [DC31 probe end]

    # --- DC32 revised ---
    # From r35,c14: confirmed dead end (DOWN + RIGHT both wall-blocked).
    # Burn remaining timer via UP to r10 + LEFT fails at c9 boundary.
    # Same confirmed sequence as the previous run → second reset at r40,c29.

    1, 1, 1,                        # DOWN×3 FAIL (confirmed dead end — burns timer)
    3, 3, 3, 3, 3,                  # RIGHT×5 FAIL (confirmed dead end — burns timer)
    0, 0, 0, 0, 0,                  # UP×5 → r10,c14
    0, 0, 0,                        # UP×3 FAIL (r10 ceiling)
    2,                              # LEFT → r10,c9
    2, 2, 2,                        # LEFT×3 FAIL at c9 boundary (burns timer)
    2,                              # LEFT (transition: timer expires → second reset r40,c29)
    0,                              # buffer: transition frame

    # --- From second reset r35,c29 (UP buffer moves block from r40 to r35) ---
    # Timer = 21, every step (OK or FAIL) = 1 unit — confirmed.
    # Ring A x3: must go via r10 (LEFT×4 at r15 is wall-blocked at c29).
    # Path: RIGHT + UP×5 + LEFT×4 + DOWN = 12 steps.

    3,                              # RIGHT → r35,c34 (step 1)
    0, 0, 0, 0, 0,                  # UP×5 → r10,c34 (step 6) [35→30→25→20→15→10]
    2, 2, 2, 2,                     # LEFT×4 → r10,c14 (step 10) [proven open at r10]
    1,                              # DOWN → r15,c14 [ring A x3! timer reset] (step 11)

    # Ring A x3 collected (timer = 21). Entity1: ring B×1, cross×1, ring A×3.
    # Ring B x2 via proven 18-step path (timer resets at ring B too):
    0,                              # UP → r10,c14
    3, 3, 3, 3, 3, 3, 3,            # RIGHT×7 → r10,c49
    1, 1, 1, 1, 1, 1,               # DOWN×6 → r40,c49
    2,                              # LEFT → r40,c44
    1, 1,                           # DOWN×2 → r50,c44
    2,                              # LEFT → r50,c39 [ring B x2! timer reset to 21]

    # Ring B x2 confirmed: timer reset to 21, UP from r50,c39 is BLOCKED.
    # Must go RIGHT×2 to r50,c49 first, then UP×8 to r10,c49 (proven DC31 path).
    # Then probe r5 corridor at c49 and collect ring A x4 for timer safety.

    3, 3,                           # RIGHT×2 → r50,c49 (step 2, timer=19)
    0, 0, 0, 0, 0, 0, 0, 0,         # UP×8 → r10,c49 (step 10, timer=11)
    0,                              # UP → r5,c49? [probe r5 corridor at c49] (step 11)
    2, 2, 2,                        # LEFT×3 → r5,c34 (step 14, timer=8)
    1,                              # DOWN → r10,c34 (step 15, timer=7)
    2, 2, 2, 2,                     # LEFT×4 → r10,c14 (step 19, timer=3)
    1,                              # DOWN → r15,c14 [ring A x4! timer reset] (step 20)

    # --- After ring A x4 (timer=21). Entity1: ring B×2, cross×1, ring A×4 ---
    # Probe 1: r5 corridor again with post-ring-A-x4 entity1 state (6 steps)
    0,                              # UP → r10,c14
    3, 3, 3, 3,                     # RIGHT×4 → r10,c34
    0,                              # UP → r5,c34 [r5 probe with new entity1 state]

    # Probe 2: cross x2 via r5 corridor → c49 → r45 (12 more steps, timer=9)
    3, 3, 3,                        # RIGHT×3 → r5,c49 (timer=12)
    1,                              # DOWN → r10,c49 (timer=11)
    1, 1, 1, 1, 1, 1, 1,            # DOWN×7 → r45,c49 [cross x2?] (timer=4)

    # Timer at 4 after cross x2 attempt — navigate to ring B x3 if timer reset
    0,                              # UP → r40,c49 (timer=3)
    2,                              # LEFT → r40,c44 (timer=2)
    1, 1,                           # DOWN×2 → r50,c44 (timer=0 → GAME OVER if no reset)
    2,                              # LEFT → r50,c39 [ring B x3 if accessible, timer reset?]
]

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

def initial_action(level_num: int) -> int:
    """
    Return the correct probe action for each level.

    This action is taken first (before detect_state) to get the initial frame.
    It doubles as route step 0, so compute_route returns the remainder.

    L1: UP  — block starts at r45, probe moves it to r40 (start of detour).
    L2: RIGHT — block starts at c29-33, probe moves it to c34-38 (start of L2 route).
    """
    return {1: UP, 2: RIGHT}.get(level_num, UP)


def _l2_navigate_to_r10_c49(block_pos: Optional[tuple]) -> list:
    """
    Build the minimal navigation from block_pos to r10,c49 (ring B gateway).

    Always routes via c34 (the proven clear vertical corridor) to avoid
    UP-blocking walls at c29 and other columns. Each action moves 5 units.

    Returns a list of actions. The CALLER puts actions[0] at route[-1] (probe
    slot) and actions[1:] at route[0:] — preserving the level_step=0 probe
    pattern used by the competition/batch runner.

    Examples:
      r40,c29 → [RIGHT, UP×6, RIGHT×3]  (10 steps; training default)
      r10,c34 → [RIGHT, RIGHT, RIGHT]    (3 steps; competition default if L2
                                          starts where L1 goal was)
      r40,c34 → [UP×6, RIGHT×3]          (9 steps)
    """
    r, c = block_pos
    if r == 10 and c == 49:
        return []  # already at gateway

    steps = []

    # 1. Normalize column to c34 (clear vertical corridor)
    col_diff = c - 34
    if col_diff > 0:
        steps += [LEFT] * (col_diff // 5)
    elif col_diff < 0:
        steps += [RIGHT] * ((-col_diff) // 5)
    c = 34

    # 2. Ascend to r10 via c34
    if r > 10:
        steps += [UP] * ((r - 10) // 5)
    elif r < 10:
        steps += [DOWN] * ((10 - r) // 5)
    r = 10

    # 3. Go RIGHT from c34 to c49 (3 steps × 5 cols each)
    steps += [RIGHT, RIGHT, RIGHT]

    return steps


def compute_route(state: GameState, level_num: int = 1) -> list:
    """
    Compute the winning route from a GameState.

    Level 1 — maze-aware route. The game is a cursor puzzle: sfqyzhzkij (cursor)
    must navigate fixed corridors to reach the rotation changer at game (x=19,y=30)
    and then the goal cell at game (x=34,y=10). The maze has walls at x=29 that
    block every UP move from that column, so the cursor must first normalize to
    x=34 (the clear vertical corridor) before going UP. The horizontal corridor
    at y=25 is always clear for LEFT×3 and RIGHT×3.

    Level 2 — known DC31 route (_L2_ROUTE).
    """
    if level_num == 2:
        # Adaptive: detect where the block actually is at L2 start and build
        # a prefix that navigates to r10,c49 (ring B gateway) from there.
        #
        # The batch/competition runner uses route[-1] as a probe action at
        # level_step=0 (before the route proper begins at level_step=1).
        # We preserve this pattern: nav[0] goes to route[-1] and nav[1:]
        # goes to route[0:], so the full execution order is:
        #   level_step=0: nav[0]       ← moves block toward c34 corridor
        #   level_step=1: nav[1]       (or _L2_ROUTE_FROM_TOP[0] if no nav)
        #   ...
        #   level_step=k: _L2_ROUTE_FROM_TOP[0]  ← ring B approach starts
        #
        # For r40,c29 (training default): nav=[RIGHT,UP×6,RIGHT×3], so
        #   route = [UP×6,RIGHT×3] + _L2_ROUTE_FROM_TOP + [RIGHT]
        #         = _L2_ROUTE + [RIGHT]   ← identical to the old hardcoded form.
        # For r10,c34 (competition: L2 starts where L1 goal was):
        #   nav=[RIGHT,RIGHT,RIGHT], route=[RIGHT,RIGHT]+_L2_ROUTE_FROM_TOP+[RIGHT]
        #   → 3 RIGHTs navigate c34→c49, then ring B approach.
        #   Timer to ring B: 21-13=8 (vs 21-20=1 in training) — more margin.
        if state.block_pos is None:
            return list(_L2_ROUTE) + [RIGHT]  # can't detect position; use original
        nav = _l2_navigate_to_r10_c49(state.block_pos)
        if not nav:
            # Already at r10,c49; DOWN is a safe no-op probe (r5 is passable but
            # _L2_ROUTE_FROM_TOP[0]=DOWN will correct it on the first real step).
            return list(_L2_ROUTE_FROM_TOP) + [DOWN]
        return list(nav[1:]) + list(_L2_ROUTE_FROM_TOP) + [nav[0]]

    STANDARD_COL = 34   # game x of the clear vertical corridor
    DETOUR_ROW   = 25   # game y of the clear horizontal corridor (y=25)
    FINAL_ROW    = 10   # game y of the goal (rjlbuycveu)

    if state.block_pos is None:
        return [0,0,0, 2,2,2, 1,0, 3,3,3, 0,0,0]  # safe fallback (r40,c34)

    block_row = state.block_pos[0]  # frame row = game y
    block_col = state.block_pos[1]  # frame col = game x

    # Normalize cursor to x=34 before UP moves. The x=29 column (and others)
    # have ihdgageizm walls at y=30/35/40 that block the UP path. x=34 is clear.
    col_diff = (block_col - STANDARD_COL) // 5
    if col_diff > 0:
        prefix = [LEFT] * col_diff
    elif col_diff < 0:
        prefix = [RIGHT] * (-col_diff)
    else:
        prefix = []

    ups_1 = max(0, (block_row - DETOUR_ROW) // 5)
    ups_2 = (DETOUR_ROW - FINAL_ROW) // 5   # always 3: (25-10)//5

    return (
        prefix          +          # normalize cursor to x=34 corridor first
        [UP]    * ups_1 +          # ascend to y=25 along x=34 (walls-free corridor)
        [LEFT]  * 3     +          # traverse to x=19 along y=25 (walls-free corridor)
        [DOWN]  * 1     +          # drop to rhsxkxzdjz at y=30 (rotation trigger)
        [UP]    * 1     +          # return to y=25
        [RIGHT] * 3     +          # return to x=34 along y=25
        [UP]    * ups_2            # ascend to goal at y=10
    )


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

    if before_pos is None and after_pos is None:
        return StepResult(
            success=False,
            reason="transition: block not visible in before or after frame",
            delta={"before_pos": None, "after_pos": None,
                   "row_delta": None, "col_delta": None},
        )

    if before_pos is None:
        # Block was invisible (reset/animation frame) and reappeared — not a real failure
        return StepResult(
            success=True,
            reason=f"reset: block reappeared at {after_pos}",
            delta={"before_pos": None, "after_pos": after_pos,
                   "row_delta": None, "col_delta": None},
        )

    if after_pos is None:
        return StepResult(
            success=False,
            reason="transition: block disappeared (reset animation frame)",
            delta={"before_pos": before_pos, "after_pos": None,
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
