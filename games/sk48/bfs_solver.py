"""BFS solver for sk48 Level 1.

Game model:
- Snake horizontal (rotation=0, facing RIGHT)
- Head anchor at x=11 (outside floor bounds)
- Segment positions: x ∈ {11,17,23,29,35,41}, step=6
- Snake row (game y): one of {12,18,24,30,36}
- Blocks (elmjchdqcn): can be at x ∈ {17..41}, y ∈ {12..36}
- Level 1 initial blocks: c8@(41,18), c9@(41,24), c14@(41,30)
- Win: vjfbwggsd = [8, 14, 9] (first 3 blocks in segment order)

Actions: U=slide UP, D=slide DOWN, L=retract (backward), R=extend (forward)
"""

from collections import deque

STEP = 6
SEG_X = [11, 17, 23, 29, 35, 41]
ROWS = [12, 18, 24, 30, 36]
MIN_BX, MAX_BX = 17, 41   # block x: [17,41] (x+6 <= 47)
MIN_BY, MAX_BY = 12, 36   # block y: [12,36] (y+6 <= 42)
RAIL_STARTS = [14, 20, 26, 32]  # rail y-starts (each 8px tall)

# Level 1 initial state
INIT_ROW = 36
INIT_NCOLS = 2
INIT_BLOCKS = {(41, 18): 8, (41, 24): 9, (41, 30): 14}

WIN_SEQ = [8, 14, 9]


def valid_block(x, y):
    return MIN_BX <= x <= MAX_BX and MIN_BY <= y <= MAX_BY


def push_blocks(blocks, x, y, dx, dy):
    """Recursively push block at (x,y) by (dx*STEP, dy*STEP). Returns updated dict or None."""
    nx, ny = x + dx * STEP, y + dy * STEP
    if not valid_block(nx, ny):
        return None
    nb = dict(blocks)
    if (nx, ny) in nb:
        result = push_blocks(nb, nx, ny, dx, dy)
        if result is None:
            return None
        nb = result
    nb[nx, ny] = nb.pop((x, y))
    return nb


def can_slide(row, dy_s):
    """Check if snake at row can slide in direction dy_s (-1=UP, +1=DOWN)."""
    check = row + 2 + dy_s * 3
    return any(rs <= check <= rs + 7 for rs in RAIL_STARTS)


def action_slide(row, ncols, blocks, dy_s):
    """Slide UP/DOWN. Returns (new_row, new_ncols, new_blocks) or None."""
    if not can_slide(row, dy_s):
        return None
    new_row = row + dy_s * STEP
    if new_row not in ROWS:
        return None
    nb = dict(blocks)
    for i in range(ncols):
        sx = SEG_X[i]
        # Process (dx,dy) branch: block at target row needs to be pushed first
        tgt_key = (sx, new_row)
        if tgt_key in nb:
            r = push_blocks(nb, sx, new_row, 0, dy_s)
            if r is None:
                return None  # blocked
            nb = r
        # Process (0,0) branch: block at current row
        cur_key = (sx, row)
        if cur_key in nb:
            r = push_blocks(nb, sx, row, 0, dy_s)
            if r is None:
                return None  # blocked
            nb = r
    return new_row, ncols, nb


def action_retract(row, ncols, blocks):
    """Retract snake (remove seg[0], remaining shift left). Returns (row, ncols-1, blocks) or None."""
    if ncols <= 1:
        return None
    nb = dict(blocks)
    # Segments SEG_X[1..ncols-1] all shift LEFT by STEP simultaneously.
    # Process left-to-right so blocked positions propagate correctly.
    for i in range(1, ncols):
        sx = SEG_X[i]
        tx = SEG_X[i - 1]  # target x for block at sx

        # (dx,dy) branch: block at target x (tx) — needs to be pushed further left
        if valid_block(tx, row) and (tx, row) in nb:
            r = push_blocks(nb, tx, row, -1, 0)
            if r is not None:
                nb = r
            # If fail: block at tx detaches (stays), blocks propagation

        # (0,0) branch: block at current x (sx) — push left to tx
        if (sx, row) in nb:
            if not valid_block(tx, row):
                pass  # tx=11 OOB for blocks, stays
            elif (tx, row) in nb:
                pass  # target still occupied (detached), stays
            else:
                r = push_blocks(nb, sx, row, -1, 0)
                if r is not None:
                    nb = r
    return row, ncols - 1, nb


def action_extend(row, ncols, blocks):
    """Extend snake rightward. Returns (row, ncols+1, blocks) or None."""
    if ncols >= len(SEG_X):
        return None
    last_x = SEG_X[ncols - 1]
    next_x = SEG_X[ncols]
    nb = dict(blocks)

    # (dx,dy) branch: block at target position next_x
    if (next_x, row) in nb:
        r = push_blocks(nb, next_x, row, 1, 0)
        if r is not None:
            nb = r
        # If fail: block detaches at next_x (stays, segment still extends)

    # (0,0) branch: block at last_x
    if (last_x, row) in nb:
        r = push_blocks(nb, last_x, row, 1, 0)
        if r is not None:
            nb = r
        # If fail: block detaches at last_x (stays)

    return row, ncols + 1, nb


def to_state(row, ncols, blocks):
    return (row, ncols, frozenset(blocks.items()))


def from_state(state):
    row, ncols, bfs = state
    return row, ncols, dict(bfs)


def check_win(row, ncols, blocks):
    seq = [blocks[(SEG_X[i], row)] for i in range(ncols) if (SEG_X[i], row) in blocks]
    return seq[:3] == WIN_SEQ


def bfs_solve():
    init = to_state(INIT_ROW, INIT_NCOLS, INIT_BLOCKS)
    queue = deque([(init, [])])
    visited = {init}

    while queue:
        state, path = queue.popleft()
        row, ncols, blocks = from_state(state)

        for action, result in [
            ('U', action_slide(row, ncols, blocks, -1)),
            ('D', action_slide(row, ncols, blocks, +1)),
            ('L', action_retract(row, ncols, blocks)),
            ('R', action_extend(row, ncols, blocks)),
        ]:
            if result is None:
                continue
            new_row, new_ncols, new_blocks = result
            nstate = to_state(new_row, new_ncols, new_blocks)
            if nstate in visited:
                continue
            visited.add(nstate)
            new_path = path + [action]

            if check_win(new_row, new_ncols, new_blocks):
                print(f"\nSOLUTION FOUND! {len(new_path)} steps: {''.join(new_path)}")
                print(f"Final: row={new_row}, ncols={new_ncols}")
                print(f"Blocks: {new_blocks}")
                segs = [(SEG_X[i], new_row) for i in range(new_ncols)]
                vjf = [new_blocks[p] for p in segs if p in new_blocks]
                print(f"vjfbwggsd sequence: {vjf}")
                return new_path, nstate

            if len(new_path) < 60:
                queue.append((nstate, new_path))

    print("No solution found within depth limit")
    return None, None


if __name__ == '__main__':
    print(f"BFS sk48 L1. Initial: row={INIT_ROW}, ncols={INIT_NCOLS}, blocks={INIT_BLOCKS}")
    print(f"Target sequence: {WIN_SEQ}")
    print("Searching...")
    path, final = bfs_solve()
    if path:
        action_map = {'U': 1, 'D': 2, 'L': 3, 'R': 4}
        action_nums = [action_map[a] for a in path]
        print(f"\nGame actions: {action_nums}")
        print(f"Compressed: ", end='')
        prev, cnt = path[0], 1
        for a in path[1:]:
            if a == prev:
                cnt += 1
            else:
                print(f"{prev}*{cnt}" if cnt > 1 else prev, end=' ')
                prev, cnt = a, 1
        print(f"{prev}*{cnt}" if cnt > 1 else prev)
