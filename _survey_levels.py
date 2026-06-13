"""Compare L1 vs L2 sprite composition per game to classify level-2 difficulty.
A big jump in distinct sprite tags/sizes usually means a NEW mechanic."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import importlib.util
from pathlib import Path
from arcengine import ARCBaseGame

GAMES = ["ls20","cd82","sp80","re86","tu93","wa30","ar25","g50t","sk48","cn04","ka59"]

def load(game):
    inst = next((Path("environment_files")/game).iterdir())
    spec = importlib.util.spec_from_file_location("s_"+game, inst/f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    cls = next(v for v in vars(mod).values() if isinstance(v,type) and issubclass(v,ARCBaseGame) and v is not ARCBaseGame)
    return cls, mod

def sig(level):
    from collections import Counter
    c = Counter()
    for s in level.get_sprites():
        # group by tag set + size to spot distinct entity kinds
        tags = tuple(sorted(getattr(s,"tags",[]) or []))
        c[(tags, s.width, s.height)] += 1
    return c

for game in GAMES:
    try:
        cls, mod = load(game)
        nlev = len(mod.levels)
        l1 = sig(mod.levels[0])
        l2 = sig(mod.levels[1]) if nlev > 1 else None
        avail = "?"
        try:
            g = cls(); avail = getattr(g,"_available_actions",None)
        except Exception:
            pass
        n1 = sum(l1.values()); k1 = len(l1)
        line = f"{game:6s} levels={nlev} actions={avail}  L1: {n1} sprites/{k1} kinds"
        if l2:
            n2 = sum(l2.values()); k2 = len(l2)
            new_kinds = len(set(l2) - set(l1))
            line += f"  | L2: {n2} sprites/{k2} kinds  (+{new_kinds} new kinds vs L1)"
        print(line)
    except Exception as e:
        print(f"{game:6s} ERROR {type(e).__name__}: {e}")
