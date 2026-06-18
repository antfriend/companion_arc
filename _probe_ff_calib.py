import io,sys
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import importlib.util
from pathlib import Path
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
ENV=Path("environment_files")
def load(game):
    inst=next((ENV/game).iterdir())
    spec=importlib.util.spec_from_file_location("dy_"+game,inst/f"{game}.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values() if isinstance(v,type) and issubclass(v,ARCBaseGame) and v is not ARCBaseGame)
def first_frame(game):
    g=load(game)()
    obs=g.perform_action(ActionInput(id=GameAction.RESET),raw=True)
    return np.asarray(obs.frame[-1])

def clusters_max(mask):
    from collections import deque
    seen=np.zeros_like(mask);best=0
    for sr in range(mask.shape[0]):
        for sc in range(mask.shape[1]):
            if mask[sr,sc] and not seen[sr,sc]:
                q=deque([(sr,sc)]);seen[sr,sc]=True;sz=0
                while q:
                    r,c=q.popleft();sz+=1
                    for dr,dc in((1,0),(-1,0),(0,1),(0,-1)):
                        nr,nc=r+dr,c+dc
                        if 0<=nr<mask.shape[0] and 0<=nc<mask.shape[1] and mask[nr,nc] and not seen[nr,nc]:
                            seen[nr,nc]=True;q.append((nr,nc))
                best=max(best,sz)
    return best

for game in ["sp80","cd82"]:
    f=first_frame(game)
    vals,counts=np.unique(f,return_counts=True)
    bg=int(vals[np.argmax(counts)]);bgfrac=counts.max()/f.size
    print(f"\n=== {game}  shape={f.shape}  bg={bg} bgfrac={bgfrac:.3f}")
    print(f"  count(9)={np.count_nonzero(f==9)} count(11)={np.count_nonzero(f==11)} count(8)={np.count_nonzero(f==8)} count(2)={np.count_nonzero(f==2)}")
    print(f"  max color-11 cluster={clusters_max(f==11)}  max color-2 cluster={clusters_max(f==2)}")
    # distinct nonzero-ish colors present
    print(f"  palette present:",{int(v):int(c) for v,c in zip(vals,counts)})
