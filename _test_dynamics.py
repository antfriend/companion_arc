"""De-risk harness for the dynamics solver layer (ARC-RFC-0001 §6).

Currently implements the foundational equivalence checks (build steps 1–2):
  A. choose() == observe/propose/commit  (the refactor is a faithful split)
  B. SupervisedAgent(empty library) == GoalSeekAgent  (no-regression by
     construction: the supervisor adds nothing until a dynamic recognizes)

Steps 6.1–6.3 (recognizer confusion matrix, within-dynamic win-rate, abort
safety) are added when the first Dynamic (sp80) is ported.

Usage: python _test_dynamics.py
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np

from core.general_agent import GeneralAgent
from core.general_agent_dyn import GeneralAgentDyn
from core.goal_agent import GoalSeekAgent
from core.solve_agent import SupervisedAgent


def _frames(n=120, h=16, w=16, seed=0):
    """A reproducible frame stream with a few colors so the agents branch."""
    rs = np.random.RandomState(seed)
    out = []
    for i in range(n):
        # mostly-stable board with a small moving blob → some no-ops, some change
        a = np.zeros((h, w), dtype=np.int64)
        a[2:5, 2:5] = 11
        bx, by = 6 + (i % 7), 6 + ((i * 3) % 7)
        a[by, bx] = 9
        if i % 5 == 0:
            a += rs.randint(0, 2, (h, w))      # occasional perturbation
        out.append(a)
    return out


def _seq_choose(agent, frames):
    return [int(agent.choose(f)) for f in frames]


def _seq_opc(agent, frames):
    out = []
    for f in frames:
        agent.observe(f)
        a = int(agent.propose(f))
        agent.commit(f, a)
        out.append(a)
    return out


def test_split_equivalence():
    frames = _frames(seed=1)
    ok = True
    for name, make in (("GeneralAgent", lambda: GeneralAgent(4, seed=7)),
                       ("GeneralAgentDyn", lambda: GeneralAgentDyn(4, seed=7)),
                       ("GoalSeekAgent", lambda: GoalSeekAgent(4, seed=7, goal_mode="near"))):
        a = _seq_choose(make(), frames)
        b = _seq_opc(make(), frames)
        same = a == b
        ok = ok and same
        print(f"  [{'OK ' if same else 'FAIL'}] {name:16s} choose() == observe/propose/commit")
    return ok


def test_empty_library_equals_goal():
    frames = _frames(seed=2)
    goal = _seq_choose(GoalSeekAgent(4, seed=7, goal_mode="near"), frames)
    sup = _seq_choose(SupervisedAgent(4, seed=7, goal_mode="near", dynamics=[]), frames)
    same = goal == sup
    print(f"  [{'OK ' if same else 'FAIL'}] SupervisedAgent(empty) == GoalSeekAgent "
          f"({sum(x==y for x,y in zip(goal,sup))}/{len(goal)} match)")
    return same


# ---------------------------------------------------------------------------
# Real-game de-risk (ARC-RFC-0001 §6.1–6.3), behind --games (needs arcengine).
# ---------------------------------------------------------------------------
def run_game_tests(seeds=12, budget=150):
    import importlib.util
    from pathlib import Path
    from arcengine import ARCBaseGame, ActionInput, GameAction
    from core.dynamics.registry import RECOG_HI
    from games.sp80.dynamic import Sp80Dynamic

    ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
               GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
    END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
    ENV = Path(__file__).parent / "environment_files"
    GAMES = ["ls20", "cd82", "sp80", "re86", "tu93", "wa30",
             "ar25", "g50t", "sk48", "cn04", "ka59"]

    def load(game):
        inst = next((ENV / game).iterdir())
        spec = importlib.util.spec_from_file_location("dy_" + game, inst / f"{game}.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return next(v for v in vars(mod).values()
                    if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)

    def play(cls, kind, seed, recog=None):
        g = cls()
        obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
        raw = list(getattr(g, "_available_actions", [1, 2, 3, 4, 5]))
        mo = [ACTIONS[a - 1] for a in raw if a != 6]; n = len(mo)
        if kind == "goal":
            agent = GoalSeekAgent(n, seed=seed, goal_mode="near")
        else:
            agent = SupervisedAgent(n, seed=seed, goal_mode="near", dynamics=[Sp80Dynamic()])
        fired = won = False; fcount = 0; steps = 0
        for _ in range(budget):
            if obs is None or str(obs.state) in END or not obs.frame:
                break
            full = np.asarray(obs.frame[-1])
            if recog is not None and recog.recognize(full) >= RECOG_HI:
                fcount += 1; fired = True
            a = agent.choose(full) % n
            obs = g.perform_action(ActionInput(id=mo[a]), raw=True); steps += 1
            if obs is not None and obs.levels_completed > 0:
                won = True; break
        return won, fired, fcount, steps

    classes = {}
    for game in GAMES:
        try:
            classes[game] = load(game)
        except Exception as e:
            print(f"  {game} load-error {e}")

    # §6.1 recognizer precision — sp80 recognizer fire-rate per game (goal rollout)
    print("§6.1 recognizer precision (sp80 fingerprint fire-rate during a goal rollout):")
    rec = Sp80Dynamic()
    cross = []
    for game, cls in classes.items():
        fires = sum(play(cls, "goal", s, recog=rec)[1] for s in range(seeds))
        rate = fires / seeds
        tag = "← target" if game == "sp80" else ("CROSS-FIRE" if rate > 0 else "")
        if game != "sp80" and rate > 0:
            cross.append(game)
        print(f"    {game:6s}: fired in {fires:2d}/{seeds} episodes  {tag}")

    # §6.2 within-dynamic win-rate on sp80 — supervised should beat goal
    sg = sum(play(classes["sp80"], "goal", s)[0] for s in range(seeds)) if "sp80" in classes else 0
    ss = sum(play(classes["sp80"], "sup", s)[0] for s in range(seeds)) if "sp80" in classes else 0
    print(f"\n§6.2 within-dynamic win-rate on sp80:  goal {sg}/{seeds}  →  supervised {ss}/{seeds}")

    # §6.3 abort safety — supervised vs goal on NON-sp80 games (parity = no regression)
    print("\n§6.3 abort safety on non-sp80 games (supervised win == goal win):")
    reg = True
    for game, cls in classes.items():
        if game == "sp80":
            continue
        wg = sum(play(cls, "goal", s)[0] for s in range(seeds))
        ws = sum(play(cls, "sup", s)[0] for s in range(seeds))
        ok = ws >= wg
        reg = reg and ok
        print(f"    {game:6s}: goal {wg}/{seeds}  supervised {ws}/{seeds}  "
              f"{'OK' if ok else 'REGRESSION'}")

    print("\nverdict:")
    print(f"  precision : {'CLEAN (no cross-fires)' if not cross else 'CROSS-FIRES on '+','.join(cross)}")
    print(f"  upside    : {'supervised > goal on sp80' if ss > sg else 'no measured upside (ss<=sg)'}")
    print(f"  safety    : {'no regression off-target' if reg else 'REGRESSION off-target'}")


def main():
    print("DYNAMICS DE-RISK — foundational equivalence (steps 1–2)\n")
    print("A. refactor faithfulness:")
    a = test_split_equivalence()
    print("\nB. additive floor (no-regression by construction):")
    b = test_empty_library_equals_goal()
    print()
    if a and b:
        print("PASS: explorer split is faithful AND the supervisor with an empty")
        print("library is byte-identical to `goal`. Safe to port the first Dynamic.")
    else:
        print("FAIL: equivalence broken — fix before adding any Dynamic.")
        sys.exit(1)

    if "--games" in sys.argv:
        print("\n" + "=" * 60)
        print("REAL-GAME DE-RISK (sp80 Dynamic) — ARC-RFC-0001 §6.1–6.3\n")
        run_game_tests()


if __name__ == "__main__":
    main()
