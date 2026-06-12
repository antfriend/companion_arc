"""
games/g50t/detector.py — L1 solver for g50t (recording/replay maze puzzle).

Mechanics (L1):
  - A "goal" cursor (7x7, color-9 block with a color-5 center pixel) moves in
    6px steps within the body of a large color-5 player sprite.
  - A door blocks the direct downward path; a button (isolated 3x3 of color 8)
    opens it while pressed.
  - Two-stage recording (ACTION5 = submit): record a path to the button,
    submit; a ghost replays it (holding the button), goal resets to start,
    then navigate to the win target.
  - Win target: tracker sprite (9x9, color-9 ring around 5x5 color-5 block
    with a color-9 center pixel); goal must reach tracker_pos + (1,1).

Frame-derived (hidden variants translate layouts):
  - goal:    pixel == 5 whose 8 neighbors are all 9 → sprite TL = center-(3,3)
  - tracker: pixel == 9 whose 8 neighbors are all 5 → sprite TL = center-(4,4)
  - button:  color-8 cluster with exactly 9 pixels in a 3x3 bbox
             → sprite TL = bbox min - (2,2)
  Stage step counts = relative distances / 6. Canonical move orders preserved
  (stage 0: horizontal then vertical; stage 1: vertical then horizontal —
  the door sits on the vertical leg and is held open by the ghost).

Caveat: the pre-route burn action (UP) is recorded into stage 0. Canonically
it is wall-blocked (goal starts at the body's top edge) so detection after
the burn still sees the start position. A variant with open space above the
goal would desync stage 1 by one step — accepted risk, noted for round 3.

Action indices: 0=UP, 1=DOWN, 2=LEFT, 3=RIGHT, 4=SUBMIT(ACTION5)
"""

from dataclasses import dataclass

import numpy as np

_STEP = 6


@dataclass
class GameState:
    goal: tuple | None = None      # (x, y) sprite TL
    button: tuple | None = None
    tracker: tuple | None = None
    level_num: int = 1


def _find_center(g: np.ndarray, center_color: int, ring_color: int) -> tuple | None:
    """Find the unique pixel of center_color fully ringed by ring_color."""
    rows, cols = g.shape
    pos = np.argwhere(g == center_color)
    for r, c in pos:
        r, c = int(r), int(c)
        if r < 1 or c < 1 or r >= rows - 1 or c >= cols - 1:
            continue
        ring = g[r - 1:r + 2, c - 1:c + 2].flatten().tolist()
        if all(v == ring_color for i, v in enumerate(ring) if i != 4):
            return (r, c)
    return None


def _find_button(g: np.ndarray) -> tuple | None:
    """Isolated 3x3 block of color 8 (the door's 8-region is larger)."""
    pos = np.argwhere(g == 8)
    if len(pos) == 0:
        return None
    # Cluster by connectivity proxy: group pixels into bbox islands via sort
    remaining = {(int(r), int(c)) for r, c in pos}
    while remaining:
        seed = next(iter(remaining))
        stack, cluster = [seed], set()
        while stack:
            cur = stack.pop()
            if cur not in remaining:
                continue
            remaining.discard(cur)
            cluster.add(cur)
            r, c = cur
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (r + dr, c + dc) in remaining:
                        stack.append((r + dr, c + dc))
        rs = [r for r, _ in cluster]
        cs = [c for _, c in cluster]
        if len(cluster) == 9 and max(rs) - min(rs) == 2 and max(cs) - min(cs) == 2:
            return (min(rs), min(cs))
    return None


def detect_state(grid: np.ndarray) -> GameState:
    g = np.asarray(grid)

    goal_c = _find_center(g, 5, 9)
    tracker_c = _find_center(g, 9, 5)
    button_tl8 = _find_button(g)

    goal = (goal_c[1] - 3, goal_c[0] - 3) if goal_c else None
    tracker = (tracker_c[1] - 4, tracker_c[0] - 4) if tracker_c else None
    button = (button_tl8[1] - 2, button_tl8[0] - 2) if button_tl8 else None
    return GameState(goal=goal, button=button, tracker=tracker)


def _leg(dist: int, pos_idx: int, neg_idx: int) -> list:
    if dist % _STEP != 0:
        raise ValueError(f"distance {dist} not a multiple of {_STEP}")
    n = abs(dist) // _STEP
    return [pos_idx if dist > 0 else neg_idx] * n


def compute_route(state: GameState, level_num: int = 1) -> list:
    if level_num != 1:
        return []
    if state.goal is None or state.button is None or state.tracker is None:
        return []
    gx, gy = state.goal
    bx, by = state.button
    tx, ty = state.tracker[0] + 1, state.tracker[1] + 1

    try:
        route = []
        # Stage 0: goal -> button (horizontal first, canonical order)
        route += _leg(bx - gx, 3, 2)
        route += _leg(by - gy, 1, 0)
        route.append(4)   # submit recording; ghost holds button, goal resets
        # Stage 1: start -> tracker+(1,1) (vertical first — door on this leg
        # is held open by the ghost)
        route += _leg(ty - gy, 1, 0)
        route += _leg(tx - gx, 3, 2)
        return route
    except ValueError:
        return []
