"""Triage L2 closeness for re86 / cn04 / cd82: at L2 start, does the dynamic
recognize() fire and does its route solver return a plan? Distinguishes a
recognition gap (cheap) from a solver gap (real build)."""
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
    spec = importlib.util.spec_from_file_location("tr_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def frame_at(game, level_idx):
    cls = load(game)
    g = cls()
    g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    g.set_level(level_idx)
    # take a no-op-ish action to render the level frame
    obs = g.perform_action(ActionInput(id=GameAction.ACTION7), raw=True)
    if obs is None or not obs.frame:
        # fall back: render directly
        return None
    return np.asarray(obs.frame[-1])


def probe(game, dyn_factory):
    print(f"\n===== {game} =====")
    for lvl in (0, 1):
        f = frame_at(game, lvl)
        if f is None:
            print(f"  L{lvl+1}: no frame")
            continue
        d = dyn_factory()
        d.reset()
        try:
            conf = d.recognize(f)
        except Exception as e:
            conf = f"ERR {e}"
        plan = None
        try:
            d.set_level(lvl + 1)
        except Exception:
            pass
        try:
            step = d.next_action(f, 5)
            plan = step
        except Exception as e:
            plan = f"ERR {e}"
        print(f"  L{lvl+1}: recognize={conf}  first_step={plan}  uniques={np.unique(f).tolist()}")


def main():
    from games.re86.dynamic import Re86Dynamic
    from games.cn04.dynamic import Cn04Dynamic
    from games.cd82.dynamic import Cd82Dynamic
    probe("re86", Re86Dynamic)
    probe("cn04", Cn04Dynamic)
    probe("cd82", Cd82Dynamic)


if __name__ == "__main__":
    main()
