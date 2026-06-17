"""Unified level-agnostic ls20 solver (CORE DYNAMICS prototype).

ls20 is ONE mechanic at every level — "transform-and-deliver":
  the block carries (shape,color,rotation); changer tiles cycle each attribute; rings
  reset a move-timer (single-use); each target requires a specific (shape,color,rotation)
  and admits the block only when all three match; WIN = deliver the block onto every
  target matching. Levels differ only in CONFIGURATION (how many changers/targets/rings),
  not rules — so L1 is a trivial case of the L2 solver.

This prototype reads the per-level spec (block attrs, target requirements, changer/ring
positions) from the GAME OBJECT (the eventual games/ls20/dynamic.py must read the same
facts from the FRAME — feasible: targets are drawn with their required appearance and the
block's preview shows its state), builds a 5px-cell passability map from the frame, plans
attribute-transform + delivery + timer-aware ring interleaving, and VALIDATES by executing
in the real game. Goal: ONE core solver clears L1 AND L2.

Usage: python _solve_ls20.py [maxlevel]
"""
import importlib.util, io, random, sys
from collections import deque
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

ENV = Path(__file__).parent / "environment_files"
ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3, 4: GameAction.ACTION4}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
R0, C0, STEP, NR, NC = 5, 9, 5, 10, 10
PASS = {3, 5, 12, 9, 11, 0, 1}
VOID = 4
DELTA = {1: (-1, 0), 2: (1, 0), 3: (0, -1), 4: (0, 1)}
# changer tags -> attribute index (0 shape, 1 color, 2 rotation)
CHANGER_TAG = {"ttfwljgohq": 0, "soyhouuebz": 1, "rhsxkxzdjz": 2}
RING_TAG = "npxgalaybz"
TARGET_TAG = "rjlbuycveu"
TIMER_WINDOW = 23            # safe moves between resets (true timer ~25; small margin)


def load():
    inst = next(d for d in (ENV / "ls20").iterdir() if d.is_dir() and not d.name.startswith("__"))
    spec = importlib.util.spec_from_file_location("sv_ls20", inst / "ls20.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return next(v for v in vars(m).values() if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def cell_of(x, y):
    return ((y - R0) // STEP, (x - C0) // STEP)


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


def nearest(pm, start, cells):
    best, bestp = None, None
    for cell in cells:
        p = bfs(pm, start, {cell})
        if p is not None and (bestp is None or len(p) < len(bestp)):
            best, bestp = cell, p
    return best, bestp


def read_spec(g):
    """Per-level spec from the game object (frame-readable in the real dynamic)."""
    nattr = [len(g.ijessuuig), len(g.tnkekoeuk), 4]
    block_cell = cell_of(g.gudziatsk.x, g.gudziatsk.y)
    block_attrs = [g.fwckfzsyc, g.hiaauhahz, g.cklxociuu]
    targets = []
    for i, t in enumerate(g.plrpelhym):
        targets.append((cell_of(t.x, t.y), [g.ldxlnycps[i], g.yjdexjsoa[i], g.ehwheiwsk[i]]))
    changers = {0: [], 1: [], 2: []}
    for tag, ai in CHANGER_TAG.items():
        changers[ai] = [cell_of(s.x, s.y) for s in g.current_level.get_sprites_by_tag(tag)]
    rings = [cell_of(s.x, s.y) for s in g.current_level.get_sprites_by_tag(RING_TAG)]
    return nattr, block_cell, block_attrs, targets, changers, rings


def _nbr(pm, cell):
    for dr, dc in DELTA.values():
        n = (cell[0] + dr, cell[1] + dc)
        if 0 <= n[0] < NR and 0 <= n[1] < NC and pm[n]:
            return n
    return None


def plan(pm, block_cell, block_attrs, targets, changers, rings, nattr):
    """Plan a flat waypoint list (changer-visits then delivery, per target), then walk it
    PROACTIVELY topping up the timer at a ring whenever the next leg wouldn't fit the
    window. Each changer-visit = stepping ONTO the changer; repeated visits bounce off a
    neighbour so each return is a fresh step-on."""
    attrs = list(block_attrs)
    # CHANGERS and TARGETS must not be crossed in transit (a changer mutates attrs; a
    # non-matching target bounces). RINGS may be crossed — doing so collects the ring and
    # RESETS the timer (a free, beneficial reset we account for in hop()). Route avoids only
    # the correctness-critical tiles; the intended destination is whitelisted per call.
    avoid = {c for cs in changers.values() for c in cs} | {t[0] for t in targets}
    ring_set = set(rings)

    def route(a, b):
        return bfs(pm, a, {b}, blocked=avoid - {b})

    def cells_of(start, acts):
        cur2, out = start, []
        for a in acts:
            dr, dc = DELTA[a]; cur2 = (cur2[0] + dr, cur2[1] + dc); out.append(cur2)
        return out

    def nearest_r(start, cells):
        best, bp = None, None
        for c in cells:
            p = route(start, c)
            if p is not None and (bp is None or len(p) < len(bp)):
                best, bp = c, p
        return best, bp

    def nbr_plain(cell):
        for dr, dc in DELTA.values():
            n = (cell[0] + dr, cell[1] + dc)
            if 0 <= n[0] < NR and 0 <= n[1] < NC and pm[n] and n not in avoid and n not in ring_set:
                return n
        return _nbr(pm, cell)

    order = sorted(range(len(targets)),
                   key=lambda i: abs(targets[i][0][0] - block_cell[0]) + abs(targets[i][0][1] - block_cell[1]))
    waypoints, prev = [], block_cell
    for ti in order:
        tcell, req = targets[ti]
        for ai in (0, 1, 2):                                   # shape, color, rotation
            need = (req[ai] - attrs[ai]) % nattr[ai]
            if need and not changers[ai]:
                raise RuntimeError(f"need attr {ai} x{need} but no changer")
            for _ in range(need):
                ch, _ = nearest_r(prev, changers[ai])
                if ch is None:
                    raise RuntimeError(f"attr {ai} changer unreachable")
                if prev == ch:                                # bounce to re-trigger
                    waypoints.append(nbr_plain(ch))
                waypoints.append(ch); prev = ch
                attrs[ai] = (attrs[ai] + 1) % nattr[ai]
        waypoints.append(tcell); prev = tcell

    cur, since_reset, rings_left, actions = block_cell, 0, list(rings), []

    def hop(dst):
        """Execute route cur->dst, accounting for rings CROSSED en route (each collected
        ring resets the move-timer). Updates since_reset to moves since the last ring."""
        nonlocal cur, since_reset
        p = route(cur, dst)
        if p is None:
            raise RuntimeError(f"no path {cur}->{dst}")
        ms = since_reset
        for c in cells_of(cur, p):
            ms += 1
            if c in rings_left:
                rings_left.remove(c); ms = 0
        actions.extend(p); since_reset = ms; cur = dst

    def nearest_reachable_ring():
        reach = [(r, route(cur, r)) for r in rings_left]
        reach = [(r, q) for r, q in reach if q is not None and since_reset + len(q) <= TIMER_WINDOW]
        return min(reach, key=lambda x: len(x[1])) if reach else (None, None)

    def first_ring_dist(leg):
        for i, c in enumerate(cells_of(cur, leg)):
            if c in rings_left:
                return i + 1
        return len(leg)            # no ring on this leg

    for idx, wp in enumerate(waypoints):
        more = idx < len(waypoints) - 1
        leg = route(cur, wp)
        if leg is None:
            raise RuntimeError(f"no path {cur}->{wp}")
        # KEEP-A-RING-REACHABLE invariant: if completing this leg would leave the nearest
        # remaining ring unreachable while work still remains, top up NOW (a ring is still
        # reachable at this moment). Prevents stranding after the long oscillation phase.
        if more and rings_left:
            after = [len(route(wp, r)) for r in rings_left if route(wp, r) is not None]
            ring_after = min(after) if after else 10 ** 9
            rcell, _q = nearest_reachable_ring()
            if rcell is not None and since_reset + len(leg) + ring_after > TIMER_WINDOW:
                hop(rcell); leg = route(cur, wp)
        # SAFETY: if the ring-free prefix of this leg itself exceeds the window, detour.
        while since_reset + first_ring_dist(leg) > TIMER_WINDOW and rings_left:
            rcell, _q = nearest_reachable_ring()
            if rcell is None:
                break
            hop(rcell); leg = route(cur, wp)
        hop(wp)
    return actions


def solve_and_play(maxlevel=2):
    random.seed(0); np.random.seed(0)
    g = load()()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    level = 1
    while level <= maxlevel:
        if obs is None or str(obs.state) in END or not obs.frame:
            print(f"[stop] state={str(obs.state) if obs else None}"); break
        f = np.asarray(obs.frame[-1])
        nattr, bc, ba, tg, ch, rings = read_spec(g)
        print(f"\n=== LEVEL {level} === block@{bc} attrs(sh,co,rot)={ba} "
              f"targets={[(c, r) for c, r in tg]} changers={{k:v for k,v in ch.items() if v}} rings={rings}")
        try:
            acts = plan(build_map(f), bc, ba, tg, ch, rings, nattr)
        except RuntimeError as e:
            print(f"  PLAN FAILED: {e}"); break
        print(f"  plan: {len(acts)} moves")
        before = obs.levels_completed or 0
        for a in acts:
            obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
            if obs is None or str(obs.state) in END or not obs.frame:
                break
            if (obs.levels_completed or 0) > before:
                break
        done = (obs.levels_completed or 0) if obs else 0
        if done > before:
            print(f"  LEVEL {level} SOLVED ✓  (levels_completed={done})")
            level += 1
        else:
            print(f"  LEVEL {level} NOT solved (levels_completed={done}, state={str(obs.state) if obs else None})")
            print(f"    DIAG block@{cell_of(g.gudziatsk.x, g.gudziatsk.y)} attrs={[g.fwckfzsyc, g.hiaauhahz, g.cklxociuu]} "
                  f"vs target@{tg[0][0]} req={tg[0][1]}  (block reset to start? {cell_of(g.gudziatsk.x, g.gudziatsk.y)==bc})")
            break
    print(f"\nRESULT: cleared up to level {level-1}")


if __name__ == "__main__":
    solve_and_play(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
