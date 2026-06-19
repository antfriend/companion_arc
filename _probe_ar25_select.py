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
    pcells=frozenset((st.piece_x+ox,st.piece_y+oy) for ox,oy in st.piece_shape)
    return st.piece_x,st.piece_y,st.mirror_x,pcells
labels=['A1','A2','A3','A4','A5','A7']
# Test: after k cycles of ACTION5, which entity moves under A1/A2/A3/A4?
for ncyc in range(4):
    g,obs,mo,n=fresh_to_L2()
    for _ in range(ncyc):
        obs=g.perform_action(ActionInput(id=mo[4]),raw=True)  # ACTION5 = cycle selection
    base=feat(np.asarray(obs.frame[-1]))
    res=[]
    for k in [0,1,2,3]:  # A1,A2,A3,A4
        g2,o2,mo2,n2=fresh_to_L2()
        for _ in range(ncyc): o2=g2.perform_action(ActionInput(id=mo2[4]),raw=True)
        b=feat(np.asarray(o2.frame[-1]))
        o2=g2.perform_action(ActionInput(id=mo2[k]),raw=True); a=feat(np.asarray(o2.frame[-1]))
        dpx,dpy,dmx=a[0]-b[0],a[1]-b[1],a[2]-b[2]
        res.append(f"{labels[k]}:dpiece=({dpx},{dpy})dmx={dmx}")
    print(f"after {ncyc}x ACTION5 (sel state): piece@({base[0]},{base[1]}) mx={base[2]} | "+"  ".join(res))
