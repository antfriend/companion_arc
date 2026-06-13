"""Does the online platform vary instances across fresh scorecards / resets?

Earlier test reused ONE scorecard and saw identical frames — possibly an
artifact. The larva observed ls20 block start varying (c34/c39/c29) on the
gateway. This test creates a FRESH scorecard each run and also does repeated
resets within a run, comparing first frames, to find where variation lives.
"""
import io, sys, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import arc_agi
from arc_agi import OperationMode


def frame_sig(fr):
    a = np.asarray(fr)
    # signature = positions of each non-background value (bbox per color)
    bg = int(np.bincount(a.flatten()).argmax())
    parts = []
    for v in sorted(set(a.flatten().tolist())):
        if v == bg:
            continue
        pos = np.argwhere(a == v)
        parts.append(f"{v}:{pos[:,0].min()}-{pos[:,0].max()},{pos[:,1].min()}-{pos[:,1].max()},n{len(pos)}")
    h = hashlib.md5(a.tobytes()).hexdigest()[:8]
    return h, " ".join(parts)


arc = arc_agi.Arcade(operation_mode=OperationMode.ONLINE)
envs = {e.game_id.split("-")[0]: e.game_id for e in arc.available_environments}

for prefix in ("ls20", "tu93", "wa30"):
    gid = envs.get(prefix)
    if not gid:
        continue
    print(f"\n=== {gid} ===")
    sigs = []
    for run in range(4):
        card = arc.open_scorecard(tags=[f"varcheck-{prefix}-{run}"])
        env = arc.make(gid, scorecard_id=card)
        actions = [a for a in (env.action_space or []) if a.is_simple()]
        obs = env.step(actions[0]) if actions else None
        if obs and obs.frame:
            h, sig = frame_sig(obs.frame[0])
            sigs.append(h)
            print(f"  freshcard run{run}: hash={h}  {sig[:140]}")
        try:
            arc.close_scorecard(card)
        except Exception:
            pass
    print(f"  distinct first-frame hashes across 4 fresh scorecards: {len(set(sigs))}")
