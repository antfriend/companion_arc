"""Dump detect_state + frame signature for a game at a given level (isolated).
Usage: python _dbg_level.py <game> <level_1based>
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import importlib.util
from pathlib import Path
import numpy as np
from arcengine import ARCBaseGame

game = sys.argv[1]
level = int(sys.argv[2])
inst = next((Path("environment_files") / game).iterdir())
spec = importlib.util.spec_from_file_location("dbg", inst / f"{game}.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
cls = next(v for v in vars(mod).values() if isinstance(v,type) and issubclass(v,ARCBaseGame) and v is not ARCBaseGame)
det = importlib.import_module(f"games.{game}.detector")

g = cls(); g.set_level(level-1)
lvl = g.current_level
print(f"=== {game} L{level}  grid_size={lvl.grid_size} avail={getattr(g,'_available_actions',None)} ===")
print("sprites:")
for s in lvl.get_sprites():
    print(f"  {s.name:16s} pos=({s.x},{s.y}) size=({s.width}x{s.height}) rot={s.rotation} vis={s.is_visible}")
f = np.asarray(g.camera.render(lvl.get_sprites()))
print("frame", f.shape, "vals:")
for v in sorted(set(f.flatten().tolist())):
    pos = np.argwhere(f==v)
    print(f"  v{v}: n={len(pos)} bbox=r{pos[:,0].min()}-{pos[:,0].max()} c{pos[:,1].min()}-{pos[:,1].max()}")
st = det.detect_state(f)
print("detect_state:", st)
try:
    print("route:", det.compute_route(st, level))
except Exception as e:
    print("route ERROR:", type(e).__name__, e)
