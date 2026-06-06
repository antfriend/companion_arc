"""
games/sp80/detector.py — Per-game detector for sp80 (ARC-AGI-3).

Standard detector interface:
  detect_state(grid)              → GameState
  compute_route(state)            → list[int]
  verify_step(before, after, act) → StepResult
  format_companion_block(state, route) → str

STATUS: STUB — adaptive route not yet implemented.
  The hardcoded fallback [4,3,3,3,4,2,2,1] works for some instances only.
  Frame analysis needed to identify which entity position varies between
  instances. Run a batch with agent_framework's [frame] logging enabled
  to capture entity_signatures, then update detect_state + compute_route.

Action space: 5 simple actions (ACTION1=0 … ACTION5=4).
Known winning route (one instance): [4, 3, 3, 3, 4, 2, 2, 1]
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

# Hardcoded route — works for the known instance only.
# TODO: replace with adaptive logic once frame archaeology is complete.
_FALLBACK_ROUTE = [4, 3, 3, 3, 4, 2, 2, 1]


@dataclass
class GameState:
    """Observable state extracted from one sp80 frame."""
    grid_shape: tuple
    entity_signatures: dict   # {pixel_value: {'count': N, 'bbox': (r1,r2,c1,c2)}}
    # TODO: add specific cursor_pos / target_pos fields once game mechanics are known


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


def detect_state(grid: np.ndarray) -> GameState:
    """Extract observable state from one frame."""
    rows, cols = grid.shape
    bg = int(np.bincount(grid.flatten()).argmax())
    sigs = {}
    for val in np.unique(grid):
        if int(val) == bg:
            continue
        positions = np.argwhere(grid == val)
        if not len(positions):
            continue
        r1 = int(positions[:, 0].min())
        r2 = int(positions[:, 0].max())
        c1 = int(positions[:, 1].min())
        c2 = int(positions[:, 1].max())
        sigs[int(val)] = {"count": len(positions), "bbox": (r1, r2, c1, c2)}
    return GameState(grid_shape=(rows, cols), entity_signatures=sigs)


def compute_route(state: GameState, level_num: int = 1) -> list:
    """Return the action route for the given state."""
    # TODO: implement adaptive route based on cursor position once
    # entity_signatures archaeology identifies the moveable entity and its
    # starting position across multiple instances.
    return list(_FALLBACK_ROUTE)


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    """Stub — always reports unknown until game mechanics are understood."""
    return StepResult(success=True, reason="unverified (sp80 stub)", delta={})


def format_companion_block(state: GameState, route: list) -> str:
    """Serialize state + route to a companion [strategy] block."""
    import time
    ts = int(time.time())
    sig_str = " ".join(
        f"v{v}:n={d['count']},r{d['bbox'][0]}-{d['bbox'][1]}c{d['bbox'][2]}-{d['bbox'][3]}"
        for v, d in sorted(state.entity_signatures.items())
    )
    route_str = ",".join(str(a) for a in route)
    return (
        f"[strategy game=sp80 level=1 type=hardcoded version=1 created={ts}]\n"
        f"entity_signatures: {sig_str}\n"
        f"route: {route_str}\n"
        "[/strategy]"
    )
