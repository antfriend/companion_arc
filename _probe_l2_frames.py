import io,sys
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import importlib.util
from pathlib import Path
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from core.dynamics import library
ACTIONS=[GameAction.ACTION1,GameAction.ACTION2,GameAction.ACTION3,GameAction.ACTION4,GameAction.ACTION5,GameAction.ACTION6,GameAction.ACTION7]
END=("GameState.GAME_OVER","game_over","GameState.WIN","win")
ENV=Path("environment_files")
def load(game):
    inst=next((ENV/game).iterdir())
    spec=importlib.util.spec_from_file_location("p_"+game,inst/f"{game}.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values() if isinstance(v,type) and issubclass(v,ARCBaseGame) and v is not ARCBaseGame)
def palette(f):
    v,c=np.unique(f,return_counts=True)
    return {int(x):int(n) for x,n in sorted(zip(v,c),key=lambda t:-t[1])}
for game in ["tu93","wa30","sp80","cn04","ar25","re86","g50t"]:
    try:
        g=load(game)()
        obs=g.perform_action(ActionInput(id=GameAction.RESET),raw=True)
        raw=list(getattr(g,"_available_actions",[1,2,3,4,5]))
        mo=[ACTIONS[a-1] for a in raw if a!=6];n=len(mo)
        ag=SupervisedAgent(n,seed=0);prev=0;l1frame=None;l2frame=None
        for _ in range(600):
            if obs is None or str(obs.state) in END or not obs.frame: break
            full=np.asarray(obs.frame[-1])
            if prev==0 and l1frame is None: l1frame=full.copy()
            a=ag.choose(full)%n
            obs=g.perform_action(ActionInput(id=mo[a]),raw=True)
            if obs is not None and (obs.levels_completed or 0)>prev:
                prev=obs.levels_completed; ag.reset_level()
                if prev==1:
                    l2frame=np.asarray(obs.frame[-1]).copy(); break
        print(f"\n=== {game}  n_actions={n}  reached_L{prev}")
        if l1frame is not None: print(f"  L1 palette: {palette(l1frame)}")
        if l2frame is not None:
            print(f"  L2 palette: {palette(l2frame)}")
            # diff of palettes (new/changed colors at L2)
            p1,p2=palette(l1frame),palette(l2frame)
            newc=[k for k in p2 if k not in p1]
            print(f"  L2 NEW colors vs L1: {newc}")
        else:
            print("  (did not reach L2)")
    except Exception as e:
        print(f"\n=== {game}  ERROR {type(e).__name__}: {e}")
