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
        prev=obs.levels_completed; ag.reset_level()
        if prev==2: break
print("reached lvl",prev,"state",str(obs.state))
if prev==2 and obs is not None and obs.frame:
    f=np.asarray(obs.frame[-1]); v,c=np.unique(f[:63,:63],return_counts=True)
    print("L3 palette:",{int(x):int(n) for x,n in sorted(zip(v,c),key=lambda t:-t[1])})
    st=A.detect_state(f)
    print(f"L3 detect: piece=({st.piece_x},{st.piece_y}) |piece|={len(st.piece_shape)} |markers|={len(st.markers)} mirror_x={st.mirror_x}")
    print(f"  solve_placement_2d -> {A.solve_placement_2d(st)}")
    # multiple color-5 clusters? color-10 horizontal mirror?
    CH={9:'.',5:'P',11:'o',10:'|',0:' ',4:'+',13:'h',12:'m'}
    ga=f[:63,:63]
    for gy in range(21):
        row=''
        for gx in range(21):
            patch=ga[gy*3:gy*3+3,gx*3:gx*3+3]; vv,cc=np.unique(patch,return_counts=True);col=int(vv[np.argmax(cc)])
            row+=CH.get(col,str(col%10))
        print('  '+row)
