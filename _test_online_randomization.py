"""Diagnose real-gateway behavior: instance hashes + per-run randomization.

1. List the live platform's game_ids — compare hashes with local/competition.
2. Start cn04 twice (two resets = two runs) and diff the first frames.
3. Same for ls20 (known-randomizing control) and g50t (hardcoded route game).
"""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import arc_agi
from arc_agi import OperationMode

arc = arc_agi.Arcade(operation_mode=OperationMode.ONLINE)
envs = arc.available_environments
print(f"{len(envs)} games on live platform:")
local = {
    "ar25": "0c556536", "cd82": "fb555c5d", "cn04": "2fe56bfb", "g50t": "5849a774",
    "ka59": "38d34dbb", "ls20": "9607627b", "re86": "8af5384d", "sk48": "d8078629",
    "tu93": "0768757b", "wa30": "ee6fef47", "sp80": "589a99af",
}
for e in sorted(envs, key=lambda x: x.game_id):
    gid = e.game_id
    prefix = gid.split("-")[0]
    mark = ""
    if prefix in local:
        mark = "MATCH" if local[prefix] in gid else f"DIFFERS (local {local[prefix]})"
    print(f"  {gid}  {mark}")

card = arc.open_scorecard(tags=["diag-randomization"])

for prefix in ("cn04", "ls20", "g50t"):
    gid = next((e.game_id for e in envs if e.game_id.startswith(prefix)), None)
    if gid is None:
        print(f"{prefix}: not on platform")
        continue
    frames = []
    for run in range(2):
        env = arc.make(gid, scorecard_id=card)
        obs = env.reset() if hasattr(env, "reset") else None
        if obs is None or not getattr(obs, "frame", None):
            # fall back: first simple action to obtain a frame
            actions = [a for a in (env.action_space or []) if a.is_simple()]
            obs = env.step(actions[0])
        frames.append(np.asarray(obs.frame[0]))
    a, b = frames
    same = a.shape == b.shape and bool(np.array_equal(a, b))
    diff = int((a != b).sum()) if a.shape == b.shape else -1
    print(f"{gid}: run1 vs run2 frames identical={same} diff_pixels={diff}")

arc.close_scorecard(card)
print("done")
