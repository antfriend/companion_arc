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
from dataclasses import dataclass
from typing import List, Optional

STEP = 6
_W = 2          # weighted-A* heuristic weight (speed over optimal route length)


# ===========================================================================
# Geometry-parametric model (level-agnostic) — used by the Dynamic.
#
# The L1 push model below is hardcoded to L1's grid. The competition presents
# the SAME mechanic at other anchors/sizes (L2: head at game-x=5, 4 blocks, a
# taller rail). `Model` lifts the four actions to operate on a `Geom` derived
# from the frame (games/sk48/detector.read_state), so one BFS solves any level.
# ===========================================================================

@dataclass
class Geom:
    seg_x: List[int]        # segment grid-x slots, left→right (head = seg_x[0])
    rows: List[int]         # valid head-top grid rows (slide positions)
    step: int = STEP

    @property
    def min_bx(self):       # first BLOCK slot (the head slot can't hold a block)
        return self.seg_x[1]

    @property
    def max_bx(self):
        return self.seg_x[-1]

    @property
    def min_by(self):
        return min(self.rows)

    @property
    def max_by(self):
        return max(self.rows)


class Model:
    """The L1 push rules (push_blocks / slide / retract / extend / win), lifted
    to an arbitrary Geom. Mirrors the module-level L1 functions exactly except
    the grid constants come from `geom` and a slide is legal iff its destination
    is a real rail row (geom.rows)."""

    def __init__(self, geom: Geom):
        self.g = geom

    def _valid_block(self, x, y):
        g = self.g
        return g.min_bx <= x <= g.max_bx and g.min_by <= y <= g.max_by

    def _push(self, blocks, x, y, dx, dy):
        s = self.g.step
        nx, ny = x + dx * s, y + dy * s
        if not self._valid_block(nx, ny):
            return None
        nb = dict(blocks)
        if (nx, ny) in nb:
            r = self._push(nb, nx, ny, dx, dy)
            if r is None:
                return None
            nb = r
        nb[nx, ny] = nb.pop((x, y))
        return nb

    def slide(self, row, ncols, blocks, dy_s):
        new_row = row + dy_s * self.g.step
        if new_row not in self.g.rows:
            return None
        nb = dict(blocks)
        for i in range(ncols):
            sx = self.g.seg_x[i]
            for key in ((sx, new_row), (sx, row)):
                if key in nb:
                    r = self._push(nb, key[0], key[1], 0, dy_s)
                    if r is None:
                        return None
                    nb = r
        return new_row, ncols, nb

    def retract(self, row, ncols, blocks):
        if ncols <= 1:
            return None
        nb = dict(blocks)
        for i in range(1, ncols):
            sx = self.g.seg_x[i]
            tx = self.g.seg_x[i - 1]
            if self._valid_block(tx, row) and (tx, row) in nb:
                r = self._push(nb, tx, row, -1, 0)
                if r is not None:
                    nb = r
            if (sx, row) in nb:
                if not self._valid_block(tx, row):
                    pass
                elif (tx, row) in nb:
                    pass
                else:
                    r = self._push(nb, sx, row, -1, 0)
                    if r is not None:
                        nb = r
        return row, ncols - 1, nb

    def extend(self, row, ncols, blocks):
        if ncols >= len(self.g.seg_x):
            return None
        last_x = self.g.seg_x[ncols - 1]
        next_x = self.g.seg_x[ncols]
        nb = dict(blocks)
        if (next_x, row) in nb:
            r = self._push(nb, next_x, row, 1, 0)
            if r is not None:
                nb = r
        if (last_x, row) in nb:
            r = self._push(nb, last_x, row, 1, 0)
            if r is not None:
                nb = r
        return row, ncols + 1, nb

    def win(self, row, ncols, blocks, win_seq):
        seq = [blocks[(self.g.seg_x[i], row)]
               for i in range(ncols) if (self.g.seg_x[i], row) in blocks]
        return seq[:len(win_seq)] == list(win_seq)


def _heuristic(geom: Geom, row, ncols, blocks, win_seq) -> int:
    """Lower-bound remaining moves to the win: block displacement to the goal slots
    (win-sequence colours on seg_x[1..] of one shared row) PLUS the snake's own cost to
    slide to that row and extend to cover the blocks. Including the snake terms is what
    keeps a greedy search from thrashing once the blocks are placed but the snake isn't."""
    goal_x = {c: geom.seg_x[1 + j] for j, c in enumerate(win_seq)}
    pos = {}                                    # colour -> (x, y) (first match)
    for (x, y), c in blocks.items():
        pos.setdefault(c, (x, y))
    if any(c not in pos for c in win_seq):
        return 10 ** 6                          # a goal colour vanished — dead end
    from collections import Counter
    target_row = Counter(pos[c][1] for c in win_seq).most_common(1)[0][0]
    h = 0
    for c in win_seq:
        x, y = pos[c]
        h += abs(x - goal_x[c]) // geom.step + abs(y - target_row) // geom.step
    h += abs(row - target_row) // geom.step               # slide the snake to that row
    h += max(0, (len(win_seq) + 1) - ncols)               # extend to cover the blocks
    return h


def solve_level(geom: Geom, init_row, init_ncols, init_blocks, win_seq,
                max_depth=80, max_expansions=400_000) -> Optional[List[str]]:
    """Frame-derived, level-agnostic A* over the push model. Returns an action path
    ['U'/'D'/'L'/'R', ...] or None (→ the dynamic defers to the floor). Bounded by
    max_expansions so a pathological hidden variant can't hang — it just defers."""
    import heapq
    win_seq = list(win_seq)
    M = Model(geom)

    def key(row, ncols, blocks):
        return (row, ncols, tuple(sorted(blocks.items())))

    start = (init_row, init_ncols, dict(init_blocks))
    h0 = _heuristic(geom, init_row, init_ncols, init_blocks, win_seq)
    # heap entries: (f, tie, g, row, ncols, blocks, path)
    heap = [(h0, 0, 0, init_row, init_ncols, dict(init_blocks), [])]
    best_g = {key(*start): 0}
    tie = 1
    expansions = 0
    while heap:
        f, _, g, row, ncols, blocks, path = heapq.heappop(heap)
        if g > best_g.get(key(row, ncols, blocks), g):
            continue
        expansions += 1
        if expansions > max_expansions:
            return None
        for action, result in (('U', M.slide(row, ncols, blocks, -1)),
                               ('D', M.slide(row, ncols, blocks, +1)),
                               ('L', M.retract(row, ncols, blocks)),
                               ('R', M.extend(row, ncols, blocks))):
            if result is None:
                continue
            nr, nc, nb = result
            if M.win(nr, nc, nb, win_seq):
                return path + [action]
            ng = g + 1
            if ng >= max_depth:
                continue
            k = key(nr, nc, nb)
            if ng < best_g.get(k, max_depth + 1):
                best_g[k] = ng
                h = _heuristic(geom, nr, nc, nb, win_seq)
                # Weighted A* (W=_W): the push model makes the displacement heuristic a
                # loose under-estimate, so plain A* ≈ BFS. Weighting trades optimality
                # for speed — any route within budget wins the level just the same.
                heapq.heappush(heap, (ng + _W * h, tie, ng, nr, nc, nb, path + [action]))
                tie += 1
    return None
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


def solve(init_row, init_ncols, init_blocks, win_seq, max_depth=60):
    """Frame-derived BFS: plan a winning action path ['U'/'D'/'L'/'R', ...] from a
    state READ off the pixels (detector.read_state), not the hardcoded INIT. Returns
    None if no win is reachable within max_depth (→ the dynamic defers to the floor)."""
    win_seq = list(win_seq)[:3]

    def _win(row, ncols, blocks):
        seq = [blocks[(SEG_X[i], row)] for i in range(ncols) if (SEG_X[i], row) in blocks]
        return seq[:len(win_seq)] == win_seq

    init = to_state(init_row, init_ncols, dict(init_blocks))
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
            nr, nc, nb = result
            ns = to_state(nr, nc, nb)
            if ns in visited:
                continue
            visited.add(ns)
            npath = path + [action]
            if _win(nr, nc, nb):
                return npath
            if len(npath) < max_depth:
                queue.append((ns, npath))
    return None


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
