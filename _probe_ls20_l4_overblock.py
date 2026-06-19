"""Test: detect pusher LINES (color-1, no color-0), forbid BOTH candidate cells
each straddles, and check the waypoint chain still has a path."""
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
import _solve_ls20 as P
from games.ls20 import solver as S
import _probe_ls20_level as L

g = P.load()(); obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
obs = L.advance(g, obs, 4); f = np.asarray(obs.frame[-1])
spec = S.read_spec(f, 4); pm = spec["pm"]

def pusher_cells(f):
    grid = np.zeros(f.shape, bool); grid[S.R0:S.R0+S.NR*S.STEP, S.C0:S.C0+S.NC*S.STEP] = True
    m1 = (f == 1) & grid
    cells = set()
    for (r0, r1, c0, c1) in S._clusters(m1):
        # skip the rotation cross (color-0 within/adjacent to the cluster)
        sub = f[max(0,r0-1):r1+2, max(0,c0-1):c1+2]
        if np.any(sub == 0):
            continue
        h, w = r1-r0, c1-c0
        if h >= w:   # vertical line -> horizontal pusher: straddles two COLS
            cr = S.cell_of_px(r0, c0)[0]
            for cc in {S.cell_of_px(r0, c0)[1], S.cell_of_px(r0, c0-4)[1], S.cell_of_px(r0, c1)[1]}:
                if 0 <= cc < S.NC: cells.add((cr, cc))
        else:        # horizontal line -> vertical pusher: straddles two ROWS
            cc = S.cell_of_px(r0, c0)[1]
            for rr in {S.cell_of_px(r0, c0)[0], S.cell_of_px(r0-4, c0)[0], S.cell_of_px(r1, c0)[0]}:
                if 0 <= rr < S.NR: cells.add((rr, cc))
    return cells

pcells = pusher_cells(f)
print("over-approx pusher cells:", sorted(pcells))
print("real sprite cells: (5,2),(2,7),(4,6),(4,7),(7,3),(7,7),(3,4)")
block = spec["block"]; sh = spec["changers"][0][0]; co = spec["changers"][1][0]; tgt = spec["targets"][0][0]
avoid = {sh, co, tgt}
def reach(a, b): return S.bfs(pm, a, {b}, blocked=(pcells | (avoid - {b})))
print("block->shape:", reach(block, sh) is not None)
print("shape->color:", reach(sh, co) is not None)
print("color->target:", reach(co, tgt) is not None)
nbrs = [(co[0]+dr,co[1]+dc) for dr,dc in S.DELTA.values() if 0<=co[0]+dr<S.NR and 0<=co[1]+dc<S.NC and pm[co[0]+dr,co[1]+dc] and (co[0]+dr,co[1]+dc) not in pcells and (co[0]+dr,co[1]+dc) not in avoid]
print("color plain nbr exists:", bool(nbrs), nbrs)
