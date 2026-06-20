"""Dump cd82 L2 internals: target pattern, canvas, palette colors+positions,
basket fill regions. Grounds the paint-planner build."""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import importlib.util
from arcengine import ARCBaseGame, ActionInput, GameAction

ENV = Path(__file__).parent / "environment_files"


def load(game):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("cd_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def dump(g, lvl):
    g.set_level(lvl)
    L = g.current_level
    print(f"\n===== cd82 L{lvl+1} =====")
    canvas = [s for s in L.get_sprites() if s.name.startswith("xytrjjbyib")]
    target = [s for s in L.get_sprites() if s.name.startswith("eoqnvkspoa-")]
    palette = [s for s in L.get_sprites() if s.name.startswith("pqkenviek")]
    if target:
        print("TARGET pixels (10x10):")
        for row in np.asarray(target[0].pixels):
            print("  " + " ".join(f"{int(v):2d}" for v in row))
    if canvas:
        print("CANVAS pixels (10x10):")
        for row in np.asarray(canvas[0].pixels):
            print("  " + " ".join(f"{int(v):2d}" for v in row))
    print("PALETTE items (pqkenviek):")
    for s in palette:
        px = np.asarray(s.pixels)
        print(f"  pos=({s.x},{s.y}) center_color={int(px[px.shape[0]//2, px.shape[1]//2])} shape={px.shape}")


def main():
    cls = load("cd82")
    g = cls()
    g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    for lvl in (0, 1, 2):
        dump(g, lvl)


if __name__ == "__main__":
    main()
