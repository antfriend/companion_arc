"""Advance to L4, plan, and EXECUTE move-by-move logging block cell vs expected,
to see whether the pusher-free plan runs clean or the block gets shoved."""
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
import _solve_ls20 as P
from games.ls20 import solver as S
import _probe_ls20_level as L

ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3, 4: GameAction.ACTION4}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")

g = P.load()()
obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
obs = L.advance(g, obs, 4)
if (obs.levels_completed or 0) != 3:
    print("didn't reach L4"); raise SystemExit
f = np.asarray(obs.frame[-1])
# pusher bar sprite sizes
for s in g.current_level.get_sprites_by_tag("gbvqrjtaqo"):
    print(f"  pusher {s.name} pos=({s.x},{s.y}) cell={S.cell_of_px(s.y,s.x)} size={np.asarray(s.pixels).shape}")
spec = S.read_spec(f, 4)
print("pushers(spec):", sorted(spec["pushers"]))
route = S.plan(spec)
print(f"plan len={len(route) if route else None} route={route}")
if not route:
    raise SystemExit
cell = spec["block"]; exp = []
for a in route:
    dr, dc = S.DELTA[a]; cell = (cell[0]+dr, cell[1]+dc); exp.append(cell)
before = obs.levels_completed or 0
for i, a in enumerate(route):
    obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
    if obs is None or str(obs.state) in END or (obs.levels_completed or 0) > before:
        print(f"  [{i}] a={a} -> state={str(obs.state) if obs else None} lvl={obs.levels_completed if obs else '?'}")
        break
    bc = S.read_block_cell(np.asarray(obs.frame[-1]))
    div = "" if bc == exp[i] else f"  <-- DIVERGED exp={exp[i]}"
    print(f"  [{i:2d}] a={a} block={bc}{div}")
    if bc != exp[i]:
        print("   (stopping at first divergence)"); break
print("final levels_completed:", obs.levels_completed if obs else None)
