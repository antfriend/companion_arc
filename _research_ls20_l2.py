"""Research: closed-loop navigation for the ls20 L2 5-wide block.

Builds a 5px-cell passability map from the live L2 start frame, BFS-navigates the block
(1 cell = 5px per action) to a chosen target (cross / ring / goal room), and emits the
action sequence so it can be VALIDATED by replay in explore.py. This is the foundation
for the closed-loop solver (the open-loop route never reaches the cross).

Grid (decoded from raw pixels): row-cells r0=5 step 5; col-cells c0=9 step 5; 5px cells.
Colors: 3=track(passable) 5=floor(passable) 4=void(blocked) 12=block 9=entity1-trail
11=ring 0/1=cross/state-changer.

Usage: python _research_ls20_l2.py [target]   target in {cross,ringA,ringB,goal}
"""
import importlib.util, io, sys
from collections import deque
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from core.dynamics import library  # noqa
from games.ls20.dynamic import Ls20Dynamic

ENV = Path(__file__).parent / "environment_files"
ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3, 4: GameAction.ACTION4}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
R0, C0, STEP = 5, 9, 5
NR, NC = 10, 10                    # logical cells (rows 5..50, cols 9..54)
PASS = {3, 5, 12, 9, 11, 0, 1}     # passable / occupiable colours
VOID = 4
# action -> cell delta (UP a1, DOWN a2, LEFT a3, RIGHT a4)
DELTA = {1: (-1, 0), 2: (1, 0), 3: (0, -1), 4: (0, 1)}


def load():
    inst = next(d for d in (ENV / "ls20").iterdir() if d.is_dir() and not d.name.startswith("__"))
    spec = importlib.util.spec_from_file_location("rs_ls20", inst / "ls20.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return next(v for v in vars(m).values() if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def l2_start_frame():
    """Play the solver to L1 completion; return the first L2 frame."""
    g = load()()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    agent = SupervisedAgent(4, seed=0)
    prev = 0
    for _ in range(120):
        if obs is None or str(obs.state) in END or not obs.frame:
            break
        a = agent.choose(np.asarray(obs.frame[-1])) % 4
        obs = g.perform_action(ActionInput(id=ACT[a + 1]), raw=True)
        if obs and (obs.levels_completed or 0) > prev:
            return np.asarray(obs.frame[-1])
    raise SystemExit("never reached L2")


def cell_color(f, r, c):
    """Majority non-void colour in the 5x5 cell, else void."""
    pr, pc = R0 + r * STEP, C0 + c * STEP
    patch = f[pr:pr + STEP, pc:pc + STEP]
    vals = patch.reshape(-1)
    nonvoid = vals[vals != VOID]
    if len(nonvoid) == 0:
        return VOID
    return int(np.bincount(nonvoid).argmax())


def build_map(f):
    grid = np.full((NR, NC), VOID)
    for r in range(NR):
        for c in range(NC):
            col = cell_color(f, r, c)
            grid[r, c] = col
    passable = np.isin(grid, list(PASS))
    return grid, passable


def find_cell(f, colors):
    """Cell (r,c) whose 5x5 patch contains any of `colors` (first/topmost-leftmost)."""
    pos = np.argwhere(np.isin(f, list(colors)))
    if not len(pos):
        return None
    # map pixel to cell
    cells = {}
    for pr, pc in pos:
        r = (pr - R0) // STEP; c = (pc - C0) // STEP
        if 0 <= r < NR and 0 <= c < NC:
            cells[(r, c)] = cells.get((r, c), 0) + 1
    if not cells:
        return None
    return max(cells, key=cells.get)


def bfs(passable, start, goals):
    goals = set(goals)
    q = deque([(start, [])])
    seen = {start}
    while q:
        (r, c), path = q.popleft()
        if (r, c) in goals:
            return path
        for a, (dr, dc) in DELTA.items():
            nr, nc = r + dr, c + dc
            if 0 <= nr < NR and 0 <= nc < NC and passable[nr, nc] and (nr, nc) not in seen:
                seen.add((nr, nc))
                q.append(((nr, nc), path + [a]))
    return None


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "cross"
    f = l2_start_frame()
    grid, passable = build_map(f)
    block = find_cell(f, {12})
    cross = find_cell(f, {0, 1})
    rings = []
    pos11 = np.argwhere(f == 11)
    seen = set()
    for pr, pc in pos11:
        r = (pr - R0) // STEP; c = (pc - C0) // STEP
        if (r, c) not in seen and 0 <= r < NR and 0 <= c < NC:
            seen.add((r, c)); rings.append((r, c))
    goalroom = find_cell(f, {9}) if False else None
    # goal room cell = the color-5 room with color-9 inside, around col-cell 1 (cols 13-19)
    gr = None
    for r in range(NR):
        for c in range(NC):
            if cell_color(f, r, c) in (5, 9) and C0 + c * STEP >= 9 and c <= 2:
                gr = (r, c)
    print("=== ls20 L2 cell map (.=void  #=track  o=block  +=cross  R=ring  G=goalroom) ===")
    print("    " + "".join(f"c{C0+c*STEP:<3}"[:3] for c in range(NC)))
    for r in range(NR):
        row = f"r{R0+r*STEP:<2} "
        for c in range(NC):
            ch = "#" if passable[r, c] else "."
            if (r, c) == block: ch = "o"
            elif (r, c) == cross: ch = "+"
            elif (r, c) in rings: ch = "R"
            elif (r, c) == gr: ch = "G"
            row += f" {ch} "
        print(row)
    print(f"\nblock={block} cross={cross} rings={rings} goalroom={gr}")

    tgt = {"cross": [cross], "goal": [gr], "ringa": rings[:1], "ringb": rings[1:2] or rings}.get(target.lower())
    if not tgt or tgt == [None]:
        # also try cells ADJACENT to target (block sits next to it, trail overlaps)
        tgt = [cross]
    # try the target cell AND its 4 neighbours (trail/adjacency collection)
    goals = set()
    for g in tgt:
        if g is None: continue
        goals.add(g)
        for dr, dc in DELTA.values():
            goals.add((g[0] + dr, g[1] + dc))
    path = bfs(passable, block, goals)
    names = {1: "UP", 2: "DOWN", 3: "LEFT", 4: "RIGHT"}
    if path is None:
        print(f"\nNO PATH to {target}")
    else:
        print(f"\nPATH to {target} ({len(path)} moves): {[names[a] for a in path]}")
        print("explore tokens:", " ".join(str(a) for a in path))


if __name__ == "__main__":
    main()
