"""Completion-based two-sided proxy for the per-instance SOLVING regime.

The validated coverage proxy (_test_proxy_curve.py) is BLIND to completion-
recognition gains: it scores how much state an agent visits, not whether it
COMPLETES. sp80 is the only canonical game exploration ever finishes, and its
win-rate is stochastic noise. So a solving mechanism cannot be validated there.

This proxy measures WIN-RATE and STEPS-TO-WIN on goal-reaching tasks, with a
credibility anchor — exactly as the coverage proxy earned trust by reproducing
the known leaderboard ordering random < v1.

Two pillars:
  A. Synthetic goal-gridworlds (own ground truth): solvable / affordance / trap.
  B. Budget-shrunk sp80 (the one completing canonical game) for real-frame transfer.

Credibility anchor = an ORACLE (BFS to the TRUE goal, allowed only in synthetic
worlds where we own ground truth). The proxy is VALID iff:
  * solvable/affordance: oracle >> base win-rate and << steps  (completion-sensitive)
  * trap:               aggressive "near" REGRESSES base, safe "react" ties base
                        (safety-sensitive — the additive-only law's failure mode)
Only then are the middle numbers (our goal modes vs base) trustworthy.

Usage: python _test_solve_proxy.py [--seeds N] [--sp80-budget N] [--no-sp80]
"""
import collections
import io
import random
import statistics
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np

from core.general_agent import GeneralAgent
from core.general_agent_dyn import GeneralAgentDyn
from core.goal_agent import GoalSeekAgent

SEEDS = 40
SP80_BUDGET = 60
RUN_SP80 = True
if "--seeds" in sys.argv:
    i = sys.argv.index("--seeds"); SEEDS = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
if "--sp80-budget" in sys.argv:
    i = sys.argv.index("--sp80-budget"); SP80_BUDGET = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
if "--no-sp80" in sys.argv:
    RUN_SP80 = False; sys.argv.remove("--no-sp80")

# action index -> (dy, dx). The agents do NOT know this; they learn it online.
MAP = [(-1, 0), (1, 0), (0, -1), (0, 1)]
N = 12                       # grid side (interior is rows/cols 1..N-2)
BG, ENT, GOAL, KEY, TRAP = 0, 3, 4, 5, 6
BUDGET = {"solvable": 40, "affordance": 70, "trap": 60}


# --------------------------------------------------------------------------
# Synthetic goal-gridworld
# --------------------------------------------------------------------------
class SyntheticWorld:
    def __init__(self, kind: str, seed: int):
        self.kind = kind
        rng = random.Random(seed)
        cells = [(y, x) for y in range(1, N - 1) for x in range(1, N - 1)]
        rng.shuffle(cells)
        # entity and goal far apart
        self.epos = cells[0]
        self.gpos = next(c for c in cells[1:]
                         if abs(c[0] - self.epos[0]) + abs(c[1] - self.epos[1]) >= N // 2)
        self.kpos = None
        self.collected = True
        self.trap_cells = set()
        self.done = False
        self.won = False
        if kind == "affordance":
            self.collected = False
            self.kpos = next(c for c in cells[2:]
                             if c not in (self.epos, self.gpos)
                             and abs(c[0] - self.epos[0]) + abs(c[1] - self.epos[1]) >= 2)
        if kind == "trap":
            # ADVERSARIAL: a salient 2x2 lethal "magnet" placed NEAR the entity
            # on the side AWAY from the goal. A naive nearest-object seeker locks
            # onto it (closer + larger than the 1-cell goal) and dies; undirected
            # play wanders past it toward the real goal. This is the additive-
            # safety failure mode the proxy must be able to detect.
            def sgn(v):
                return (v > 0) - (v < 0)
            ay = sgn(self.epos[0] - self.gpos[0]) or 1     # unit AWAY from goal
            ax = sgn(self.epos[1] - self.gpos[1]) or 1
            my = min(max(self.epos[0] + 2 * ay, 1), N - 3)
            mx = min(max(self.epos[1] + 2 * ax, 1), N - 3)
            self.trap_cells = {(my, mx), (my + 1, mx), (my, mx + 1), (my + 1, mx + 1)}
            self.trap_cells.discard(self.epos); self.trap_cells.discard(self.gpos)

    def frame(self) -> np.ndarray:
        a = np.zeros((N, N), dtype=np.int64)
        for (y, x) in self.trap_cells:
            a[y, x] = TRAP
        a[self.gpos] = GOAL
        if self.kpos is not None and not self.collected:
            a[self.kpos] = KEY
        a[self.epos] = ENT
        return a

    def reset(self) -> np.ndarray:
        return self.frame()

    def _passable(self, cell, for_oracle=False):
        y, x = cell
        if not (1 <= y < N - 1 and 1 <= x < N - 1):
            return False
        if cell in self.trap_cells:
            return False
        if self.kind == "affordance" and not self.collected and cell == self.gpos:
            return False                 # goal locked until key collected
        return True

    def step(self, a: int):
        if self.done:
            return self.frame(), self.done, self.won
        dy, dx = MAP[a % 4]
        ny, nx = self.epos[0] + dy, self.epos[1] + dx
        cell = (ny, nx)
        # trap = death
        if cell in self.trap_cells:
            self.done = True
            return self.frame(), True, False
        # locked goal or wall = blocked no-op
        if not (1 <= ny < N - 1 and 1 <= nx < N - 1):
            return self.frame(), False, False
        if self.kind == "affordance" and not self.collected and cell == self.gpos:
            return self.frame(), False, False
        # key pickup (reaction: key vanishes, goal unlocks)
        if self.kpos is not None and not self.collected and cell == self.kpos:
            self.epos = cell; self.collected = True
            return self.frame(), False, False
        # goal reached
        if cell == self.gpos and (self.collected or self.kind != "affordance"):
            self.epos = cell; self.done = True; self.won = True
            return self.frame(), True, True
        self.epos = cell
        return self.frame(), False, False

    # ground-truth oracle: BFS first step toward the current true target
    def oracle_action(self) -> int:
        if self.kind == "affordance" and not self.collected:
            target = self.kpos
        else:
            target = self.gpos
        start = self.epos
        if target is None or start == target:
            return 0
        q = collections.deque([start])
        prev = {start: None}
        while q:
            cur = q.popleft()
            if cur == target:
                break
            for ai, (dy, dx) in enumerate(MAP):
                nxt = (cur[0] + dy, cur[1] + dx)
                if nxt in prev:
                    continue
                # the target itself is reachable even if "locked" predicate says no
                if nxt != target and not self._passable(nxt):
                    continue
                if nxt == target or self._passable(nxt):
                    prev[nxt] = cur
                    q.append(nxt)
        if target not in prev:
            return 0
        # walk back to the first move
        node = target
        while prev[node] is not None and prev[node] != start:
            node = prev[node]
        dy, dx = node[0] - start[0], node[1] - start[1]
        for ai, m in enumerate(MAP):
            if m == (dy, dx):
                return ai
        return 0


def _greedy_action(frame: np.ndarray) -> int:
    """Naive DIRECTED-COMMITMENT anchor (the 0.08-detector shape): every step,
    beeline one true step toward the nearest foreground object. No exploration,
    no confidence gate, no tie-break discipline. Deliberately additive-UNSAFE —
    it exists to prove the proxy's safety axis can detect a regression."""
    from core.goal_agent import _centroid, _bg_color
    e = _centroid(frame == ENT)
    if e is None:
        return 0
    ey, ex = e[0], e[1]
    bg = _bg_color(frame)
    best, bd = None, None
    for c in np.unique(frame):
        if c in (bg, ENT):
            continue
        cc = _centroid(frame == c)
        if cc is None:
            continue
        d = (cc[0] - ey) ** 2 + (cc[1] - ex) ** 2
        if bd is None or d < bd:
            bd, best = d, (cc[0], cc[1])
    if best is None:
        return 0
    gy, gx = best
    # pick the true move that most reduces distance to the object
    bestA, bestD = 0, None
    for ai, (dy, dx) in enumerate(MAP):
        nd = (ey + dy - gy) ** 2 + (ex + dx - gx) ** 2
        if bestD is None or nd < bestD:
            bestD, bestA = nd, ai
    return bestA


def make_agent(policy, seed):
    if policy in ("random", "oracle", "greedy"):
        return None
    if policy == "base":
        return GeneralAgentDyn(4, seed=seed)
    if policy == "v1":
        return GeneralAgent(4, seed=seed)
    if policy in ("near", "react", "frontier"):
        return GoalSeekAgent(4, seed=seed, goal_mode=policy)
    raise ValueError(policy)


def play_syn(kind, policy, seed):
    w = SyntheticWorld(kind, seed)
    frame = w.reset()
    agent = make_agent(policy, seed)
    rng = random.Random(seed * 7919 + 1)
    budget = BUDGET[kind]
    for step in range(budget):
        if policy == "oracle":
            a = w.oracle_action()
        elif policy == "greedy":
            a = _greedy_action(frame)
        elif policy == "random":
            a = rng.randrange(4)
        else:
            a = agent.choose(frame) % 4
        frame, done, won = w.step(a)
        if done:
            return won, step + 1
    return False, budget


# --------------------------------------------------------------------------
# Pillar B: budget-shrunk sp80 (real frame, movement only)
# --------------------------------------------------------------------------
def play_sp80(policy, seed, budget):
    import importlib.util
    from pathlib import Path
    from arcengine import ARCBaseGame, ActionInput, GameAction
    ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
               GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
    END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
    root = Path(__file__).parent / "environment_files" / "sp80"
    inst = next(root.iterdir())
    spec = importlib.util.spec_from_file_location("pc_sp80", inst / "sp80.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    cls = next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)
    g = cls()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    raw = list(getattr(g, "_available_actions", [1, 2, 3, 4, 5]))
    mo = [ACTIONS[a - 1] for a in raw if a != 6]
    n = len(mo)
    rng = random.Random(seed)
    agent = make_agent(policy, seed)
    if agent is not None:
        agent.set_n_actions(n)
    for step in range(budget):
        if obs is None or str(obs.state) in END or not obs.frame:
            break
        full = np.asarray(obs.frame[-1])
        a = rng.randrange(n) if agent is None else agent.choose(full) % n
        obs = g.perform_action(ActionInput(id=mo[a]), raw=True)
        if obs is not None and obs.levels_completed > 0:
            return True, step + 1
    return False, budget


# --------------------------------------------------------------------------
def summarize(kind, policies):
    rows = {}
    for p in policies:
        wins, swins = 0, []
        for s in range(SEEDS):
            won, steps = play_syn(kind, p, s)
            wins += int(won)
            if won:
                swins.append(steps)
        rows[p] = (wins / SEEDS, statistics.mean(swins) if swins else float("nan"))
    return rows


def main():
    print(f"COMPLETION PROXY (solving regime)   seeds={SEEDS}\n")
    policies = ["random", "base", "near", "react", "frontier", "greedy", "oracle"]
    results = {}
    for kind in ("solvable", "affordance", "trap"):
        rows = summarize(kind, policies)
        results[kind] = rows
        print(f"== {kind}  (budget {BUDGET[kind]}) ==")
        print(f"{'policy':9s} | {'win%':>5s} | {'avg steps-to-win':>16s}")
        print("-" * 38)
        for p in policies:
            wr, st = rows[p]
            stxt = f"{st:.1f}" if st == st else "  -"
            print(f"{p:9s} | {wr*100:4.0f}% | {stxt:>16s}")
        print()

    sp80 = None
    if RUN_SP80:
        print(f"== sp80 (real, budget {SP80_BUDGET}) ==")
        print(f"{'policy':9s} | {'win%':>5s} | {'avg steps-to-win':>16s}")
        print("-" * 38)
        sp80 = {}
        for p in ("random", "base", "near", "react", "frontier"):
            wins, swins = 0, []
            for s in range(SEEDS):
                try:
                    won, steps = play_sp80(p, s, SP80_BUDGET)
                except Exception as e:
                    print(f"  sp80 {p} error: {e}"); won, steps = False, SP80_BUDGET
                wins += int(won)
                if won:
                    swins.append(steps)
            sp80[p] = (wins / SEEDS, statistics.mean(swins) if swins else float("nan"))
            wr, st = sp80[p]
            stxt = f"{st:.1f}" if st == st else "  -"
            print(f"{p:9s} | {wr*100:4.0f}% | {stxt:>16s}")
        print()

    # ---- credibility verdict --------------------------------------------
    # Two anchors bound the metric's sensitivity, exactly as the coverage proxy
    # used random<v1. ORACLE (true-goal BFS) must beat base -> the metric detects
    # COMPLETION gains. GREEDY (naive committed beeline, the 0.08-detector shape)
    # must REGRESS base on the trap -> the metric detects additive-UNSAFETY. Only
    # with both anchors firing do the real goal_mode numbers in between mean
    # something. The modes are then judged: upside (beats base on goal worlds)
    # AND safe (does not regress base on the trap).
    sv = results["solvable"]; af = results["affordance"]; tr = results["trap"]
    upside_anchor = (sv["oracle"][0] >= sv["base"][0] + 0.25 and
                     af["oracle"][0] >= af["base"][0] + 0.25)
    safety_anchor = tr["greedy"][0] <= tr["base"][0] - 0.10
    print("=" * 60)
    print("ANCHORS (bound the metric's sensitivity):")
    print(f"  upside  oracle vs base: solvable {sv['oracle'][0]*100:.0f}/"
          f"{sv['base'][0]*100:.0f}%  affordance {af['oracle'][0]*100:.0f}/"
          f"{af['base'][0]*100:.0f}%  -> {'DETECTS gains' if upside_anchor else 'FLAT'}")
    print(f"  safety  greedy vs base on trap: {tr['greedy'][0]*100:.0f}/"
          f"{tr['base'][0]*100:.0f}%  -> "
          f"{'DETECTS unsafety' if safety_anchor else 'NO regression visible'}")
    proxy_ok = upside_anchor and safety_anchor
    print("-" * 60)
    if not proxy_ok:
        print("PROXY INVALID: an anchor did not fire — the metric cannot be")
        print("trusted to measure that axis. Redesign worlds/anchor before shipping.")
        return
    print("PROXY VALID on both axes. Goal-mode read-off (gain w/o regression):")
    for m in ("near", "react", "frontier"):
        g_sv = sv[m][0] - sv["base"][0]
        g_af = af[m][0] - af["base"][0]
        g_tr = tr[m][0] - tr["base"][0]
        safe = g_tr >= -0.07
        gainful = (g_sv > 0.05) or (g_af > 0.05)
        tag = ("SAFE+GAIN" if safe and gainful else
               "SAFE,flat" if safe else "REGRESSES-trap")
        print(f"  {m:8s}  solvable {g_sv*100:+4.0f}  affordance {g_af*100:+4.0f}  "
              f"trap {g_tr*100:+4.0f}   -> {tag}")


if __name__ == "__main__":
    main()
