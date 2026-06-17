"""
games/ls20/solver.py — the ls20 "transform-and-deliver" CORE solver, frame-driven.

ls20 is ONE mechanic at every level: a block carries (shape, color, rotation); changer
tiles cycle each attribute; rings reset a move-timer (single-use); each target admits the
block only when all three attrs match its required appearance; WIN = deliver the block to
every target matching. Levels differ only in CONFIGURATION (L1 = +1 rotation visit; L2 =
+3 + 2 rings; L3 adds a colour change) — so one planner clears them all.

This module is the frame-readable port of the validated prototype (`_solve_ls20.py`):
  - read_spec(frame, level): derive the per-level spec from PIXELS.
  - plan(spec): the proven transform-and-deliver + timer-aware ring-interleaving planner.

SCOPE (this port): COLOUR + ROTATION configs (L1, L2, L3) are fully handled. The block's
ROTATION is read from the left-margin appearance preview (rotation-matched to each target's
drawn 3×3); its COLOUR is read from WHICH palette colour that preview is painted in, and each
target's COLOUR from the palette colour its silhouette is drawn in. If a target needs a SHAPE
change (its silhouette matches the block under NO rotation) and no shape-changer reading exists
yet, read_spec returns None so the supervisor defers to the explorer floor (additive-safe).

Geometry: 5px logical cells; row-cells from R0=5 step 5; col-cells from C0=9 step 5. The 10×10
play grid is rows [5,55) × cols [9,59); UI/previews live in the left margin (cols<9) + bottom.
Colours: 3 track (passable), 5 floor (passable), 4 void; 11 ring; 0/1 cross (rotation changer).
PALETTE = [12,9,14,8] is the block's COLOUR cycle (a fixed source constant `tnkekoeuk`): a
colour-changer visit advances the index by 1. These four are the ONLY palette colours that
appear inside the grid, and ONLY on three things — the mover (a fixed colour-12 head + colour-9
body), the colour-changer (its interior shows ≥3 of them at once), and the targets (each drawn
in its required colour) — which is what makes cell-based detection clean.
"""

from collections import deque

import numpy as np

R0, C0, STEP, NR, NC = 5, 9, 5, 10, 10
PASS = {3, 5, 12, 9, 11, 0, 1}
VOID = 4
BLOCK = 12                       # the mover's head colour (fixed, regardless of block colour)
RING = 11
PALETTE = [12, 9, 14, 8]         # colour cycle order (source `tnkekoeuk`); index = colour attr
SHAPE, COLOR, ROT = 0, 1, 2      # attribute indices
DELTA = {1: (-1, 0), 2: (1, 0), 3: (0, -1), 4: (0, 1)}     # UP DOWN LEFT RIGHT
# Per-window move budget = StepCounter // StepsDecrement. Source: StepCounter=42 every level;
# StepsDecrement=2 on L2/L3 ⇒ 21 moves between ring resets. The budget is CONTINUOUS across
# levels (a new level does NOT refill it), so plan() seeds the FIRST window from the remaining
# steps read off the frame. (Decrement-1 levels get a conservative 21-of-42; harmless there.)
TIMER_WINDOW = 21


# --------------------------------------------------------------------------- geometry
def cell_of_px(r, c):
    return ((r - R0) // STEP, (c - C0) // STEP)


def build_map(f):
    pm = np.zeros((NR, NC), bool)
    for r in range(NR):
        for c in range(NC):
            patch = f[R0 + r * STEP:R0 + r * STEP + STEP, C0 + c * STEP:C0 + c * STEP + STEP]
            nv = patch[patch != VOID]
            pm[r, c] = len(nv) > 0 and int(np.bincount(nv).argmax()) in PASS
    return pm


def bfs(pm, start, goals, blocked=frozenset()):
    goals = set(goals)
    q = deque([(start, [])]); seen = {start}
    while q:
        (r, c), path = q.popleft()
        if (r, c) in goals:
            return path
        for a, (dr, dc) in DELTA.items():
            n = (r + dr, c + dc)
            if 0 <= n[0] < NR and 0 <= n[1] < NC and pm[n] and n not in seen and n not in blocked:
                seen.add(n); q.append((n, path + [a]))
    return None


# --------------------------------------------------------------------------- frame reader
def _clusters(mask):
    """4-connected component bboxes of a boolean mask → list of (r0,r1,c0,c1)."""
    seen = np.zeros_like(mask); out = []
    for sr in range(mask.shape[0]):
        for sc in range(mask.shape[1]):
            if mask[sr, sc] and not seen[sr, sc]:
                q = deque([(sr, sc)]); seen[sr, sc] = True
                r0 = r1 = sr; c0 = c1 = sc
                while q:
                    r, c = q.popleft()
                    r0, r1, c0, c1 = min(r0, r), max(r1, r), min(c0, c), max(c1, c)
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < mask.shape[0] and 0 <= nc < mask.shape[1] and mask[nr, nc] and not seen[nr, nc]:
                            seen[nr, nc] = True; q.append((nr, nc))
                out.append((r0, r1, c0, c1))
    return out


def _shape3(f, r0, r1, c0, c1, color):
    """Downscale a shape's bbox to a 3x3 boolean silhouette of `color` pixels."""
    h, w = r1 - r0 + 1, c1 - c0 + 1
    sig = np.zeros((3, 3), bool)
    for i in range(3):
        for j in range(3):
            rr0 = r0 + (i * h) // 3; rr1 = r0 + ((i + 1) * h) // 3
            cc0 = c0 + (j * w) // 3; cc1 = c0 + ((j + 1) * w) // 3
            blk = f[rr0:max(rr1, rr0 + 1), cc0:max(cc1, cc0 + 1)]
            sig[i, j] = np.any(blk == color)
    return sig


def _rot_delta(block_sig, target_sig):
    """Number of +90° rotations (cross visits) to turn block_sig into target_sig, or None
    if no rotation aligns them (different shape)."""
    for k in range(4):
        if np.array_equal(np.rot90(block_sig, -k), target_sig):   # -k = clockwise k turns
            return k
    return None


def _cell_patch(f, r, c):
    return f[R0 + r * STEP:R0 + r * STEP + STEP, C0 + c * STEP:C0 + c * STEP + STEP]


def _sig_of_color(patch, color):
    """3x3 silhouette of `color` pixels within their tight bbox in `patch`, or None."""
    ys, xs = np.where(patch == color)
    if not len(ys):
        return None
    return _shape3(patch, int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max()), color)


def read_block_cell(frame):
    """The mover's cell from the frame: its colour-12 head, scoped to the play grid (colour-12
    also leaks into the colour-changer interior and the left-margin preview). The head is a
    full 5-wide×2-tall band ⇒ the largest in-grid colour-12 cluster; its top-left = its cell.
    Returns the (row, col) cell or None."""
    f = np.asarray(frame)
    grid = np.zeros(f.shape, bool)
    grid[R0:R0 + NR * STEP, C0:C0 + NC * STEP] = True
    blk_cl = _clusters((f == BLOCK) & grid)
    if not blk_cl:
        return None
    br0, _br1, bc0, _bc1 = max(blk_cl, key=lambda b: (b[1] - b[0] + 1) * (b[3] - b[2] + 1))
    return cell_of_px(br0, bc0)


def read_spec(frame, level=1):
    """Derive the transform-and-deliver spec from the frame. Returns dict or None (defer).

    Returns {pm, block, rings, changers:{COLOR:[cells], ROT:[cells]}, targets:[(cell, deltas)]}
    where deltas = [shape_delta, colour_delta, rot_delta] per target. Returns None if a target
    needs a SHAPE change (silhouette matches under no rotation) — not yet frame-decoded.
    """
    f = np.asarray(frame)
    pm = build_map(f)

    grid = np.zeros(f.shape, bool)
    grid[R0:R0 + NR * STEP, C0:C0 + NC * STEP] = True
    block = read_block_cell(f)
    if block is None:
        return None

    # --- BLOCK colour + shape: the left-margin preview (rows>=50, cols<C0) painted in the
    # block's current palette colour. block_colour_idx = that palette colour's index.
    margin = np.zeros(f.shape, bool)
    margin[50:, :C0] = True
    block_color_idx = None
    block_sig = None
    for idx, col in enumerate(PALETTE):
        m = (f == col) & margin
        if np.any(m):
            ys, xs = np.where(m)
            block_color_idx = idx
            block_sig = _shape3(f, int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max()), col)
            break
    if block_sig is None:
        return None

    # --- rings: small ~3x3 colour-11 squares in the grid (EXCLUDE the wide UI timer bar).
    rings = [cell_of_px((r0 + r1) // 2, (c0 + c1) // 2)
             for r0, r1, c0, c1 in _clusters((f == RING) & grid)
             if (r1 - r0) <= 4 and (c1 - c0) <= 4]

    # --- changers + targets: scan grid cells. Palette colours appear in-grid ONLY on the
    # mover (block cell), the colour-changer (≥3 distinct palette colours at once), and the
    # targets (each a single palette colour = its required colour). The rotation-changer
    # (cross) is the colour-0/1 cell.
    color_changer, rot_changer, targets = [], [], []
    cross_cl = _clusters(((f == 0) | (f == 1)) & grid)
    if cross_cl:
        r0, r1, c0, c1 = max(cross_cl, key=lambda b: (b[1] - b[0] + 1) * (b[3] - b[2] + 1))
        rot_changer = [cell_of_px((r0 + r1) // 2, (c0 + c1) // 2)]

    for r in range(NR):
        for c in range(NC):
            if (r, c) == block:
                continue
            patch = _cell_patch(f, r, c)
            present = [col for col in PALETTE if np.any(patch == col)]
            if not present:
                continue
            if len(present) >= 3:                          # colour-changer signature
                color_changer = [(r, c)]
                continue
            # a target: drawn in its required colour (the dominant palette colour here)
            tcol = max(present, key=lambda col: int(np.count_nonzero(patch == col)))
            tcol_idx = PALETTE.index(tcol)
            tgt_sig = _sig_of_color(patch, tcol)
            rd = _rot_delta(block_sig, tgt_sig)
            if rd is None:
                return None                                # shape change needed → defer
            cd = (tcol_idx - block_color_idx) % len(PALETTE)
            targets.append(((r, c), [0, cd, rd]))

    if not targets:
        return None
    # a needed colour change with no readable colour-changer ⇒ defer
    if any(d[COLOR] for _, d in targets) and not color_changer:
        return None
    changers = {COLOR: color_changer, ROT: rot_changer}
    # TIMER: the move-budget is CONTINUOUS across levels (a new level does NOT refill it), so
    # read the CURRENT remaining steps from the bottom timer bar (color-11 columns in row 61).
    steps = int(np.count_nonzero(f[61] == RING))
    return {"pm": pm, "block": block, "rings": rings, "changers": changers,
            "targets": targets, "steps": steps}


# --------------------------------------------------------------------------- planner
def plan(spec):
    """Transform-and-deliver plan: for each target, for each attribute that needs changing,
    visit that attribute's changer `delta` times (bouncing off a neighbour to re-trigger),
    then deliver — weaving single-use ring resets so no ring-free run exceeds the timer
    window. Returns a list of action ids (1=UP 2=DOWN 3=LEFT 4=RIGHT), or None."""
    pm, block, rings = spec["pm"], spec["block"], list(spec["rings"])
    changers, targets = spec["changers"], spec["targets"]
    # Changers and targets must NOT be crossed in transit (a changer mutates attrs; a
    # non-matching target bounces). Rings MAY be crossed — a crossed ring is a free reset.
    avoid = {c for cs in changers.values() for c in cs} | {t[0] for t in targets}

    def route(a, b):
        return bfs(pm, a, {b}, blocked=avoid - {b})

    def cells_of(start, acts):
        cur2, out = start, []
        for a in acts:
            dr, dc = DELTA[a]; cur2 = (cur2[0] + dr, cur2[1] + dc); out.append(cur2)
        return out

    def nbr_plain(cell):
        for dr, dc in DELTA.values():
            n = (cell[0] + dr, cell[1] + dc)
            if 0 <= n[0] < NR and 0 <= n[1] < NC and pm[n] and n not in avoid and n not in set(rings):
                return n
        return None

    def nearest_changer(start, cells):
        best, bp = None, None
        for cell in cells:
            p = route(start, cell)
            if p is not None and (bp is None or len(p) < len(bp)):
                best, bp = cell, p
        return best

    # waypoints = an ORDERED list of cells the block must LAND on: per target, `delta` landings
    # on that attribute's changer (a repeated cell = re-trigger, realised below by leaving and
    # returning), then the target itself. Re-triggers and resets are interleaved by deliver().
    order = sorted(range(len(targets)),
                   key=lambda i: abs(targets[i][0][0] - block[0]) + abs(targets[i][0][1] - block[1]))
    waypoints, prev = [], block
    for ti in order:
        tcell, deltas = targets[ti]
        for ai in (COLOR, ROT):
            if not deltas[ai]:
                continue
            ch = nearest_changer(prev, changers.get(ai, []))
            if ch is None:
                return None
            waypoints += [ch] * deltas[ai]
            prev = ch
        waypoints.append(tcell); prev = tcell

    def walk(frm, leg, sr, rl):
        """Advance window-position sr along `leg` (from `frm`), consuming any ring crossed
        (single-use, resets the window). Returns end_sr, or None if it expires mid-leg."""
        for c in cells_of(frm, leg):
            sr += 1
            if sr > TIMER_WINDOW:
                return None
            if c in rl:
                rl.discard(c); sr = 0
        return sr

    def land_options(cur, wp, rl):
        """Candidate action-legs that LAND the block on `wp` (re-triggering it if cur==wp by
        leaving and returning). Ordered cheap-first: direct / neighbour-bounce, then via each
        still-unused ring (a productive bounce that ALSO resets the timer). Each is a full leg."""
        cands = []
        if cur != wp:
            d = route(cur, wp)
            if d is not None:
                cands.append(d)
        else:                                          # re-trigger: step off and back on
            nb = nbr_plain(wp)
            if nb is not None:
                a, b = route(cur, nb), route(nb, wp)
                if a and b:
                    cands.append(a + b)
        for r in rl:                                   # leave to a ring (reset) and come back
            a, b = route(cur, r), route(r, wp)
            if a is not None and b is not None and (a + b):
                cands.append(a + b)
        return cands

    # DELIVER the waypoints with timer-aware single-use ring resets. WHEN to reset is the hard
    # part: rings are single-use and the best moment is usually a re-trigger bounce or right
    # before a long delivery leg, not greedily on the first overflow. Search it: a tiny DFS
    # (≤2 rings, short waypoint list) tries cheap legs first and backtracks to route via a ring
    # where needed, returning the first fully-feasible action sequence, or None.
    def deliver(cur, sr, rl, wps):
        if not wps:
            return []
        wp = wps[0]
        for leg in land_options(cur, wp, rl):
            rl2 = set(rl)
            ns = walk(cur, leg, sr, rl2)               # consumes any ring crossed
            if ns is None:
                continue
            rest = deliver(wp, ns, rl2, wps[1:])
            if rest is not None:
                return leg + rest
        return None

    # The move-budget is CONTINUOUS across levels, so SEED the first window from the remaining
    # steps read off the frame (full window = TIMER_WINDOW; `steps` remaining ⇒ steps//2 moves).
    steps = spec.get("steps", TIMER_WINDOW * 2)
    since_reset = max(0, TIMER_WINDOW - steps // 2)
    return deliver(block, since_reset, set(rings), waypoints)
