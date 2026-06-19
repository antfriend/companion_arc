"""_test_hazard_nav.py — provable unit test for the hazard-aware nav organ.

Synthetic gridworlds with a DETERMINISTIC patroller (the test's ground truth). The
controller sees only OBSERVED hazard positions (no oracle) and drives via
HazardTracker + predict_occupancy + spacetime_bfs, exactly as the real adapters will.

Proves three properties:
  A. SOLVABLE  — on open boards the agent reaches the goal and NEVER collides.
  B. WAIT      — when a patroller periodically seals the only door, the agent waits
                 for a gap rather than walking into it, and still gets through.
  C. FAIL-SAFE — when boxed with no safe move, the organ returns None (no crash, no
                 illegal move), and a GREEDY controller (no hazard model) would die.

Run: python _test_hazard_nav.py
"""

from core.dynamics.hazard_nav import (
    HazardTracker, predict_occupancy, spacetime_bfs, manhattan, WAIT,
)


class Patroller:
    """Bounces along a fixed axis between [lo, hi], pausing one tick at each end
    (mirrors the irregular real wa30 turn delay). Ground truth, hidden from agent."""

    def __init__(self, pos, axis, lo, hi, vel=1):
        self.pos = pos          # (x, y)
        self.axis = axis        # 0 = move in x, 1 = move in y
        self.lo, self.hi = lo, hi
        self.v = vel
        self._paused = False

    def step(self):
        x, y = self.pos
        coord = x if self.axis == 0 else y
        nxt = coord + self.v
        if nxt < self.lo or nxt > self.hi:
            if not self._paused:        # pause one tick at the wall
                self._paused = True
                return
            self._paused = False
            self.v = -self.v
            nxt = coord + self.v
        if self.axis == 0:
            self.pos = (nxt, y)
        else:
            self.pos = (x, nxt)


def run_episode(walls, start, goal, patrollers, bounds, horizon=10,
                radius=1, max_ticks=400, model_hazards=True):
    """Drive the closed-loop controller. Returns (outcome, ticks) where outcome in
    {'win','collision','stuck','timeout'}. model_hazards=False = greedy ablation."""
    x0, y0, x1, y1 = bounds

    def passable(c):
        return (x0 <= c[0] <= x1 and y0 <= c[1] <= y1 and c not in walls)

    tracker = HazardTracker()
    agent = start
    for tick in range(max_ticks):
        haz_cells = [p.pos for p in patrollers]
        if agent in haz_cells:
            return "collision", tick
        if agent == goal:
            return "win", tick

        if model_hazards:
            hz = tracker.update(haz_cells)
            occ = predict_occupancy(hz, horizon, radius=radius, bounds=bounds)
        else:
            occ = [set() for _ in range(horizon + 1)]   # greedy: blind to hazards
        mv = spacetime_bfs(agent, goal, passable, occ, horizon)
        if mv is None:
            return "stuck", tick

        prev_agent = agent
        if mv != WAIT:
            cand = (agent[0] + mv[0], agent[1] + mv[1])
            if passable(cand):
                agent = cand
        # hazards move after the agent (one move per action, as in-game)
        prev_haz = list(haz_cells)
        for p in patrollers:
            p.step()
        new_haz = [p.pos for p in patrollers]
        # collision if co-occupying, or if they swapped through each other
        if agent in new_haz:
            return "collision", tick
        for ph, nh in zip(prev_haz, new_haz):
            if agent == ph and prev_agent == nh:
                return "collision", tick
    return "timeout", max_ticks


def line_walls(bounds):
    x0, y0, x1, y1 = bounds
    w = set()
    for x in range(x0 - 1, x1 + 2):
        w.add((x, y0 - 1)); w.add((x, y1 + 1))
    for y in range(y0 - 1, y1 + 2):
        w.add((x0 - 1, y)); w.add((x1 + 1, y))
    return w


def test_solvable():
    """A: open board, a patroller sweeping the middle row. Agent must cross it."""
    bounds = (0, 0, 9, 9)
    wins = 0
    N = 12
    for sx in range(0, 6, 1):
        for px in range(0, 8, 2):
            walls = line_walls(bounds)
            pat = Patroller((px, 5), axis=0, lo=0, hi=9, vel=1)
            out, _ = run_episode(walls, (sx, 0), (sx, 9), [pat], bounds)
            assert out != "collision", f"COLLISION at start={sx},patrol={px}"
            if out == "win":
                wins += 1
    total = len(range(0, 6, 1)) * len(range(0, 8, 2))
    print(f"  A solvable: {wins}/{total} reached goal, 0 collisions")
    assert wins == total, "agent failed to cross an open board"


def test_wait_for_gap():
    """B: a single door in a wall, and a patroller SWEEPING the door-approach row.
    The agent must hold/dodge until the sweep clears the door, then cross. Proven by
    contrast: the hazard-modelling organ wins with no collision; the greedy ablation
    (blind to the hazard) walks into the sweep and dies."""
    bounds = (0, 0, 6, 10)
    walls = line_walls(bounds)
    for x in range(0, 7):            # wall row at y=5, single door at x=3
        if x != 3:
            walls.add((x, 5))
    # Sweep the patroller's starting phase so the proof is timing-independent: the
    # organ must cross safely from EVERY phase; the blind greedy must die on some.
    organ_wins = organ_coll = greedy_coll = 0
    phases = range(0, 7)
    for x0 in phases:
        pat = Patroller((x0, 4), axis=0, lo=0, hi=6, vel=1)
        out, _ = run_episode(walls, (3, 0), (3, 10), [pat], bounds,
                             horizon=14, radius=1, max_ticks=400, model_hazards=True)
        organ_wins += (out == "win")
        organ_coll += (out == "collision")
        pat2 = Patroller((x0, 4), axis=0, lo=0, hi=6, vel=1)
        g, _ = run_episode(walls, (3, 0), (3, 10), [pat2], bounds,
                           horizon=14, radius=1, max_ticks=400, model_hazards=False)
        greedy_coll += (g == "collision")
    print(f"  B wait-for-gap: organ wins {organ_wins}/{len(phases)} (0 coll? {organ_coll==0})"
          f"  greedy collisions {greedy_coll}/{len(phases)}")
    assert organ_coll == 0, "organ collided on some phase"
    assert organ_wins == len(phases), "organ failed to cross on some phase"
    assert greedy_coll > 0, "greedy ablation never died (test not adversarial enough)"


def test_fail_safe_vs_greedy():
    """C: patroller marches straight at a cornered agent with no escape. The organ
    must return None (stuck, fail-safe) while the greedy ablation walks into death."""
    bounds = (0, 0, 4, 0)            # 1-D corridor of length 5
    walls = line_walls(bounds)
    # agent at the left end; patroller marching left toward it, no room to pass
    pat = Patroller((4, 0), axis=0, lo=0, hi=4, vel=-1)
    safe_out, _ = run_episode(walls, (0, 0), (4, 0), [pat], bounds,
                              horizon=8, radius=0, max_ticks=20, model_hazards=True)
    pat2 = Patroller((4, 0), axis=0, lo=0, hi=4, vel=-1)
    greedy_out, _ = run_episode(walls, (0, 0), (4, 0), [pat2], bounds,
                                horizon=8, radius=0, max_ticks=20, model_hazards=False)
    print(f"  C fail-safe: organ={safe_out}  greedy={greedy_out}")
    assert safe_out != "collision", "organ collided in the trap (should fail-safe)"
    assert greedy_out == "collision", "greedy ablation should have died (test too easy)"


if __name__ == "__main__":
    print("hazard-nav organ — synthetic proof")
    test_solvable()
    test_wait_for_gap()
    test_fail_safe_vs_greedy()
    print("ALL PASS")
