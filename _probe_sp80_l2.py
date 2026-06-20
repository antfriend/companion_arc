"""Probe sp80 L2: inspect layout, verify flood mechanic, test deepcopy-based
spill search. Goal — confirm whether a flood forward-model + placement search
can win L2 (3 obstacles, 3 pieces, k=2 action rotation)."""
import copy
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
from arcengine import ActionInput, GameAction

import importlib.util
ENV = Path(__file__).parent / "environment_files"


def load(game):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("pl_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from arcengine import ARCBaseGame
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def dump_level(g, lvl_idx):
    g.set_level(lvl_idx)
    L = g.current_level
    print(f"\n=== Level {lvl_idx+1}  grid={L.grid_size}  steps={L.get_data('steps')} rot={L.get_data('dojfslwbg')} ===")
    for s in L.get_sprites():
        tags = list(getattr(s, "tags", []))
        print(f"  {s.name:30s} pos=({s.x},{s.y}) wxh={s.width}x{s.height} tags={tags}")
    print(f"  k(rotation fahhoimkk)={g.fahhoimkk}  steps={g.zlhbnhpcq}")


def frame_of(g):
    obs = g.perform_action(ActionInput(id=GameAction.ACTION7), raw=True)  # no-op-ish
    return np.asarray(obs.frame[-1]) if obs and obs.frame else None


def main():
    cls = load("sp80")
    g = cls()
    g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    for i in range(3):
        dump_level(g, i)

    # Test deepcopy: snapshot L2, try a raw spill, see outcome, restore.
    g2 = cls()
    g2.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    g2.set_level(1)  # L2
    print("\n--- deepcopy test ---")
    try:
        snap = copy.deepcopy(g2)
        print("deepcopy OK")
    except Exception as e:
        print("deepcopy FAILED:", e)


if __name__ == "__main__":
    main()
