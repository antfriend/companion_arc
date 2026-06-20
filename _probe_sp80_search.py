"""Feasibility search for sp80 L2: can a short sequence of piece moves + spill
win? Uses deepcopy snapshots on the real engine (faithful flood). Reports any
winning action sequence found, plus the post-spill frame so we can see how the
flood channels."""
import copy
import io
import sys
from collections import deque
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
from arcengine import ActionInput, GameAction

import importlib.util
ENV = Path(__file__).parent / "environment_files"
A = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
     GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6]


def load(game):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("ps_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from arcengine import ARCBaseGame
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def fresh_l2(cls):
    g = cls()
    g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    g.set_level(1)
    return g


def apply(g, seq):
    """Apply a list of GameAction ids; return (levels_completed, state, last_frame)."""
    obs = None
    for a in seq:
        obs = g.perform_action(ActionInput(id=a), raw=True)
        if obs is None or str(obs.state) in ("GameState.GAME_OVER", "GameState.WIN"):
            break
    lc = obs.levels_completed if obs else 0
    st = str(obs.state) if obs else "None"
    fr = np.asarray(obs.frame[-1]) if obs and obs.frame else None
    return lc, st, fr


def main():
    cls = load("sp80")

    # Baseline: just spill immediately (no moves), see the flood + outcome.
    g = fresh_l2(cls)
    lc, st, fr = apply(g, [GameAction.ACTION5] + [GameAction.ACTION1] * 12)
    print(f"immediate spill: levels_completed={lc} state={st}")
    if fr is not None:
        # show interior grid (strip 4px scale -> logical 16x16 by sampling)
        print("post-spill frame uniques:", np.unique(fr, return_counts=True))

    # BFS over piece-moves (A1..A4) with a spill test (A5 + filler) at each node.
    cls2 = load("sp80")
    start = fresh_l2(cls2)
    MOVES = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3, GameAction.ACTION4]
    SPILL_TAIL = [GameAction.ACTION5] + [GameAction.ACTION1] * 12
    seen = 0
    best = None
    q = deque([(start, [])])
    MAXDEPTH = 6
    found = []
    while q:
        g, path = q.popleft()
        if len(path) >= MAXDEPTH:
            continue
        for mv in MOVES:
            child = copy.deepcopy(g)
            obs = child.perform_action(ActionInput(id=mv), raw=True)
            if obs is None or str(obs.state) in ("GameState.GAME_OVER", "GameState.WIN"):
                continue
            npath = path + [mv]
            # test spill from this node
            t = copy.deepcopy(child)
            lc, st, _ = apply(t, SPILL_TAIL)
            seen += 1
            if lc >= 1:
                found.append(npath)
                print(f"WIN via moves {[int(str(m).split('ACTION')[1]) for m in npath]} -> lc={lc}")
                if len(found) >= 5:
                    print(f"(stopping after 5 wins; explored {seen} spill tests)")
                    return
            q.append((child, npath))
    print(f"explored {seen} spill-tests, wins found: {len(found)}")


if __name__ == "__main__":
    main()
