"""wa30 detector — adaptive delivery puzzle, L1 only.

Game: cursor (color-0 direction-edge + color-14 body, 4x4 sprite) picks up items
(color-4 border + color-9 interior, 4x4) and delivers them to a drop zone
(color-9 border + color-2 interior). 5 actions: 0=UP, 1=DOWN, 2=LEFT, 3=RIGHT, 4=PICKUP/DROP.

celomdfhbh = 4 (step size). All positions multiples of 4.
L1 only: no adversaries, 200 step budget, 3 items, one drop zone.
"""
import numpy as np
from collections import deque

STEP = 4
DIRS = [(0, -STEP), (0, STEP), (-STEP, 0), (STEP, 0)]


def detect_state(grid):
    """Extract game state from frame. Returns dict or None."""
    frame = grid[:63, :]  # exclude progress-bar row 63

    # --- Cursor: color-0 direction edge (4 pixels in a line on one side of 4x4 sprite) ---
    pos0 = np.argwhere(frame == 0)
    if len(pos0) == 0:
        return None
    rows0 = pos0[:, 0].astype(int)
    cols0 = pos0[:, 1].astype(int)
    r_min, r_max = int(rows0.min()), int(rows0.max())
    c_min = int(cols0.min())

    if r_min == r_max:  # horizontal edge — rotation 0 (top) or 180 (bottom)
        r, c = r_min, c_min
        body_below = r + 1 < 63 and int(frame[r + 1, c]) == 14
        if body_below:
            cursor_x, cursor_y = c, r       # rotation 0: top edge, body below
        else:
            cursor_x, cursor_y = c, r - 3   # rotation 180: bottom edge, body above
    else:  # vertical edge — rotation 90 (right) or 270 (left)
        r, c = r_min, c_min
        body_left = c > 0 and int(frame[r, c - 1]) == 14
        if body_left:
            cursor_x, cursor_y = c - 3, r   # rotation 90: right edge, body to left
        else:
            cursor_x, cursor_y = c, r       # rotation 270: left edge, body to right

    # All entities live on the same STEP lattice as the cursor; derive the
    # lattice phase from the cursor so shifted (hidden-variant) layouts work.
    phase_x = cursor_x % STEP
    phase_y = cursor_y % STEP

    def snap(v: int, phase: int) -> int:
        return ((v - phase) // STEP) * STEP + phase

    # --- Drop zone: color-2 interior → derive valid item placement positions ---
    pos2 = np.argwhere(frame == 2)
    dz_valid = set()
    if len(pos2) > 0:
        dz_y0 = int(pos2[:, 0].min()) - 1   # sprite TL row (1 row inside border)
        dz_y1 = int(pos2[:, 0].max()) + 1   # sprite BR row
        dz_x0 = int(pos2[:, 1].min()) - 1
        dz_x1 = int(pos2[:, 1].max()) + 1
        for y in range(dz_y0, dz_y1 + 1):
            for x in range(dz_x0, dz_x1 + 1):
                if x % STEP == phase_x and y % STEP == phase_y:
                    dz_valid.add((x, y))

    # --- Items: color-4 clusters, snap to the phased STEP lattice ---
    pos4 = np.argwhere(frame == 4)
    seen_cells = set()
    items = []
    for row, col in pos4:
        cell = (snap(int(col), phase_x), snap(int(row), phase_y))
        if cell not in seen_cells:
            seen_cells.add(cell)
            if cell not in dz_valid:
                items.append(cell)

    return {
        'cursor_x': cursor_x,
        'cursor_y': cursor_y,
        'items': items,
        'dz_valid': dz_valid,
    }


def _bfs(start, goals, blocked):
    """BFS from start to nearest goal in goals set. Returns (path_of_(dx,dy), goal)."""
    if start in goals:
        return [], start
    q = deque([(start, [])])
    seen = {start}
    while q:
        pos, path = q.popleft()
        for dx, dy in DIRS:
            npos = (pos[0] + dx, pos[1] + dy)
            if npos in goals:
                return path + [(dx, dy)], npos
            if (npos not in seen and npos not in blocked
                    and 0 <= npos[0] <= 60 and 0 <= npos[1] <= 60):
                seen.add(npos)
                q.append((npos, path + [(dx, dy)]))
    return None, None


def _carry_bfs(start, goals, item_off, blocked):
    """BFS while carrying item at fixed offset; both cursor and item must avoid blocked."""
    if start in goals:
        return [], start
    q = deque([(start, [])])
    seen = {start}
    ox, oy = item_off
    while q:
        pos, path = q.popleft()
        for dx, dy in DIRS:
            npos = (pos[0] + dx, pos[1] + dy)
            ipos = (npos[0] + ox, npos[1] + oy)
            if npos in goals:
                return path + [(dx, dy)], npos
            if (npos not in seen
                    and npos not in blocked
                    and ipos not in blocked
                    and 0 <= npos[0] <= 60 and 0 <= npos[1] <= 60
                    and 0 <= ipos[0] <= 60 and 0 <= ipos[1] <= 60):
                seen.add(npos)
                q.append((npos, path + [(dx, dy)]))
    return None, None


def _act(dx, dy):
    if dy < 0: return 0   # UP
    if dy > 0: return 1   # DOWN
    if dx < 0: return 2   # LEFT
    return 3              # RIGHT


def compute_route(state, level_num):
    """Return list of action indices for L1. Returns [] for other levels."""
    if level_num != 1 or state is None:
        return []

    cursor = (state['cursor_x'], state['cursor_y'])
    unplaced = list(state['items'])
    dz_valid = state['dz_valid']
    placed = set()
    route = []

    while unplaced:
        # Pick nearest undelivered item
        item = min(unplaced, key=lambda i: abs(i[0] - cursor[0]) + abs(i[1] - cursor[1]))
        unplaced.remove(item)
        others = set(unplaced) | placed  # all items that block movement

        # Approach: BFS to an adjacent cell around item
        approach_goals = set()
        for dx, dy in DIRS:
            ap = (item[0] + dx, item[1] + dy)
            if 0 <= ap[0] <= 60 and 0 <= ap[1] <= 60 and ap not in others:
                approach_goals.add(ap)
        if not approach_goals:
            continue

        path, approach = _bfs(cursor, approach_goals, others | {item})
        if path is None:
            continue

        for dx, dy in path:
            route.append(_act(dx, dy))
        cursor = approach

        # Rotate to face item: issue a blocked move toward item (cursor stays, rotates)
        face_dx, face_dy = item[0] - cursor[0], item[1] - cursor[1]
        route.append(_act(face_dx, face_dy))  # blocked by item; costs 1 step

        # Pickup (ACTION5 = index 4)
        route.append(4)

        item_off = (item[0] - cursor[0], item[1] - cursor[1])
        carry_blocked = set(unplaced) | placed

        # Carry to drop zone: compute cursor positions where item lands in dz_valid
        drop_goals = set()
        for dz in dz_valid:
            cx, cy = dz[0] - item_off[0], dz[1] - item_off[1]
            if (0 <= cx <= 60 and 0 <= cy <= 60
                    and (cx, cy) not in carry_blocked
                    and (cx + item_off[0], cy + item_off[1]) not in carry_blocked):
                drop_goals.add((cx, cy))
        if not drop_goals:
            continue

        carry_path, drop_pos = _carry_bfs(cursor, drop_goals, item_off, carry_blocked)
        if carry_path is None:
            continue

        for dx, dy in carry_path:
            route.append(_act(dx, dy))
        cursor = drop_pos

        # Drop (ACTION5 = index 4)
        route.append(4)
        placed.add((cursor[0] + item_off[0], cursor[1] + item_off[1]))

    return route
