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

SCOPE (this port): rotation-only configs (L1, L2) are fully handled. If a target also needs
a SHAPE or COLOUR change (L3+), read_spec returns None so the supervisor defers to the
explorer floor (additive-safe) until the colour/shape changer reading is added.

Geometry: 5px logical cells; row-cells from R0=5 step 5; col-cells from C0=9 step 5.
Colours: 3 track (passable), 5 floor (passable), 4 void; 12 block; 11 ring; 0/1 cross
(rotation changer); 9 the shape paint colour used by the appearance previews.
"""

from collections import deque

import numpy as np

R0, C0, STEP, NR, NC = 5, 9, 5, 10, 10
PASS = {3, 5, 12, 9, 11, 0, 1}
VOID = 4
BLOCK = 12
RING = 11
DELTA = {1: (-1, 0), 2: (1, 0), 3: (0, -1), 4: (0, 1)}     # UP DOWN LEFT RIGHT
TIMER_WINDOW = 23


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


def read_spec(frame, level=1):
    """Derive the transform-and-deliver spec from the frame. Returns dict or None (defer).

    Returns {pm, block, rings, cross, targets:[(cell, rot_delta)]} for rotation-only
    configs; None if a target needs a shape/colour change not yet frame-decoded.
    """
    f = np.asarray(frame)
    pm = build_map(f)

    blk = np.argwhere(f == BLOCK)
    if not len(blk):
        return None
    block = cell_of_px(int(blk[:, 0].min()), int(blk[:, 1].min()))

    # rings are small ~3x3 colour-11 squares; EXCLUDE the wide colour-11 timer bar.
    rings = [cell_of_px((r0 + r1) // 2, (c0 + c1) // 2)
             for r0, r1, c0, c1 in _clusters(f == RING)
             if (r1 - r0) <= 4 and (c1 - c0) <= 4]
    cross_cl = _clusters((f == 0) | (f == 1))
    if not cross_cl:
        return None
    r0, r1, c0, c1 = max(cross_cl, key=lambda b: (b[1] - b[0]) * (b[3] - b[2]))
    cross = cell_of_px((r0 + r1) // 2, (c0 + c1) // 2)

    # block appearance = the colour-9 shape in the bottom-left preview panel (UI rows >= 50)
    panel = _clusters((f == 9) & (np.arange(f.shape[0])[:, None] >= 50))
    if not panel:
        return None
    pr0, pr1, pc0, pc1 = max(panel, key=lambda b: (b[1] - b[0]) * (b[3] - b[2]))
    block_sig = _shape3(f, pr0, pr1, pc0, pc1, 9)

    # targets = colour-9 shapes in the PLAY area (rows < 50). A single target's colour-9
    # silhouette FRAGMENTS (transparent gaps), so merge nearby fragments (gap<=2) into one
    # ~3x3 region. Exclude the block's colour-9 trail (directly under the colour-12 mover).
    mover_cols = set(range(int(blk[:, 1].min()), int(blk[:, 1].max()) + 1))
    regions = _merge(_clusters((f == 9) & (np.arange(f.shape[0])[:, None] < 50)), gap=2)
    targets = []
    for tr0, tr1, tc0, tc1 in regions:
        if set(range(tc0, tc1 + 1)) & mover_cols and tr0 >= int(blk[:, 0].max()):
            continue                          # trail
        if (tr1 - tr0) > 6 or (tc1 - tc0) > 6:
            continue                          # too big to be a 3x3 target appearance
        tgt_sig = _shape3(f, tr0, tr1, tc0, tc1, 9)
        rd = _rot_delta(block_sig, tgt_sig)
        if rd is None:
            return None                       # shape/colour change needed → defer (L3+)
        targets.append((cell_of_px((tr0 + tr1) // 2, (tc0 + tc1) // 2), rd))
    if not targets:
        return None
    return {"pm": pm, "block": block, "rings": rings, "cross": cross, "targets": targets}


def _merge(boxes, gap=2):
    """Union bboxes whose expansions (by `gap`) overlap → merged regions."""
    boxes = [list(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        out = []
        for b in boxes:
            for o in out:
                if (b[0] <= o[1] + gap and o[0] <= b[1] + gap
                        and b[2] <= o[3] + gap and o[2] <= b[3] + gap):
                    o[0], o[1] = min(o[0], b[0]), max(o[1], b[1])
                    o[2], o[3] = min(o[2], b[2]), max(o[3], b[3])
                    changed = True
                    break
            else:
                out.append(b)
        boxes = out
    return [tuple(b) for b in boxes]


# --------------------------------------------------------------------------- planner
def plan(spec):
    """Transform-and-deliver plan (rotation-only): for each target, visit the cross
    `rot_delta` times then deliver, weaving single-use ring resets so no run exceeds the
    timer window. Returns a list of action ids (1=UP 2=DOWN 3=LEFT 4=RIGHT), or None."""
    pm, block, cross, rings = spec["pm"], spec["block"], spec["cross"], list(spec["rings"])
    targets = spec["targets"]
    avoid = {cross} | {t[0] for t in targets}

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

    # waypoints: per target, `rot_delta` cross visits (bounce to re-trigger) then deliver.
    order = sorted(range(len(targets)),
                   key=lambda i: abs(targets[i][0][0] - block[0]) + abs(targets[i][0][1] - block[1]))
    waypoints, prev = [], block
    for ti in order:
        tcell, rd = targets[ti]
        for _ in range(rd):
            if prev == cross:
                nb = nbr_plain(cross)
                if nb is None:
                    return None
                waypoints.append(nb)
            waypoints.append(cross); prev = cross
        waypoints.append(tcell); prev = tcell

    cur, since_reset, rings_left, actions = block, 0, list(rings), []

    def hop(dst):
        nonlocal cur, since_reset
        p = route(cur, dst)
        if p is None:
            return False
        ms = since_reset
        for c in cells_of(cur, p):
            ms += 1
            if c in rings_left:
                rings_left.remove(c); ms = 0
        actions.extend(p); since_reset = ms; cur = dst
        return True

    def nearest_reachable_ring():
        reach = [(r, route(cur, r)) for r in rings_left]
        reach = [(r, q) for r, q in reach if q is not None and since_reset + len(q) <= TIMER_WINDOW]
        return min(reach, key=lambda x: len(x[1])) if reach else (None, None)

    def first_ring_dist(leg):
        for i, c in enumerate(cells_of(cur, leg)):
            if c in rings_left:
                return i + 1
        return len(leg)

    for idx, wp in enumerate(waypoints):
        more = idx < len(waypoints) - 1
        leg = route(cur, wp)
        if leg is None:
            return None
        if more and rings_left:                       # keep-a-ring-reachable invariant
            after = [len(route(wp, r)) for r in rings_left if route(wp, r) is not None]
            ring_after = min(after) if after else 10 ** 9
            rcell, _ = nearest_reachable_ring()
            if rcell is not None and since_reset + len(leg) + ring_after > TIMER_WINDOW:
                if not hop(rcell):
                    return None
                leg = route(cur, wp)
        while since_reset + first_ring_dist(leg) > TIMER_WINDOW and rings_left:   # safety
            rcell, _ = nearest_reachable_ring()
            if rcell is None:
                break
            if not hop(rcell):
                return None
            leg = route(cur, wp)
        if not hop(wp):
            return None
    return actions
