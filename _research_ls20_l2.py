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


def act_between(a_cell, b_cell):
    """action id to step from a_cell to adjacent b_cell."""
    d = (b_cell[0] - a_cell[0], b_cell[1] - a_cell[1])
    for a, dd in DELTA.items():
        if dd == d:
            return a
    return None


def plan_win(passable, block, cross, rings, gr, names):
    """Full transform-and-deliver route: cross ×3 (rotation 0->3) then deliver to target,
    routing via ring A for a timer reset. (L2 spec: shape/color already match; only
    rotation differs by +3.)"""
    target = gr
    ringA = rings[0] if rings else None
    # leg 1: block -> cross (landing = visit 1)
    leg1 = bfs(passable, block, {cross})
    if leg1 is None:
        print("no path to cross"); return
    # oscillation: pick a passable neighbour of cross; [to-nbr, back-to-cross] x2 = +2 visits
    nbr = next(((cross[0] + dr, cross[1] + dc) for dr, dc in DELTA.values()
                if 0 <= cross[0] + dr < NR and 0 <= cross[1] + dc < NC and passable[cross[0] + dr, cross[1] + dc]), None)
    osc = []
    if nbr:
        a_out = act_between(cross, nbr); a_back = act_between(nbr, cross)
        osc = [a_out, a_back, a_out, a_back]      # 2 more visits => rotation 0->3
    # Timer-aware structure (each window <= ~21 moves; expiry RESETS rotation, so all 3
    # cross visits + delivery must fit within the 2 single-use ring resets):
    #   W1: block->cross (visit1) -> ringB (RESET, adjacent to cross)
    #   W2: ringB->cross (visit2) -> osc UP/DOWN (visit3) -> cross->ringA (RESET) -> target
    ringB = rings[1] if len(rings) > 1 else None
    def seg(s, e):
        p = bfs(passable, s, {e})
        if p is None:
            raise SystemExit(f"no path {s}->{e}")
        return p
    to_ringB = seg(cross, ringB)
    back = seg(ringB, cross)                    # re-enter cross = visit2
    osc2 = osc[:2]                              # UP/DOWN = leave + re-enter = visit3
    to_ringA = seg(cross, ringA)
    to_target = seg(ringA, target)
    full = leg1 + to_ringB + back + osc2 + to_ringA + to_target
    print(f"block={block} cross={cross} ringB={ringB} ringA={ringA} target={target}")
    print(f"W1: leg1({len(leg1)})+cross->ringB({len(to_ringB)})={len(leg1)+len(to_ringB)} | "
          f"W2: ringB->cross({len(back)})+osc({len(osc2)})+cross->ringA({len(to_ringA)})"
          f"+ringA->target({len(to_target)})={len(back)+len(osc2)+len(to_ringA)+len(to_target)}")
    print(f"\nFULL WIN ROUTE ({len(full)} moves): {[names[a] for a in full]}")
    print("explore tokens:", " ".join(str(a) for a in full))


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
    # target cell = the goal-room color-9 pattern (rows 38-46, cols 12-20)
    gr = None
    room = np.argwhere(f[38:47, 12:21] == 9)
    if len(room):
        pr = 38 + int(room[:, 0].mean()); pc = 12 + int(room[:, 1].mean())
        gr = ((pr - R0) // STEP, (pc - C0) // STEP)
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

    if target.lower() == "win":
        return plan_win(passable, block, cross, rings, gr, names={1:"UP",2:"DOWN",3:"LEFT",4:"RIGHT"})
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
