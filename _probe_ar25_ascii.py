import io,sys
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import importlib.util
from pathlib import Path
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from core.dynamics import library
ACT=[GameAction.ACTION1,GameAction.ACTION2,GameAction.ACTION3,GameAction.ACTION4,GameAction.ACTION5,GameAction.ACTION6,GameAction.ACTION7]
END=("GameState.GAME_OVER","game_over","GameState.WIN","win")
ENV=Path("environment_files")
def load(game):
    inst=next((ENV/game).iterdir())
    spec=importlib.util.spec_from_file_location("p_"+game,inst/f"{game}.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values() if isinstance(v,type) and issubclass(v,ARCBaseGame) and v is not ARCBaseGame)
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
CH={9:'.',5:'P',11:'o',10:'|',0:' ',4:'+'}
def show(ff,title):
    ga=ff[:63,:63]
    # downscale 3x to 21x21 by majority
    print(title)
    for gy in range(21):
        row=''
        for gx in range(21):
            patch=ga[gy*3:gy*3+3,gx*3:gx*3+3]
            v,c=np.unique(patch,return_counts=True); col=int(v[np.argmax(c)])
            row+=CH.get(col,str(col%10))
        print('  '+row)
show(np.asarray(obs.frame[-1]),"L2 START (P=piece5  o=marker11  |=mirror10  .=bg9):")
for k,lbl in [(2,'ACTION3'),(2,'ACTION3'),(3,'ACTION4'),(3,'ACTION4')]:
    obs=g.perform_action(ActionInput(id=mo[k]),raw=True)
    show(np.asarray(obs.frame[-1]),f"after {lbl}: state={str(obs.state)} lvl={obs.levels_completed}")
