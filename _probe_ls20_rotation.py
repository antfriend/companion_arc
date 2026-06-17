"""Probe the ls20 L2 inner-ring ROTATION trigger.

Drives a given action sequence from L2 start and, per step, prints the two
signatures that matter:
  INNER  = the goal-room entity1 pattern (rows 41-43, cols 14-18) — the thing that
           must rotate clear of the block's entry cell to WIN.
  CARRIER= the entity1 "state" shape (rows 54-62, cols 1-10) — set by ring collection.
plus block cell, cross-present, timer. Lets us pin the exact (state, action) that
rotates INNER.

Usage: python _probe_ls20_rotation.py <tokens...>     e.g. 1 4 1 1 1 1 1 4 4 2 ...
Tokens: 1=UP 2=DOWN 3=LEFT 4=RIGHT  (a*N repeat, e.g. 1*5)
"""
import importlib.util, io, random, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from core.dynamics import library  # noqa: F401 — registers the dynamics (needed to solve L1)

ENV = Path(__file__).parent / "environment_files"
ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3, 4: GameAction.ACTION4}
NAME = {1: "UP", 2: "DOWN", 3: "LEFT", 4: "RIGHT"}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
INNER = (slice(41, 44), slice(14, 19))     # goal-room entity1 pattern region
CARRIER = (slice(54, 62), slice(1, 11))    # entity1 carrier "state" region


def load():
    inst = next(d for d in (ENV / "ls20").iterdir() if d.is_dir() and not d.name.startswith("__"))
    spec = importlib.util.spec_from_file_location("pr_ls20", inst / "ls20.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return next(v for v in vars(m).values() if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def parse(toks):
    out = []
    for t in toks:
        for tt in str(t).split():
            if "*" in tt:
                a, r = tt.split("*"); out += [int(a)] * int(r)
            else:
                out.append(int(tt))
    return out


def sig9(patch):
    """compact: '9' where colour-9 else '.'"""
    return "/".join("".join("9" if int(v) == 9 else "." for v in row) for row in patch)


def block_cell(f):
    p = np.argwhere(f == 12)
    return (round(p[:, 0].mean(), 1), round(p[:, 1].mean(), 1)) if len(p) else None


def main():
    seq = parse(sys.argv[1:]) if len(sys.argv) > 1 else []
    random.seed(0); np.random.seed(0)          # match explore.py replay determinism
    g = load()()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    agent = SupervisedAgent(4, seed=0)
    prev = 0
    # to L2 start
    for _ in range(120):
        if obs is None or str(obs.state) in END or not obs.frame:
            break
        a = agent.choose(np.asarray(obs.frame[-1])) % 4
        obs = g.perform_action(ActionInput(id=ACT[a + 1]), raw=True)
        if obs and (obs.levels_completed or 0) > prev:
            prev = obs.levels_completed
            break
    f = np.asarray(obs.frame[-1])
    print(f"L2 START  block={block_cell(f)} cross={'Y' if (f==0).any() and (f==1).any() else 'n'} "
          f"timer={(f==11).sum()}")
    print(f"  INNER  = {sig9(f[INNER])}")
    print(f"  CARRIER= {sig9(f[CARRIER])}")
    prev_inner = sig9(f[INNER]); prev_car = sig9(f[CARRIER])
    for i, a in enumerate(seq):
        if obs is None or str(obs.state) in END or not obs.frame:
            print(f"[end @ step {i}] {str(obs.state) if obs else None}"); break
        obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
        if not (obs and obs.frame):
            print(f"[no frame @ {i}]"); break
        f = np.asarray(obs.frame[-1])
        inner = sig9(f[INNER]); car = sig9(f[CARRIER])
        cross = "Y" if ((f == 0).any() and (f == 1).any()) else "n"
        tag = []
        if inner != prev_inner: tag.append("INNER-CHG!")
        if car != prev_car: tag.append("CARRIER-CHG")
        st = str(obs.state).replace("GameState.", "")
        lvl = obs.levels_completed or 0
        print(f"{i:3d} {NAME[a]:5s} blk={str(block_cell(f)):14s} x={cross} t={int((f==11).sum()):3d} "
              f"L{lvl} {st:12s} INNER={inner}  {' '.join(tag)}")
        if car != prev_car:
            print(f"      CARRIER= {car}")
        prev_inner, prev_car = inner, car


if __name__ == "__main__":
    main()
