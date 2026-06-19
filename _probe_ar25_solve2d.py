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
ENV=Path("environment_files"); W=21;H=21
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
st=A.detect_state(np.asarray(obs.frame[-1]))
shape=sorted(st.piece_shape); markers=set(st.markers)
maxsx=max(sx for sx,sy in shape); maxsy=max(sy for sx,sy in shape)
# find q,py s.t. {(q-sx, py+sy)} == markers
sol=None
for mx0,my0 in markers:
    for sx0,sy0 in shape:
        q=mx0+sx0; py=my0-sy0
        refl={(q-sx,py+sy) for sx,sy in shape}
        if refl==markers and 0<=py and py+maxsy<=H-1:
            # find reachable (M,px): 2M-px=q, 0<=px, px+maxsx<=W-1, 0<=M<=20
            for M in range(0,21):
                px=2*M-q
                if 0<=px and px+maxsx<=W-1:
                    sol=(M,px,py); break
        if sol: break
    if sol: break
print("piece=",(st.piece_x,st.piece_y),"mirror=",st.mirror_x,"shape_extent=",(maxsx,maxsy))
print("2D solution (M*,px*,py*)=",sol)
if sol:
    Mt,pxt,pyt=sol
    # 1) select mirror (sel0 at start) move to Mt; 2) select piece move to (pxt,pyt)
    seq=[]
    # mirror moves (A3 left=mo[2], A4 right=mo[3]); currently sel=mirror
    dM=Mt-st.mirror_x
    seq+=[mo[3]]*max(dM,0)+[mo[2]]*max(-dM,0)
    seq+=[mo[4]]  # ACTION5 -> select piece
    dx=pxt-st.piece_x; dy=pyt-st.piece_y
    seq+=[mo[3]]*max(dx,0)+[mo[2]]*max(-dx,0)+[mo[1]]*max(dy,0)+[mo[0]]*max(-dy,0)
    for i,act in enumerate(seq):
        obs=g.perform_action(ActionInput(id=act),raw=True)
        if obs is None or not obs.frame: break
        if str(obs.state) in END or (obs.levels_completed or 0)>1: break
    s=A.detect_state(np.asarray(obs.frame[-1]))
    print(f"after exec: piece=({s.piece_x},{s.piece_y}) mirror={s.mirror_x} lvl={obs.levels_completed} state={str(obs.state)}")
