"""
games/cd82/detector.py — Per-game detector for cd82 (ARC-AGI-3).

cd82 is a basket-firing puzzle. 8 baskets sit on a ring around a 3×3
navigation grid with the center (1,1) forbidden. The player navigates the
"ActiveBasket" selector with ACTION1-4 (row/col ±1) then fires ACTION5
to paint a rectangular region of the 10×10 canvas.

Level 1 target (pqwme1-1): canvas rows 5-9 = color 15, rows 0-4 = 0.
→ Navigate to basket 4 (bottom, grid (2,1)) and fire with default color 15.

Variable state: on step 0 (obs=None → in_offline=False) the agent takes a
random action before the first frame is captured. This may move the active
basket away from its default starting position (basket 0, grid (0,1)).
detect_state() reads the active basket from the first observed frame and
compute_route() plans the minimal path to basket 4 avoiding the center.

Action index mapping (ArcAgent route):
  0=ACTION1 (row-1)  1=ACTION2 (row+1)  2=ACTION3 (col-1)  3=ACTION4 (col+1)
  4=ACTION5 (fire)

Basket ring layout (3×3 nav grid):
  7(0,0)  0(0,1)  1(0,2)
  6(1,0)  [ctr]   2(1,2)
  5(2,0)  4(2,1)  3(2,2)
"""

from dataclasses import dataclass

import numpy as np

# Frame bounding-box minimum corner (r_min, c_min) of the v2 (border) pixels
# for each basket's ActiveBasket sprite → nav grid position (row, col).
# Basket 0 (horizontal, x=25,y=24):  r24-32, c25-38  → (0,1)
# Basket 1 (diagonal,   x=33,y=21):  r21-37, c33-49  → (0,2)
# Basket 2 (horizontal, x=38,y=32):  r32-45, c38-46  → (1,2)
# Basket 3 (diagonal,   x=33,y=40):  r40-56, c33-49  → (2,2)
# Basket 4 (horizontal, x=25,y=45):  r45-53, c25-38  → (2,1)  ← L1 target
# Basket 5 (diagonal,   x=14,y=40):  r40-56, c14-30  → (2,0)
# Basket 6 (horizontal, x=17,y=32):  r32-45, c17-25  → (1,0)
# Basket 7 (diagonal,   x=14,y=21):  r21-37, c14-30  → (0,0)
_BASKET_BY_FRAME_POS: dict = {
    (24, 25): (0, 1),
    (21, 33): (0, 2),
    (32, 38): (1, 2),
    (40, 33): (2, 2),
    (45, 25): (2, 1),
    (40, 14): (2, 0),
    (32, 17): (1, 0),
    (21, 14): (0, 0),
}

# Minimal action sequences to navigate from each grid position to basket 4 at (2,1).
# All paths avoid the forbidden center (1,1).
# Actions: 0=row-1  1=row+1  2=col-1  3=col+1
_NAV_TO_B4: dict = {
    (0, 0): [1, 1, 3],     # basket 7: down→(1,0), down→(2,0), right→(2,1)
    (0, 1): [3, 1, 1, 2],  # basket 0: right→(0,2), down→(1,2), down→(2,2), left→(2,1)
    (0, 2): [1, 1, 2],     # basket 1: down→(1,2), down→(2,2), left→(2,1)
    (1, 0): [1, 3],        # basket 6: down→(2,0), right→(2,1)
    (1, 2): [1, 2],        # basket 2: down→(2,2), left→(2,1)
    (2, 0): [3],           # basket 5: right→(2,1)
    (2, 1): [],            # basket 4: already there
    (2, 2): [2],           # basket 3: left→(2,1)
}

FIRE = 4  # ACTION5


@dataclass
class GameState:
    """Observable state extracted from one cd82 frame."""
    grid_shape: tuple
    entity_signatures: dict   # {pixel_value: {'count': N, 'bbox': (r1,r2,c1,c2)}}
    basket_grid_pos: tuple    # (row, col) in 3×3 nav grid; default (0,1) if undetected
    basket_detected: bool     # True if v2 bbox matched a known basket position
    canvas_dirty: bool        # True if canvas rows 0-4 already painted (L1 cannot be won)


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


def detect_state(grid: np.ndarray) -> GameState:
    """Extract active basket position from one frame."""
    rows, cols = grid.shape
    bg = int(np.bincount(grid.flatten()).argmax())

    sigs: dict = {}
    for val in np.unique(grid):
        if int(val) == bg:
            continue
        pos = np.argwhere(grid == val)
        if not len(pos):
            continue
        r1 = int(pos[:, 0].min())
        r2 = int(pos[:, 0].max())
        c1 = int(pos[:, 1].min())
        c2 = int(pos[:, 1].max())
        sigs[int(val)] = {"count": len(pos), "bbox": (r1, r2, c1, c2)}

    # Identify active basket from pixel-2 (border) entity
    basket_grid_pos = (0, 1)  # default: assume basket 0
    detected = False
    if 2 in sigs:
        r1, _r2, c1, _c2 = sigs[2]["bbox"]
        key = (r1, c1)
        if key in _BASKET_BY_FRAME_POS:
            basket_grid_pos = _BASKET_BY_FRAME_POS[key]
            detected = True
        else:
            # Nearest-neighbor fallback within 4px tolerance (handles minor rendering offsets)
            best_d, best_pos = float("inf"), None
            for (kr, kc), gpos in _BASKET_BY_FRAME_POS.items():
                d = (r1 - kr) ** 2 + (c1 - kc) ** 2
                if d < best_d:
                    best_d, best_pos = d, gpos
            if best_d <= 16:
                basket_grid_pos = best_pos
                detected = True

    # Canvas dirtiness: xytrjjbyib canvas at game(x=27, y=34) = frame rows 34-43, cols 27-36.
    # If canvas rows 0-4 (frame rows 34-38) are filled with 15, L1 target cannot be matched.
    canvas_top = grid[34:39, 27:37]
    canvas_dirty = bool((canvas_top == 15).any())

    return GameState(
        grid_shape=(rows, cols),
        entity_signatures=sigs,
        basket_grid_pos=basket_grid_pos,
        basket_detected=detected,
        canvas_dirty=canvas_dirty,
    )


def compute_route(state: GameState, level_num: int = 1) -> list:
    """Return action route for the given level.

    L1: navigate from detected basket to basket 4 (grid (2,1)), then fire.
    L2+: not achievable with simple actions only (requires color-select ACTION6).
    """
    if level_num != 1:
        return []

    nav = _NAV_TO_B4.get(state.basket_grid_pos, _NAV_TO_B4[(0, 1)])
    return nav + [FIRE]


def verify_step(before: np.ndarray, after: np.ndarray, action: int) -> StepResult:
    """Stub — always reports unverified."""
    return StepResult(success=True, reason="unverified (cd82)", delta={})


def format_companion_block(state: GameState, route: list) -> str:
    """Serialize state + route to a companion [strategy] block."""
    import time
    ts = int(time.time())
    route_str = ",".join(str(a) for a in route)
    return (
        f"[strategy game=cd82 level=1 type=adaptive version=1 created={ts}]\n"
        f"basket_grid_pos={state.basket_grid_pos} detected={state.basket_detected}"
        f" canvas_dirty={state.canvas_dirty}\n"
        f"route: {route_str}\n"
        "[/strategy]"
    )
