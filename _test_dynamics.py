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
def run_game_tests(seeds=10, budget=200):
    import importlib.util
    from pathlib import Path
    from arcengine import ARCBaseGame, ActionInput, GameAction
    from core.dynamics.registry import RECOG_HI
    from games.sp80.dynamic import Sp80Dynamic
    from games.cd82.dynamic import Cd82Dynamic
    from games.tu93.dynamic import Tu93Dynamic
    from games.wa30.dynamic import Wa30Dynamic
    from games.re86.dynamic import Re86Dynamic
    from games.ar25.dynamic import Ar25Dynamic
    from games.cn04.dynamic import Cn04Dynamic
    from games.ls20.dynamic import Ls20Dynamic
    from games.g50t.dynamic import G50tDynamic

    DYN = {"sp80": Sp80Dynamic, "cd82": Cd82Dynamic, "tu93": Tu93Dynamic,
           "wa30": Wa30Dynamic, "re86": Re86Dynamic, "ar25": Ar25Dynamic,
           "cn04": Cn04Dynamic, "ls20": Ls20Dynamic, "g50t": G50tDynamic}  # target → Dynamic

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

    def play(cls, make_agent, seed, recog=None, budget=budget):
        g = cls()
        obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
        raw = list(getattr(g, "_available_actions", [1, 2, 3, 4, 5]))
        mo = [ACTIONS[a - 1] for a in raw if a != 6]; n = len(mo)
        agent = make_agent(n, seed)
        fired = won = False
        for _ in range(budget):
            if obs is None or str(obs.state) in END or not obs.frame:
                break
            full = np.asarray(obs.frame[-1])
            if recog is not None and recog.recognize(full) >= RECOG_HI:
                fired = True
            a = agent.choose(full) % n
            obs = g.perform_action(ActionInput(id=mo[a]), raw=True)
            if obs is not None and obs.levels_completed > 0:
                won = True; break
        return won, fired

    def goal(n, seed):
        return GoalSeekAgent(n, seed=seed, goal_mode="near")

    def sup(classes_):
        return lambda n, seed: SupervisedAgent(n, seed=seed, goal_mode="near",
                                               dynamics=[C() for C in classes_])

    classes = {}
    for game in GAMES:
        try:
            classes[game] = load(game)
        except Exception as e:
            print(f"  {game} load-error {e}")

    # §6.1 recognizer confusion matrix — each dynamic must fire ONLY on its target.
    print("§6.1 recognizer confusion matrix (fires in ≥1 of "
          f"{seeds} goal rollouts, budget 40):")
    print(f"    {'dynamic':8s} | " + " ".join(f"{g[:4]:>4s}" for g in GAMES))
    clean = True
    for tgt, Cls in DYN.items():
        rec = Cls()
        cells = []
        for game in GAMES:
            if game not in classes:
                cells.append("  - "); continue
            fired = any(play(classes[game], goal, s, recog=rec, budget=40)[1]
                        for s in range(seeds))
            hit = (game == tgt)
            if fired and not hit:
                clean = False
            cells.append(("[X]" if hit else "XFR") if fired else " . ")
        print(f"    {tgt:8s} | " + " ".join(f"{c:>4s}" for c in cells))

    # §6.2 within-dynamic win-rate — supervised(single dynamic) vs goal on target.
    print("\n§6.2 within-dynamic win-rate (supervised[D] vs goal on the target game):")
    upside = True
    for tgt, Cls in DYN.items():
        if tgt not in classes:
            continue
        wg = sum(play(classes[tgt], goal, s)[0] for s in range(seeds))
        ws = sum(play(classes[tgt], sup([Cls]), s)[0] for s in range(seeds))
        upside = upside and ws > wg
        print(f"    {tgt:6s}: goal {wg}/{seeds}  →  supervised {ws}/{seeds}")

    # §6.3 abort safety — FULL library vs goal on NON-target games (parity).
    print("\n§6.3 abort safety (full-library supervised vs goal on non-target games):")
    full_lib = list(DYN.values())
    reg = True
    for game, cls in classes.items():
        if game in DYN:
            continue
        wg = sum(play(cls, goal, s)[0] for s in range(seeds))
        ws = sum(play(cls, sup(full_lib), s)[0] for s in range(seeds))
        ok = ws >= wg
        reg = reg and ok
        print(f"    {game:6s}: goal {wg}/{seeds}  supervised {ws}/{seeds}  "
              f"{'OK' if ok else 'REGRESSION'}")

    print("\nverdict:")
    print(f"  precision : {'CLEAN (no cross-fires)' if clean else 'CROSS-FIRES present'}")
    print(f"  upside    : {'supervised > goal on every target' if upside else 'a target lacks upside'}")
    print(f"  safety    : {'no off-target regression' if reg else 'OFF-TARGET REGRESSION'}")


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
