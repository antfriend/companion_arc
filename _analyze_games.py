"""Analyze wa30, cn04, ka59: first-frame signatures + action space + level structure."""
import sys, io, numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import arc_agi
from arc_agi import OperationMode

arc = arc_agi.Arcade(operation_mode=OperationMode.OFFLINE, environments_dir='environment_files')
game_ids = [e.game_id for e in arc.available_environments]
print('Available:', game_ids)

TARGETS = ['wa30-ee6fef47', 'cn04-2fe56bfb', 'ka59-38d34dbb']

for gid in TARGETS:
    if gid not in game_ids:
        print(f'\n{gid}: NOT FOUND'); continue

    env = arc.make(gid)
    all_actions = env.action_space or []
    simple = [a for a in all_actions if a.is_simple()]
    print(f'\n{"="*60}')
    print(f'{gid}')
    print(f'  Total actions: {len(all_actions)},  Simple: {len(simple)}')
    print(f'  Simple actions: {[str(a) for a in simple]}')

    # Step with first action to get initial frame
    obs = env.step(simple[0] if simple else all_actions[0])
    if not obs.frame:
        print('  No frame'); continue

    grid = list(obs.frame)[0]
    print(f'  Grid: {grid.shape}')
    print(f'  state: {obs.state}  levels: {obs.levels_completed}')

    bg = int(np.bincount(grid.flatten()).argmax())
    print(f'  bg color: {bg}')

    sigs = {}
    for v in np.unique(grid):
        iv = int(v)
        if iv == bg: continue
        pos = np.argwhere(grid == iv)
        r1, c1 = int(pos[:,0].min()), int(pos[:,1].min())
        r2, c2 = int(pos[:,0].max()), int(pos[:,1].max())
        sigs[iv] = (len(pos), r1, r2, c1, c2)

    for v, (n, r1, r2, c1, c2) in sorted(sigs.items()):
        h, w = r2-r1+1, c2-c1+1
        print(f'  v{v:2d}: n={n:4d}  rows={r1:2d}-{r2:2d}  cols={c1:2d}-{c2:2d}  bbox={h}x{w}')

    # Try a few more actions to see what moves
    print('  === Action responses ===')
    for i, act in enumerate(simple[:4]):
        obs2 = env.step(act)
        grid2 = list(obs2.frame)[0] if obs2.frame else None
        if grid2 is None:
            print(f'    action {i}: no frame'); continue
        diff = np.sum(grid2 != grid)
        print(f'    action {i} ({act}): {diff} pixels changed, state={obs2.state}')
        grid = grid2
