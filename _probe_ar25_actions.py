import io,sys
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import importlib.util
from pathlib import Path
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from core.dynamics import library
from games.ar25 import detector as A
ACT=[GameAction.ACTION1,GameAction.ACTION2,GameAction.ACTION3,GameAction.ACTION4,GameAction.ACTION5,GameAction.ACTION6,GameAction.ACTION7]
END=("GameState.GAME_OVER","game_over","GameState.WIN","win")
ENV=Path("environment_files")
def load(game):
    inst=next((ENV/game).iterdir())
    spec=importlib.util.spec_from_file_location("p_"+game,inst/f"{game}.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values() if isinstance(v,type) and issubclass(v,ARCBaseGame) and v is not ARCBaseGame)
def fresh_to_L2():
    g=load("ar25")()
    obs=g.perform_action(ActionInput(id=GameAction.RESET),raw=True)
    raw=list(getattr(g,"_available_actions",[1,2,3,4,5]))
    mo=[ACT[a-1] for a in raw if a!=6];n=len(mo)
    ag=SupervisedAgent(n,seed=0);prev=0;path=[]
    for _ in range(600):
        if obs is None or str(obs.state) in END or not obs.frame: break
        full=np.asarray(obs.frame[-1])
        a=ag.choose(full)%n; path.append(a)
        obs=g.perform_action(ActionInput(id=mo[a]),raw=True)
        if obs is not None and (obs.levels_completed or 0)>prev:
            prev=obs.levels_completed
            if prev==1: break
    return g,obs,mo,n,raw
g,obs,mo,n,raw=fresh_to_L2()
f0=np.asarray(obs.frame[-1]); st0=A.detect_state(f0)
print(f"L2 start: piece=({st0.piece_x},{st0.piece_y}) |piece|={len(st0.piece_shape)} mirror={st0.mirror_x} raw_actions={raw} n={n}")
def piece_pos(ff):
    st=A.detect_state(ff); return (st.piece_x,st.piece_y)
print("\n--- each available action applied ONCE from L2 start (fresh replay each) ---")
for k in range(n):
    g2,obs2,mo2,n2,_=fresh_to_L2()
    before=piece_pos(np.asarray(obs2.frame[-1]))
    b0=np.asarray(obs2.frame[-1]).tobytes()
    obs2=g2.perform_action(ActionInput(id=mo2[k]),raw=True)
    ff=np.asarray(obs2.frame[-1]); after=piece_pos(ff)
    changed = ff.tobytes()!=b0
    print(f"  action idx{k} (GameAction {mo2[k]}): piece {before}->{after}  board_changed={changed}  state={str(obs2.state)}")
