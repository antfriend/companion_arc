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
ag=SupervisedAgent(n,seed=0);prev=0
for _ in range(600):
    if obs is None or str(obs.state) in END or not obs.frame: break
    a=ag.choose(np.asarray(obs.frame[-1]))%n
    obs=g.perform_action(ActionInput(id=mo[a]),raw=True)
    if obs is not None and (obs.levels_completed or 0)>prev:
        prev=obs.levels_completed
        if prev==1: break
def c12(ff): return sorted({(int(c),int(r)) for r,c in np.argwhere(ff[:63,:]==12)})
st=W.detect_state(np.asarray(obs.frame[-1])); rt=W.compute_route(st,1)
print("c12 px cells at L2 start:",c12(np.asarray(obs.frame[-1])))
nm0=lambda ff: len({(int(c)//4,int(r)//4) for r,c in np.argwhere(ff[:63,:]==4)})
names={0:'U',1:'D',2:'L',3:'R',4:'@'}
for i,idx in enumerate(rt):
    b=np.asarray(obs.frame[-1]); bst=W.detect_state(b)
    obs=g.perform_action(ActionInput(id=mo[idx]),raw=True)
    if obs is None or not obs.frame: break
    a=np.asarray(obs.frame[-1])
    if i>=60 or (obs.levels_completed or 0)>1 or str(obs.state) in END:
        ast=W.detect_state(a)
        print(f"  s{i} {names[idx]}: cur {bst['cursor_x'],bst['cursor_y']}->{ast['cursor_x'],ast['cursor_y'] if ast else '?'} items{len(bst['items'])}->{len(ast['items']) if ast else '?'} state={str(obs.state)} c12={c12(a)}")
    if (obs.levels_completed or 0)>1 or str(obs.state) in END: break
