import io,sys
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import importlib.util
from pathlib import Path
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from core.dynamics import library
from games.ar25 import detector as A
ACTIONS=[GameAction.ACTION1,GameAction.ACTION2,GameAction.ACTION3,GameAction.ACTION4,GameAction.ACTION5,GameAction.ACTION6,GameAction.ACTION7]
END=("GameState.GAME_OVER","game_over","GameState.WIN","win")
ENV=Path("environment_files")
def load(game):
    inst=next((ENV/game).iterdir())
    spec=importlib.util.spec_from_file_location("p_"+game,inst/f"{game}.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values() if isinstance(v,type) and issubclass(v,ARCBaseGame) and v is not ARCBaseGame)

g=load("ar25")()
obs=g.perform_action(ActionInput(id=GameAction.RESET),raw=True)
raw=list(getattr(g,"_available_actions",[1,2,3,4,5]))
mo=[ACTIONS[a-1] for a in raw if a!=6];n=len(mo)
print("actions:",raw,"-> simple n=",n)
ag=SupervisedAgent(n,seed=0);prev=0
# advance to L2 start
for _ in range(600):
    if obs is None or str(obs.state) in END or not obs.frame: break
    full=np.asarray(obs.frame[-1])
    a=ag.choose(full)%n
    obs=g.perform_action(ActionInput(id=mo[a]),raw=True)
    if obs is not None and (obs.levels_completed or 0)>prev:
        prev=obs.levels_completed
        if prev==1: break
print("reached L",prev)
f=np.asarray(obs.frame[-1])
st=A.detect_state(f)
print(f"L2 state: piece_x={st.piece_x} piece_y={st.piece_y} |piece|={len(st.piece_shape)} |markers|={len(st.markers)} mirror_x={st.mirror_x}")
print(f"  _solve_placement -> {A._solve_placement(st)}")
print(f"  markers (game cells): {sorted(st.markers)}")
print(f"  piece_shape offsets: {sorted(st.piece_shape)}")
# Experiment: move piece RIGHT toward mirror, watch marker count + piece pos each step
def cells(area,color):
    pos=np.argwhere(area==color); return {(int(c)//3,int(r)//3) for r,c in pos}
print("\n--- experiment: step RIGHT(4) x12, watch markers(11)/piece(5) counts ---")
IDX_RIGHT=3
for k in range(12):
    obs=g.perform_action(ActionInput(id=mo[IDX_RIGHT%n]),raw=True)
    if obs is None or not obs.frame: print("  (no frame)"); break
    ff=np.asarray(obs.frame[-1]); ga=ff[:63,:63]
    st2=A.detect_state(ff)
    nm=len(cells(ga,11)); np5=len(cells(ga,5))
    print(f"  step{k+1} RIGHT: state={str(obs.state)} lvl={obs.levels_completed} piece=({st2.piece_x},{st2.piece_y}) |mark|={nm} |piece|={np5}")
    if str(obs.state) in END: break
