"""
games/re86/detector.py — Adaptive detector for re86 (ARC-AGI-3).

re86 Level 1 is a PIECE PLACEMENT puzzle with two cross-shaped pieces
(color 9, 27x27 and color 11, 23x23). ACTION5 cycles the active piece
(its center pixel renders color 0); ACTION1-4 move it 3px per action.
Win: the pieces cover their target positions, marked by small marker
pixels of the matching color (arm endpoints: two share the target center
row, two share the target center column).

Everything is frame-derived (hidden variants translate layouts):
  - active piece center: the unique color-0 pixel; its piece color is read
    from the neighboring pixels
  - each piece's target center: among that color's pixels, the small marker
    clusters (the big cluster is the piece itself) — the duplicated row is
    the target center row, the duplicated column the target center column
  - the inactive piece center: bbox center of its big cluster

Route: move active piece to its target (vertical then horizontal), CYCLE,
move the second piece to its target.

Action index mapping:
  0=UP(dy=-3) 1=DOWN(dy=+3) 2=LEFT(dx=-3) 3=RIGHT(dx=+3) 4=CYCLE(ACTION5)
"""

from collections import Counter
from dataclasses import dataclass

import numpy as np

UP, DOWN, LEFT, RIGHT, CYCLE = 0, 1, 2, 3, 4
_STEP = 3
_PIECE_COLORS = (9, 11)


@dataclass
class GameState:
    active_center: tuple | None = None    # (row, col) of the color-0 pixel
    active_color: int | None = None
    targets: dict | None = None           # {color: (row, col) target center}
    other_center: tuple | None = None     # inactive piece cross center
    other_color: int | None = None
    detected: bool = False


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


def _clusters(grid: np.ndarray, color: int) -> list:
    """8-connected clusters of color → list of sets of (r, c)."""
    remaining = {(int(r), int(c)) for r, c in np.argwhere(grid == color)}
    out = []
    while remaining:
        stack = [next(iter(remaining))]
        cluster = set()
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
        out.append(cluster)
    return out


def _target_center(clusters: list) -> tuple | None:
    """Markers = small clusters; duplicated row/col among them = target center."""
    markers = [cl for cl in clusters if len(cl) <= 4]
    pts = [next(iter(cl)) for cl in markers]
    if len(pts) < 3:
        return None
    row_dup = [r for r, n in Counter(r for r, _ in pts).items() if n >= 2]
    col_dup = [c for c, n in Counter(c for _, c in pts).items() if n >= 2]
    if not row_dup or not col_dup:
        return None
    return (row_dup[0], col_dup[0])


def _piece_center(clusters: list) -> tuple | None:
    big = max(clusters, key=len, default=None)
    if not big or len(big) < 20:
        return None
    rs = [r for r, _ in big]
    cs = [c for _, c in big]
    return ((min(rs) + max(rs)) // 2, (min(cs) + max(cs)) // 2)


def detect_state(grid: np.ndarray) -> GameState:
    g = np.asarray(grid)
    pos0 = np.argwhere(g == 0)
    if len(pos0) != 1:
        return GameState()
    ar, ac = int(pos0[0][0]), int(pos0[0][1])

    # Active piece color from the center pixel's neighbors
    neigh = [int(g[ar + dr, ac + dc]) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
             if (dr or dc) and 0 <= ar + dr < g.shape[0] and 0 <= ac + dc < g.shape[1]]
    active_color = next((v for v in neigh if v in _PIECE_COLORS), None)
    if active_color is None:
        return GameState()
    other_color = 11 if active_color == 9 else 9

    targets = {}
    for color in _PIECE_COLORS:
        cl = _clusters(g, color)
        tc = _target_center(cl)
        if tc is None:
            return GameState()
        targets[color] = tc
        if color == other_color:
            other_center = _piece_center(cl)

    if other_center is None:
        return GameState()
    return GameState(active_center=(ar, ac), active_color=active_color,
                     targets=targets, other_center=other_center,
                     other_color=other_color, detected=True)


def _legs(cur: tuple, target: tuple) -> list:
    dr, dc = target[0] - cur[0], target[1] - cur[1]
    if dr % _STEP or dc % _STEP:
        return []
    route = [UP if dr < 0 else DOWN] * (abs(dr) // _STEP)
    route += [LEFT if dc < 0 else RIGHT] * (abs(dc) // _STEP)
    return route


def compute_route(state: GameState, level_num: int = 1) -> list:
    if level_num != 1 or not state.detected:
        return []
    a = _legs(state.active_center, state.targets[state.active_color])
    b = _legs(state.other_center, state.targets[state.other_color])
    return a + [CYCLE] + b


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    return StepResult(success=True, reason="unverified (re86)", delta={})


def format_companion_block(state: GameState, route: list) -> str:
    return (
        f"[strategy game=re86 level=1 type=piece-placement version=2]\n"
        f"active: center={state.active_center} color={state.active_color}\n"
        f"other: center={state.other_center} color={state.other_color}\n"
        f"targets: {state.targets}\n"
        f"route_len: {len(route)}\n"
        "[/strategy]"
    )
