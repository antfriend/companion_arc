"""
games/ar25/detector.py — Stub detector for ar25 (ARC-AGI-3).

Not yet implemented. Returns empty route from all interface functions.
Replace detect_state / compute_route / verify_step once the mechanic is known.
"""

from dataclasses import dataclass
import numpy as np


@dataclass
class GameState:
    grid_shape: tuple
    entity_signatures: dict


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


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
    return GameState(grid_shape=(rows, cols), entity_signatures=sigs)


def compute_route(state: GameState, level_num: int = 1) -> list:
    return []


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    return StepResult(success=True, reason="stub (ar25)", delta={})


def format_companion_block(state: GameState, route: list) -> str:
    return "[strategy game=ar25 level=1 type=stub]\nnot implemented\n[/strategy]"
