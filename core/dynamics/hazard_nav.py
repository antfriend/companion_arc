"""core/dynamics/hazard_nav.py — hazard-aware navigation organ (ARC-RFC-0001).

A shared search core for L2+ dynamics that add a moving/positional HAZARD on top of
an L1 navigation task. Three hazard archetypes motivate it:

  - wa30 L2: a color-12 sprite PATROLS and KILLS on contact  -> lethal co-occupancy
  - tu93 L2: a TURRET fires instantly along its facing axis   -> lethal trigger cells
  - ls20 L4: a PUSHER SHOVES the mover on contact             -> transition modifier

The first two are LETHAL hazards: navigate so the agent never shares a (cell, time)
with the hazard's occupancy. This module handles that case with a CLOSED-LOOP,
short-horizon SPACE-TIME BFS:

  * HazardTracker   — estimates each hazard's velocity from frame-to-frame centroids.
  * predict_occupancy — extrapolates hazard cells over a short horizon (+ a safety
                        radius), the linear forecast the BFS plans against.
  * spacetime_bfs   — BFS over (cell, t) with a pluggable `passable(cell)` static
                      mask and the per-time lethal sets; returns the FIRST move of a
                      safe path to the goal, a safe WAIT when no progress is safe but
                      survival is, or None when no safe action exists.

Because the controller RE-PLANS every frame, only the short horizon must be accurate;
irregular pauses/turns in the real hazard cost at most a one-step misprediction, which
the next re-plan absorbs (and the safety radius covers). Everything is in abstract
CELL coordinates; callers map pixels <-> cells. The pusher (transition-modifier) case
is a documented future extension — see `spacetime_bfs`'s `neighbors` hook.
"""

from collections import deque

WAIT = (0, 0)


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class HazardTracker:
    """Estimate hazard velocities (cells/step) from successive frames.

    Stateless across game resets — make a fresh tracker per level (call reset()).
    `update(positions)` is called once per observed frame with the current hazard
    cells; it greedily matches each to the nearest previous hazard to derive a
    velocity, and returns a list of (cell, vel) pairs for the forecaster.
    """

    def __init__(self):
        self.prev = None          # list[(cell, vel)] from the last frame

    def reset(self):
        self.prev = None

    def update(self, positions):
        positions = [tuple(p) for p in positions]
        if self.prev is None:
            out = [(p, (0, 0)) for p in positions]
        else:
            prev_cells = [c for c, _ in self.prev]
            out = []
            for p in positions:
                if prev_cells:
                    pc = min(prev_cells, key=lambda q: manhattan(q, p))
                    out.append((p, (p[0] - pc[0], p[1] - pc[1])))
                else:
                    out.append((p, (0, 0)))
        self.prev = out
        return out


def predict_occupancy(hazards, horizon, radius=1, bounds=None):
    """Forecast lethal cells per timestep.

    hazards : list[(cell, vel)] from HazardTracker.update.
    horizon : forecast depth (occ has horizon+1 entries, t = 0..horizon).
    radius  : Manhattan-box safety buffer painted around each predicted cell.
    bounds  : optional (x0, y0, x1, y1) cell bounds; the forecast BOUNCES off them
              (a patroller reverses at a wall) instead of marching out of the arena.

    Returns occ : list[set[cell]] of length horizon+1. A patroller may PAUSE before
    turning, so the current cell is kept lethal across the whole horizon (cheap
    insurance against the observed one-step turn delay).
    """
    occ = [set() for _ in range(horizon + 1)]

    def paint(s, cx, cy):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if abs(dx) + abs(dy) <= radius:
                    s.add((cx + dx, cy + dy))

    for (cx, cy), (vx, vy) in hazards:
        x, y = cx, cy
        for t in range(horizon + 1):
            paint(occ[t], x, y)
            paint(occ[t], cx, cy)      # pause-insurance: origin stays hot
            nx, ny = x + vx, y + vy
            if bounds is not None:
                x0, y0, x1, y1 = bounds
                if nx < x0 or nx > x1:
                    vx = -vx
                    nx = x + vx
                if ny < y0 or ny > y1:
                    vy = -vy
                    ny = y + vy
            x, y = nx, ny
    return occ


def spacetime_bfs(start, goal, passable, occ, horizon,
                  neighbors=((0, -1), (0, 1), (-1, 0), (1, 0)),
                  allow_wait=True):
    """Closed-loop space-time BFS. Return the FIRST move toward a safe path.

    start     : current agent cell (assumed currently safe).
    goal      : a target cell, or an iterable of acceptable target cells (reach ANY);
                with several goals the agent routes to the nearest REACHABLE one, so a
                blocked nearest goal can't strand it (e.g. a relocated item parked on
                the closest drop cell).
    passable  : cell -> bool static traversability (walls / bounds / blockers).
    occ       : list[set[cell]] lethal cells per time (from predict_occupancy).
    horizon   : max lookahead depth (== len(occ)-1 is typical).
    neighbors : the move set, default 4-connected. (A pusher dynamic would pass a
                custom set / transition here — future extension.)
    allow_wait: include the WAIT (0,0) move (realize it as a no-op in the adapter).

    Returns one of:
      * a move (dx, dy) — first step of the shortest safe path that REACHES goal;
      * the move that gets safely CLOSEST to goal if goal is unreachable in horizon;
      * WAIT if staying put is the only safe option;
      * None if no safe action exists (caller defers / aborts).
    """
    moves = list(neighbors) + ([WAIT] if allow_wait else [])
    goals = {tuple(goal)} if (isinstance(goal, tuple) and goal and
                              not isinstance(goal[0], tuple)) else set(map(tuple, goal))

    def dist(cell):
        return min(manhattan(cell, g) for g in goals)

    def lethal(cell, t):
        return t < len(occ) and cell in occ[t]

    # Seed the queue with each legal, safe first move; carry that first move along
    # so we never reconstruct a parent chain.
    q = deque()
    seen = {(start, 0)}
    best = None          # (dist_to_goal, first_move) — greedy fallback
    for mv in moves:
        ncell = start if mv == WAIT else (start[0] + mv[0], start[1] + mv[1])
        if mv != WAIT and not passable(ncell):
            continue
        if lethal(ncell, 1):
            continue
        st = (ncell, 1)
        if st not in seen:
            seen.add(st)
            q.append((ncell, 1, mv))

    while q:
        cell, t, first = q.popleft()
        if cell in goals:
            return first
        d = dist(cell)
        if best is None or d < best[0]:
            best = (d, first)
        if t >= horizon:
            continue
        for mv in moves:
            ncell = cell if mv == WAIT else (cell[0] + mv[0], cell[1] + mv[1])
            if mv != WAIT and not passable(ncell):
                continue
            if lethal(ncell, t + 1):
                continue
            st = (ncell, t + 1)
            if st not in seen:
                seen.add(st)
                q.append((ncell, t + 1, first))

    if best is not None:
        return best[1]
    return None
