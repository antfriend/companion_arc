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
    g=load("ar25")(); obs=g.perform_action(ActionInput(id=GameAction.RESET),raw=True)
    raw=list(getattr(g,"_available_actions",[1,2,3,4,5])); mo=[ACT[a-1] for a in raw if a!=6];n=len(mo)
    ag=SupervisedAgent(n,seed=0);prev=0
    for _ in range(600):
        if obs is None or str(obs.state) in END or not obs.frame: break
        a=ag.choose(np.asarray(obs.frame[-1]))%n
        obs=g.perform_action(ActionInput(id=mo[a]),raw=True)
        if obs is not None and (obs.levels_completed or 0)>prev:
            prev=obs.levels_completed
            if prev==1: break
    return g,obs,mo,n
def feat(ff):
    st=A.detect_state(ff)
    # reflection cells of piece; overlap with markers
    M=st.mirror_x; refl={(2*M-x,y) for (x,y) in {(st.piece_x+ox,st.piece_y+oy) for ox,oy in st.piece_shape}}
    cov=len(refl & set(st.markers))
    return st.piece_x,st.piece_y,st.mirror_x,len(st.markers),cov
labels=['A1','A2','A3','A4','A5','A7']
g,obs,mo,n=fresh_to_L2(); print("L2 start feat (px,py,mx,#mark,refl∩mark):",feat(np.asarray(obs.frame[-1])))
for k in range(n):
    g,obs,mo,n=fresh_to_L2(); b=feat(np.asarray(obs.frame[-1]))
    obs=g.perform_action(ActionInput(id=mo[k]),raw=True); a=feat(np.asarray(obs.frame[-1]))
    d=tuple(a[i]-b[i] for i in range(5))
    print(f"  {labels[k]} (mo={mo[k]}): {b} -> {a}   delta(px,py,mx,#m,cov)={d}")
