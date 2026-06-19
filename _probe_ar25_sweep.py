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
def m11(ff): return int(np.count_nonzero(ff[:63,:63]==11))
def info(ff):
    st=A.detect_state(ff); return f"mx={st.mirror_x} c11px={m11(ff)} lvl?"
print("L2 start:",info(np.asarray(obs.frame[-1])), "state",str(obs.state))
# sweep mirror LEFT (ACTION3 = mo[2]) 14x, then RIGHT (ACTION4=mo[3]) 28x
seq=[(2,'L',14),(3,'R',28)]
for k,lbl,cnt in seq:
    for i in range(cnt):
        obs=g.perform_action(ActionInput(id=mo[k]),raw=True)
        if obs is None or not obs.frame: print("no frame");break
        ff=np.asarray(obs.frame[-1]); st=A.detect_state(ff)
        print(f"  {lbl}{i+1}: mx={st.mirror_x} c11px={m11(ff)} lvl={obs.levels_completed} state={str(obs.state)}")
        if str(obs.state) in END or (obs.levels_completed or 0)>1: 
            print("  *** STATE CHANGE ***"); break
    else:
        continue
    break
