"""Check whether ls20 L4 has a PUSHER-FREE path through the waypoint chain
(block -> shape-changer -> color-changer x3 -> target), treating pusher cells as
walls. If yes, the fix is trivial (avoid pushers); if no, we need shove-transitions."""
import sys, numpy as np
from pathlib import Path
from arcengine import ARCBaseGame, ActionInput, GameAction
import _solve_ls20 as P
from games.ls20 import solver as S

g = P.load()()
obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
import _probe_ls20_level as L
obs = L.advance(g, obs, 4)
f = np.asarray(obs.frame[-1])
spec = S.read_spec(f, 4)
pm = spec["pm"]
# pusher cells = color-1-only grid cells
pushers = set()
for r in range(S.NR):
    for c in range(S.NC):
        patch = S._cell_patch(f, r, c)
        if np.any(patch == 1) and not np.any(patch == 0) and not any(np.any(patch==col) for col in S.PALETTE):
            pushers.add((r, c))
print("pushers:", sorted(pushers))
block = spec["block"]; sh = spec["changers"][0][0]; co = spec["changers"][1][0]
tgt = spec["targets"][0][0]
print(f"block={block} shape_changer={sh} color_changer={co} target={tgt}")
avoid_static = {sh, co, tgt}
def reach(a, b, extra_block):
    blocked = (set(pushers) | extra_block | (avoid_static - {b}))
    return S.bfs(pm, a, {b}, blocked=blocked)
print("block->shape :", reach(block, sh, set()))
print("shape->color :", reach(sh, co, set()))
print("color->color (retrigger via nbr): need a plain neighbor of color not pusher")
# neighbors of color changer
nbrs = [(co[0]+dr, co[1]+dc) for dr,dc in S.DELTA.values()
        if 0<=co[0]+dr<S.NR and 0<=co[1]+dc<S.NC and pm[co[0]+dr, co[1]+dc]
        and (co[0]+dr,co[1]+dc) not in pushers and (co[0]+dr,co[1]+dc) not in avoid_static]
print("  color-changer plain nbrs:", nbrs)
print("color->target:", reach(co, tgt, set()))
