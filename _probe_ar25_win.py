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
st=A.detect_state(np.asarray(obs.frame[-1])); tgt=A._solve_placement(st)
dx,dy=tgt[0]-st.piece_x, tgt[1]-st.piece_y
print(f"L2 start piece=({st.piece_x},{st.piece_y}) target={tgt} dx={dx} dy={dy}")
# A5 to select piece, then RIGHT*dx (A4) + DOWN*dy (A2)
seq=[mo[4]]+[mo[3]]*max(dx,0)+[mo[2]]*max(-dx,0)+[mo[1]]*max(dy,0)+[mo[0]]*max(-dy,0)
for i,act in enumerate(seq):
    obs=g.perform_action(ActionInput(id=act),raw=True)
    if obs is None or not obs.frame: print("no frame"); break
    s=A.detect_state(np.asarray(obs.frame[-1]))
    print(f"  step{i} {act}: piece=({s.piece_x},{s.piece_y}) lvl={obs.levels_completed} state={str(obs.state)}")
    if str(obs.state) in END or (obs.levels_completed or 0)>1: break
print("FINAL:", str(obs.state), "levels_completed=",obs.levels_completed)
