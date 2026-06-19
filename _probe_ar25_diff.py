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
def color_cells(ff,color):  # game-cell coords (scale 3)
    ga=ff[:63,:63]; pos=np.argwhere(ga==color); return {(int(c)//3,int(r)//3) for r,c in pos}
def show_change(name,b,a):
    # which colors changed counts
    vb=dict(zip(*[x.tolist() for x in np.unique(b,return_counts=True)]))
    va=dict(zip(*[x.tolist() for x in np.unique(a,return_counts=True)]))
    keys=sorted(set(vb)|set(va))
    delta={k:(va.get(k,0)-vb.get(k,0)) for k in keys if va.get(k,0)!=vb.get(k,0)}
    print(f"  {name}: color-count deltas {delta}")
    # piece(5) cells before/after
    print(f"     piece5 cells before={sorted(color_cells(b,5))}")
    print(f"     piece5 cells after ={sorted(color_cells(a,5))}")
for k in [2,3,4]:  # ACTION3, ACTION4, ACTION5
    g,obs,mo,n=fresh_to_L2(); b=np.asarray(obs.frame[-1])
    obs=g.perform_action(ActionInput(id=mo[k]),raw=True); a=np.asarray(obs.frame[-1])
    show_change(f"ACTION{[1,2,3,4,5,7][k]}",b,a)
