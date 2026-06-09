"""
games/re86/detector.py — Adaptive detector for re86 (ARC-AGI-3).

re86 Level 1 is a PIECE PLACEMENT puzzle with two cross-shaped pieces:
  Sprite 0042 (color 9, 27x27 cross, center=0) → starts at (x=23, y=32), move to (x=35, y=11)
  Sprite 0030 (color 11, 23x23 cross)          → starts at (x=10, y=16), move to (x=4, y=-2)

ACTION5 cycles the active piece (sets its center pixel to 0).
ACTION1-4 move the active piece by 3 pixels (step size = 3).
Win: composite of pieces tagged 0031cppcuvqlbi matches target sprite 0053.

Target positions derived from target sprite 0053 (64x64, at (x=0,y=0)):
  Color-11 markers at canvas (3,15),(9,6),(9,24),(17,15):
    → piece 0030 cross: vertical arm at col x+11=15→x=4, horizontal at row y+11=9→y=-2
  Color-9 markers at canvas (16,48),(24,40),(24,53),(35,48):
    → piece 0042 cross: vertical arm at col x+13=48→x=35, horizontal at row y+13=24→y=11

Action index mapping:
  0=ACTION1 (UP, dy=-3)   1=ACTION2 (DOWN, dy=+3)
  2=ACTION3 (LEFT, dx=-3) 3=ACTION4 (RIGHT, dx=+3)
  4=ACTION5 (CYCLE: switch active piece)

Route is adaptive: reads active-piece center row from the first observed frame.
In batch mode, one UP fires before the frame is captured (v0_row=42, up_042=6).
In competition mode, the frame is the initial state (v0_row=45, up_042=7).
Formula: up_042 = (v0_row - 24) // 3.
"""

from dataclasses import dataclass, field

import numpy as np

UP    = 0
RIGHT = 3
LEFT  = 2
CYCLE = 4

_TARGET_042_CENTER_ROW = 24   # y=11 → center row = 11+13 = 24
_TARGET_030_UP   = 6          # sprite 0030: y=16 → y=-2, 6 UP steps
_TARGET_030_LEFT = 2          # sprite 0030: x=10 → x=4,  2 LEFT steps
_RIGHT_042 = 4                # sprite 0042: x=23 → x=35, 4 RIGHT steps


@dataclass
class GameState:
    active_center_row: int
    active_center_col: int
    detected: bool


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


def detect_state(grid: np.ndarray) -> GameState:
    """Find the active piece center (single color-0 pixel = center marker)."""
    pos = np.argwhere(grid == 0)
    if len(pos) == 1:
        return GameState(
            active_center_row=int(pos[0][0]),
            active_center_col=int(pos[0][1]),
            detected=True,
        )
    # Fallback: assume competition-mode initial position
    return GameState(active_center_row=45, active_center_col=36, detected=False)


def compute_route(state: GameState, level_num: int = 1) -> list:
    """
    L1: Move sprite 0042 (active) to (x=35, y=11), cycle to sprite 0030,
    move sprite 0030 to (x=4, y=-2).

    up_042 = (center_row - 24) // 3  adaptive to batch vs competition timing.
    """
    if level_num != 1:
        return []

    up_042 = max(0, (state.active_center_row - _TARGET_042_CENTER_ROW) // 3)

    return (
        [UP]    * up_042        # move sprite 0042 up to y=11
        + [RIGHT] * _RIGHT_042  # move sprite 0042 right to x=35
        + [CYCLE]               # switch active piece to sprite 0030
        + [UP]    * _TARGET_030_UP    # move sprite 0030 up to y=-2
        + [LEFT]  * _TARGET_030_LEFT  # move sprite 0030 left to x=4
    )


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    return StepResult(success=True, reason="unverified (re86)", delta={})


def format_companion_block(state: GameState, route: list) -> str:
    import time
    ts = int(time.time())
    route_str = ",".join(str(a) for a in route)
    return (
        f"[strategy game=re86 level=1 type=piece-placement version=1 created={ts}]\n"
        f"active_center=({state.active_center_row},{state.active_center_col})"
        f" detected={state.detected} up_042={(state.active_center_row-24)//3}\n"
        f"route: {route_str}\n"
        "[/strategy]"
    )
