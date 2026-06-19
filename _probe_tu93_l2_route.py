"""Empirically test whether tu93 L2 is winnable with a TURRET-AWARE route.

Memory said "no turret-free path" for this instance. But reading the source:
  * a turret ARMS only when the mover is at EXACTLY distance-6 (1 cell) in front
    of it on its facing axis (wlhbetxehh) — so the lethal set is ONE cell, the
    cell immediately in front of the turret.
  * the maze has a lower corridor letting the mover approach the turret column
    from BELOW (off-axis → no arm), landing on the turret's own cell only damages
    it (uneirnujpq grows the turret, no arming).

So we BFS from cursor to exit FORBIDDING each turret's arming cell, then execute
the route live and report WIN / LOSE / where it dies. This confirms (or refutes)
winnability before building the organ extension.
"""
import importlib.util, io, sys
from collections import deque
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.solve_agent import SupervisedAgent
from games.tu93.dynamic import Tu93Dynamic
from games.tu93 import detector as D

ACT = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3, GameAction.ACTION4]
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
ENV = Path(__file__).parent / "environment_files"
NAMES = {0: "UP", 1: "DOWN", 2: "LEFT", 3: "RIGHT"}
TURRET_COLORS = (8, 12, 13)
MARKER, ARMED = 15, 11
LCS = D.LOGICAL_CELL_SIZE  # 6


def load(game="tu93"):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("pr_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def _components(mask):
    """Connected components (4-conn) of a boolean mask → list of (rows, cols) arrays."""
    seen = np.zeros_like(mask, dtype=bool)
    comps = []
    pts = np.argwhere(mask)
    pset = {(int(r), int(c)) for r, c in pts}
    for r0, c0 in pts:
        if seen[r0, c0]:
            continue
        q = deque([(int(r0), int(c0))]); seen[r0, c0] = True; cells = []
        while q:
            r, c = q.popleft(); cells.append((r, c))
            for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nr, nc = r + dr, c + dc
                if (nr, nc) in pset and not seen[nr, nc]:
                    seen[nr, nc] = True; q.append((nr, nc))
        comps.append(cells)
    return comps


def find_turrets(frame, origin):
    """Return [(turret_cell, facing_dir, arming_cell)] for each turret on the frame.

    facing is derived from the marker (color-15 unarmed / color-11 armed) position
    within the turret's 3x3 body: top row=UP, bottom=DOWN, left col=LEFT, right=RIGHT.
    arming_cell = the cell one logical step in the facing direction.
    """
    f = np.asarray(frame)
    out = []
    for col in TURRET_COLORS:
        body = (f == col)
        if not body.any():
            continue
        for cells in _components(body):
            rs = [r for r, _ in cells]; cs = [c for _, c in cells]
            r0, c0, r1, c1 = min(rs), min(cs), max(rs), max(cs)
            # marker is within the same 3x3 bbox (color-15 or color-11)
            sub = f[r0:r1 + 1, c0:c1 + 1]
            mk = np.argwhere((sub == MARKER) | (sub == ARMED))
            if not len(mk):
                continue
            mr, mc = int(mk[:, 0].mean()), int(mk[:, 1].mean())
            h, w = sub.shape
            if mr == 0:
                d = (-1, 0)         # marker top -> faces UP
            elif mr == h - 1:
                d = (1, 0)          # bottom -> DOWN
            elif mc == 0:
                d = (0, -1)         # left -> LEFT
            else:
                d = (0, 1)          # right -> RIGHT
            tcell = ((r0 - origin[0]) // LCS, (c0 - origin[1]) // LCS)
            acell = (tcell[0] + d[0], tcell[1] + d[1])
            out.append((tcell, d, acell))
    return out


def bfs_forbid(grid, start, target, origin, forbidden):
    """detector._bfs but with a set of FORBIDDEN cells removed from the graph."""
    if start == target:
        return []
    pos = np.argwhere(grid == D.CORRIDOR_COLOR)
    if not len(pos):
        return []
    min_r = (int(pos[:, 0].min()) - origin[0]) // LCS - 1
    max_r = (int(pos[:, 0].max()) - origin[0]) // LCS + 1
    min_c = (int(pos[:, 1].min()) - origin[1]) // LCS - 1
    max_c = (int(pos[:, 1].max()) - origin[1]) // LCS + 1
    q = deque([(start[0], start[1], [])]); visited = {start}
    while q:
        r, c, path = q.popleft()
        for action, (dr, dc) in D._DELTAS.items():
            nr, nc = r + dr, c + dc
            if nr < min_r or nc < min_c or nr > max_r or nc > max_c:
                continue
            if (nr, nc) in forbidden:
                continue
            if not D._passage_open(grid, r, c, nr, nc, origin):
                continue
            if (nr, nc) == target:
                return path + [action]
            if (nr, nc) not in visited:
                visited.add((nr, nc)); q.append((nr, nc, path + [action]))
    return []


def main():
    g = load()()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    n = 4
    agent = SupervisedAgent(n, seed=0, dynamics=[Tu93Dynamic()])
    prev = 0
    # --- drive L1 with the existing dynamic until L2 starts ---
    for _ in range(300):
        if obs is None or str(obs.state) in END or not obs.frame:
            print("[died before L2]"); return
        a = agent.choose(np.asarray(obs.frame[-1])) % n
        obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
        if obs and (obs.levels_completed or 0) > prev:
            prev = obs.levels_completed
            break
    if prev < 1:
        print("[never cleared L1]"); return

    f = np.asarray(obs.frame[-1])
    st = D.detect_state(f)
    origin = st.cursor_pixel  # cursor TL == lattice origin; detect_state uses cur_tl
    # recompute origin exactly as detect_state does (cursor body+marker TL)
    c4 = np.argwhere(f == D.CURSOR_COLOR); body = np.argwhere(f == D.CURSOR_BODY)
    allc = np.vstack([c4, body]) if len(body) else c4
    origin = (int(allc[:, 0].min()), int(allc[:, 1].min()))

    turrets = find_turrets(f, origin)
    forbidden = {a for _, _, a in turrets}
    print(f"L2 start: cursor_cell={st.cursor_cell} target_cell={st.target_cell}")
    for tc, d, ac in turrets:
        print(f"  turret cell={tc} facing={d} -> ARMING cell forbidden={ac}")
    route = bfs_forbid(f, (0, 0), st.target_cell, origin, forbidden)
    plain = D._bfs(f, (0, 0), st.target_cell, origin)
    print(f"plain BFS len={len(plain)} route={plain}")
    print(f"turret-aware BFS len={len(route)} route={[NAMES[a] for a in route]}")
    if not route:
        print(">>> NO turret-safe path exists (forbidding arming cells). UNWINNABLE here.")
        return

    # --- execute the turret-aware route open-loop ---
    print("--- executing turret-aware route ---")
    for i, a in enumerate(route):
        if obs is None or str(obs.state) in END or not obs.frame:
            print(f"[end] state={str(obs.state) if obs else None} at step {i}"); return
        before = np.asarray(obs.frame[-1])
        bp = _cur(before)
        obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
        af = np.asarray(obs.frame[-1]) if (obs and obs.frame) else None
        ap = _cur(af) if af is not None else None
        lvl = (obs.levels_completed or 0) if obs else prev
        moved = "moved" if (bp and ap and ap != bp) else "NOOP"
        tg = " ".join(f"c{c}@{_tl(af,c)}+{int(np.count_nonzero(af==c))}" for c in TURRET_COLORS
                      if af is not None and (af == c).any())
        print(f"  [{i:2d}] {NAMES[a]:5s} {moved:5s} cur={ap} lvl={lvl} state={str(obs.state) if obs else None} | {tg}")
        if lvl > prev:
            print(f"\n*** L2 CLEARED at route step {i}! cursor reached exit. ***")
            return
    print(f"\n[route exhausted] final state={str(obs.state) if obs else None} levels={ (obs.levels_completed or 0) if obs else prev}")


def _cur(f):
    p = np.argwhere(np.asarray(f) == D.CURSOR_COLOR)
    return (int(p[:, 0].min()), int(p[:, 1].min())) if len(p) else None


def _tl(f, c):
    p = np.argwhere(np.asarray(f) == c)
    return (int(p[:, 0].min()), int(p[:, 1].min())) if len(p) else None


if __name__ == "__main__":
    main()
