"""Dump re86 L1/L2/L3 structure: per non-bg color, cluster sizes (big=piece,
small=target markers), and the color-0 active center. Grounds the N-piece solver."""
import io
import sys
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import importlib.util
from arcengine import ARCBaseGame, ActionInput, GameAction
from games.re86.detector import _clusters, _target_center, _piece_center

ENV = Path(__file__).parent / "environment_files"


def load(game):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("r_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def frame_at(g, lvl):
    g.set_level(lvl)
    obs = g.perform_action(ActionInput(id=GameAction.ACTION7), raw=True)
    return np.asarray(obs.frame[-1]) if obs and obs.frame else None


def main():
    cls = load("re86")
    g = cls()
    g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    for lvl in (0, 1, 2):
        f = frame_at(g, lvl)
        print(f"\n===== re86 L{lvl+1} =====  shape={f.shape}")
        pos0 = np.argwhere(f == 0)
        print(f"  color-0 pixels: {len(pos0)} {pos0.tolist()[:3]}")
        vals, counts = np.unique(f, return_counts=True)
        bg = int(vals[int(np.argmax(counts))])
        for v in vals:
            if int(v) in (bg,):
                continue
            cl = _clusters(f, int(v))
            sizes = sorted((len(c) for c in cl), reverse=True)
            tc = _target_center(cl)
            pc = _piece_center(cl)
            print(f"  color {int(v):2d}: nclusters={len(cl)} sizes={sizes[:6]} target_center={tc} piece_center={pc}")


if __name__ == "__main__":
    main()
