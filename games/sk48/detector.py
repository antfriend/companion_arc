"""
games/sk48/detector.py — frame reader for sk48 (ARC-AGI-3).

sk48 = snake/sokoban hybrid. A horizontal "snake" (a colour-6 bordered head box at
the left, anchored at game-x=11, plus colour-1/2 striped body segments extending
rightward) pushes coloured blocks around a grid so the first segments spell a target
sequence shown in a bottom HUD. ACTION1/2 slide the snake UP/DOWN along a colour-3
rail; ACTION3 retracts (pulls a segment back, pushing blocks left); ACTION4 extends
(grows a segment right, pushing blocks right). Win = the segment row matches the HUD
order (games/sk48/bfs_solver.py is the forward model).

read_state() reconstructs the BFS state (snake row, ncols, blocks, win sequence)
straight from the pixels, so the solver re-derives the route per instance instead of
replaying a hardcoded one. Geometry (verified on instance d8078629):
  - head box: colour-6 6×6 border box, top-left at frame (game_row, 11),
  - blocks: 4×4 uniform non-floor cells at frame (game_y+1 .. +4, game_x+1 .. +4),
    i.e. game (x, y) = (frame_col_left - 1, frame_row_top - 1),
  - snake body: colour-1/2 stripe in the head band's middle rows (game_row+2 .. +3),
  - rail: a 2-col colour-3 strip to the left,
  - HUD: a second colour-6 box low in the frame with the goal blocks left-to-right.
"""

from dataclasses import dataclass
import numpy as np

from games.sk48.bfs_solver import Geom

FLOOR = 4
STEP = 6
_NON_BLOCK = {FLOOR, 6, 0, 1, 2, 5}  # floor, head border/interior, snake stripes, bg


@dataclass
class GameState:
    grid_shape: tuple
    entity_signatures: dict


@dataclass
class StepResult:
    success: bool
    reason: str
    delta: dict


def _block_at(f, gx, gy):
    """The block colour of a 4×4 uniform non-floor cell at game (gx, gy), or None."""
    r0, c0 = gy + 1, gx + 1
    sub = f[r0:r0 + 4, c0:c0 + 4]
    if sub.shape != (4, 4):
        return None
    v = int(sub[0, 0])
    if v == FLOOR or v in (6, 0) or not np.all(sub == v):
        return None
    return v


def read_state(frame):
    """Reconstruct (geom, row, ncols, blocks, win_seq) for bfs_solver.solve_level —
    geometry DERIVED from the frame so it works at any anchor/size (L1, L2, …). Returns
    None if the frame is not a well-formed sk48 board (→ recognize 0.0, defer to floor).
    """
    f = np.asarray(frame)
    if f.ndim != 2:
        return None
    H, W = f.shape
    rows_idx = np.arange(H)[:, None]

    # Head box: a colour-6 6×6 border box in the upper play area. Its left col is the
    # snake anchor (game-x of the head slot); its top row is the snake's start row.
    p6 = np.argwhere((f == 6) & (rows_idx < 50))
    if len(p6) == 0:
        return None
    r0, r1 = int(p6[:, 0].min()), int(p6[:, 0].max())
    c0, c1 = int(p6[:, 1].min()), int(p6[:, 1].max())
    if (r1 - r0) != 5 or (c1 - c0) != 5:
        return None
    anchor_c, row = c0, r0

    # Rail: a tall, ≤2-col colour-3 strip (distinctive — keeps decoys out). Its top
    # bounds how far up the snake can slide.
    p3 = np.argwhere(f == 3)
    if len(p3) == 0:
        return None
    if (p3[:, 1].max() - p3[:, 1].min()) > 2 or (p3[:, 0].max() - p3[:, 0].min()) < 8:
        return None
    rail_r0 = int(p3[:, 0].min())

    # Play field extent: colour-4 in the upper play area (above the HUD). Its right
    # edge bounds the rightmost segment slot.
    field = np.argwhere((f == FLOOR) & (rows_idx < r1) & (rows_idx >= rail_r0 - 6))
    if len(field) == 0:
        return None
    field_right = int(field[:, 1].max())

    # Segment slots: anchor + STEP, while a 4×4 block at that slot fits in the field.
    seg_x = [anchor_c + STEP * i for i in range((field_right - anchor_c) // STEP + 1)
             if anchor_c + STEP * i + 5 <= field_right + 1]
    if len(seg_x) < 3:
        return None
    # Slide rows: start row is the bottom; step up by STEP while the rail allows.
    rows = [row - STEP * k for k in range((row - (rail_r0 - 4)) // STEP + 1)
            if row - STEP * k >= rail_r0 - 4]
    if len(rows) < 2:
        return None
    geom = Geom(seg_x=sorted(seg_x), rows=sorted(rows), step=STEP)

    # ncols: head segment + contiguous striped body segments to the right.
    ncols = 1
    for gx in seg_x[1:]:
        band = f[row + 2:row + 4, gx + 1:gx + 5]
        if band.size and np.any((band == 1) | (band == 2)):
            ncols += 1
        else:
            break

    # Blocks at the grid slots (4×4 centred in each 6×6 cell).
    blocks = {}
    for gy in rows:
        for gx in seg_x[1:]:
            v = _block_at(f, gx, gy)
            if v is not None:
                blocks[(gx, gy)] = v
    if not blocks:
        return None

    # Win sequence: goal block colours left-to-right in the bottom HUD strip.
    hud = f[r1 + 1:]                            # everything below the head box
    win = []
    for c in range(hud.shape[1]):
        col = hud[:, c]
        present = [int(v) for v in np.unique(col) if int(v) not in _NON_BLOCK]
        if present:
            v = present[0]
            if not win or win[-1] != v:
                win.append(v)
    if len(win) < 3 or len(win) != len(blocks):
        return None

    return geom, row, ncols, blocks, win


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
    return StepResult(success=True, reason="stub (sk48)", delta={})


def format_companion_block(state: GameState, route: list) -> str:
    return "[strategy game=sk48 level=1 type=snake-sokoban]\nframe-derived BFS\n[/strategy]"
