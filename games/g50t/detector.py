"""
games/g50t/detector.py — L1 solver for g50t (recording/replay maze puzzle).

Mechanics (L1):
  - Player moves a "goal" cursor (7x7) through the body of a large player sprite
  - Obstacle (door) at (13,37) blocks the direct downward path
  - Button at (37,7): when goal arrives here, door opens (slides right to (19,37))
  - Two-stage recording mechanic (ACTION5 = submit):
      Stage 0: record path to press button → RIGHT*4 to (37,7), submit with ACTION5
      Stage 1: ghost replays path 1 (holds button open), navigate goal to win target
  - Win: tracker sprite (gilbljmfbc) at (42,48) → goal must reach (43,49) = tracker+(1,1)
  - Route: [RIGHT*4, ACTION5, DOWN*7, RIGHT*5] = 17 actions

Action indices (available_actions=[1,2,3,4,5] → indices 0-4):
  0=UP(ACTION1), 1=DOWN(ACTION2), 2=LEFT(ACTION3), 3=RIGHT(ACTION4), 4=SUBMIT(ACTION5)
"""

from dataclasses import dataclass
import numpy as np


@dataclass
class GameState:
    level_num: int = 1


# Fixed L1 route: RIGHT*4, ACTION5(submit), DOWN*7, RIGHT*5
_L1_ROUTE = [3, 3, 3, 3, 4, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 3, 3]


def detect_state(grid: np.ndarray) -> GameState:
    return GameState(level_num=1)


def compute_route(state: GameState, level_num: int = 1) -> list[int]:
    if level_num != 1:
        return []
    return list(_L1_ROUTE)
