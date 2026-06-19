"""Run the ACTUAL Ls20Dynamic learn-by-bump logic on L4 with full logging."""
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
import _solve_ls20 as P
from games.ls20 import solver as S
from games.ls20.dynamic import Ls20Dynamic
import _probe_ls20_level as L

ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3, 4: GameAction.ACTION4}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")

g = P.load()()
obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
obs = L.advance(g, obs, 4)
if (obs.levels_completed or 0) != 3:
    print("didn't reach L4"); raise SystemExit
dyn = Ls20Dynamic(); dyn.reset()
dyn._level = 4
before = obs.levels_completed or 0
for step in range(120):
    f = np.asarray(obs.frame[-1])
    timer = int(np.count_nonzero(f[61] == S.RING))
    st = dyn.next_action(f, 4)
    if st is None:
        print(f"  step {step}: dynamic returned None (aborted={dyn._aborted}, replans={dyn._replans}, learned={sorted(dyn._learned_pushers)}) timer={timer}")
        break
    a = st.action
    obs = g.perform_action(ActionInput(id=ACT[a + 1]), raw=True)  # dyn returns 0-indexed
    # action encoding: dynamic returns (solver_a-1)%n; map back: game action = a+1 if 0-indexed
    lvl = (obs.levels_completed or 0) if obs else before
    if obs is None or str(obs.state) in END or lvl > before:
        print(f"  step {step}: state={str(obs.state) if obs else None} lvl={lvl} replans={dyn._replans} learned={sorted(dyn._learned_pushers)}")
        break
print("final levels_completed:", obs.levels_completed if obs else None,
      "replans:", dyn._replans, "learned_pushers:", sorted(dyn._learned_pushers), "aborted:", dyn._aborted)
