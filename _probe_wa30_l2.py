import io,sys
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import importlib.util
from pathlib import Path
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from core.dynamics import library
from games.wa30 import detector as W
ACT=[GameAction.ACTION1,GameAction.ACTION2,GameAction.ACTION3,GameAction.ACTION4,GameAction.ACTION5,GameAction.ACTION6,GameAction.ACTION7]
END=("GameState.GAME_OVER","game_over","GameState.WIN","win")
ENV=Path("environment_files")
def load(game):
    inst=next((ENV/game).iterdir())
    spec=importlib.util.spec_from_file_location("p_"+game,inst/f"{game}.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values() if isinstance(v,type) and issubclass(v,ARCBaseGame) and v is not ARCBaseGame)
g=load("wa30")(); obs=g.perform_action(ActionInput(id=GameAction.RESET),raw=True)
raw=list(getattr(g,"_available_actions",[1,2,3,4,5])); mo=[ACT[a-1] for a in raw if a!=6];n=len(mo)
print("raw actions",raw,"n",n)
ag=SupervisedAgent(n,seed=0);prev=0
for _ in range(600):
    if obs is None or str(obs.state) in END or not obs.frame: break
    a=ag.choose(np.asarray(obs.frame[-1]))%n
    obs=g.perform_action(ActionInput(id=mo[a]),raw=True)
    if obs is not None and (obs.levels_completed or 0)>prev:
        prev=obs.levels_completed
        if prev==1: break
print("reached L",prev,"state",str(obs.state))
f=np.asarray(obs.frame[-1]); ga=f[:63,:]
v,c=np.unique(ga,return_counts=True); print("L2 palette(<63):",{int(x):int(n) for x,n in sorted(zip(v,c),key=lambda t:-t[1])})
st=W.detect_state(f)
if st: print(f"detect: cursor=({st['cursor_x']},{st['cursor_y']}) #items={len(st['items'])} items={st['items']} #dz_valid={len(st['dz_valid'])}")
else: print("detect_state -> None")
print("color-12 cells (snap/4):", sorted({(int(c)//4*4,int(r)//4*4) for r,c in np.argwhere(ga==12)}))
rt=W.compute_route(st,1) if st else []
print(f"compute_route(L1 logic) len={len(rt)}: {rt[:40]}")
CH={1:'.',7:'#',0:'C',14:'c',4:'i',9:'o',2:'D',12:'X'}
print("ASCII (C=cursor0 c=body14 i=item4 o=9 D=dz2 X=12 #=7):")
for gy in range(0,63,3):
    row=''
    for gx in range(0,64,3):
        patch=ga[gy:gy+3,gx:gx+3]; vv,cc=np.unique(patch,return_counts=True);col=int(vv[np.argmax(cc)])
        row+=CH.get(col,str(col%10))
    print('  '+row)
