import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))
"""
_test_click_plumbing.py — proves the dynamics layer can drive ACTION6 clicks, and
that adding click capability did not disturb the additive (movement) path.

Click-gated games (dc22, ka59 multi-container, cd82 L2, re86 L3) need a solver to
emit ACTION6 at a chosen (x, y). The plumbing: SolverStep.click carries (x, y) →
SupervisedAgent.choose sets agent.spec=("c",x,y) → spec_to_action_input emits
ActionInput(ACTION6, {"x":x,"y":y}). When no solver clicks, spec stays ("m", action)
and the executed action is byte-identical to the int return (additive invariant).

Run: python _test_click_plumbing.py
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from core.solve_agent import SupervisedAgent
from core.click_agent import spec_to_action_input


class _ClickStub(Dynamic):
    """Fires always; emits a click at a fixed cell."""
    id = "clickstub"

    def recognize(self, frame):
        return 1.0

    def next_action(self, frame, n_actions):
        return SolverStep(action=0, expect=lambda f: True, click=(7, 9))


def _ok(cond, label, fails):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        fails.append(label)


def run() -> bool:
    fails = []
    print("click plumbing (dynamics → ACTION6) + movement additive path\n")
    frame = np.zeros((16, 16), dtype=np.int64)

    from arcengine import GameAction
    mo = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3, GameAction.ACTION4]

    # 1) A clicking dynamic drives ACTION6 at its chosen cell.
    sup = SupervisedAgent(4, seed=0, floor="v1", dynamics=[_ClickStub()])
    sup.reset_level(1)
    sup.choose(frame)
    _ok(sup.spec == ("c", 7, 9), f"agent.spec is the click  (got {sup.spec})", fails)
    ai = spec_to_action_input(sup.spec, mo)
    _ok(getattr(ai, "id", None) == GameAction.ACTION6, "translated to ACTION6", fails)
    data = getattr(ai, "data", {}) or {}
    _ok(data.get("x") == 7 and data.get("y") == 9,
        f"ACTION6 carries (x=7, y=9)  (got {data})", fails)

    # 2) Movement path: empty library → spec is ("m", action) and matches the int.
    sup0 = SupervisedAgent(4, seed=0, floor="v1", dynamics=[])
    sup0.reset_level(1)
    a = sup0.choose(frame)
    _ok(sup0.spec == ("m", a), f"no-fire spec is ('m', {a})  (got {sup0.spec})", fails)
    ai2 = spec_to_action_input(sup0.spec, mo)
    _ok(ai2.id == mo[a], "movement spec translates to the same action as the int", fails)

    # 3) Click-only floor (no movement actions) must propose a CLICK, never ("m",0)
    #    — else a launcher that indexes an empty action list crashes (the online
    #    IndexError at launch_competition._play_game).
    from core.click_agent import ClickExplorer
    f2 = np.zeros((20, 20), dtype=np.int64)
    f2[8:12, 8:12] = 5                          # a foreground blob to click
    ce = ClickExplorer(0, allow_click=True, seed=0)   # 0 moves = click-only game
    sp = ce.choose(f2)
    _ok(sp[0] == "c", f"click-only floor proposes a click on step 1  (got {sp})", fails)

    ok = not fails
    print("\nverdict:", "CLEAN — clicks drive ACTION6; movement path unchanged"
          if ok else f"BROKEN — {fails}")
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
