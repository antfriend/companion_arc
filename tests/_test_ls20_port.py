import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))
"""Validate the frame-driven ls20 solver port: (a) read_spec from the FRAME matches the
game-object ground truth, (b) plan() actually clears L1 and L2 in the real game."""
import importlib.util, io, random, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from core.dynamics import library  # noqa
from games.ls20 import solver as S

ENV = Path(__file__).resolve().parent.parent / "environment_files"
ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3, 4: GameAction.ACTION4}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")


def load():
    inst = next(d for d in (ENV / "ls20").iterdir() if d.is_dir() and not d.name.startswith("__"))
    spec = importlib.util.spec_from_file_location("t_ls20", inst / "ls20.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return next(v for v in vars(m).values() if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def to_level(g_obs_builder, n):
    random.seed(0); np.random.seed(0)
    g = load()(); obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    if n <= 1:
        return g, obs
    ag = SupervisedAgent(4, seed=0); prev = 0
    for _ in range(200):
        if obs is None or str(obs.state) in END or not obs.frame:
            break
        a = ag.choose(np.asarray(obs.frame[-1])) % 4
        obs = g.perform_action(ActionInput(id=ACT[a + 1]), raw=True)
        if obs and (obs.levels_completed or 0) >= n - 1:
            return g, obs
    return g, obs


def gt(g):
    """ground-truth spec from the game object: block cell, {COLOR,ROT} changer cells, rings,
    and per-target (cell, [shape_delta, colour_delta, rot_delta])."""
    block = S.cell_of_px(g.gudziatsk.y, g.gudziatsk.x)
    changers = {S.SHAPE: [], S.COLOR: [], S.ROT: []}
    for tag, ai in (("ttfwljgohq", S.SHAPE), ("soyhouuebz", S.COLOR), ("rhsxkxzdjz", S.ROT)):
        changers[ai] = sorted(S.cell_of_px(s.y + 2, s.x + 2)
                              for s in g.current_level.get_sprites_by_tag(tag))
    rings = sorted(S.cell_of_px(s.y + 1, s.x + 1) for s in g.current_level.get_sprites_by_tag("npxgalaybz"))
    targets = []
    for i, t in enumerate(g.plrpelhym):
        sd = (g.ldxlnycps[i] - g.fwckfzsyc) % len(g.ijessuuig)
        cd = (g.yjdexjsoa[i] - g.hiaauhahz) % len(g.tnkekoeuk)
        rd = (g.ehwheiwsk[i] - g.cklxociuu) % 4
        targets.append((S.cell_of_px(t.y, t.x), [sd, cd, rd]))
    return block, changers, rings, sorted(targets)


def main():
    MAX = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print("=== read_spec FRAME vs ground-truth + plan() clears the real game ===")
    g, obs = to_level(None, 1)
    level = 1
    while level <= MAX:
        f = np.asarray(obs.frame[-1])
        spec = S.read_spec(f, level)
        gb, gch, gr, gtg = gt(g)
        if spec is None:
            print(f"L{level}: read_spec=None — DEFER (GT block={gb} changers={gch} rings={gr} targets={gtg})")
            break
        sb = spec["block"]
        sch = {k: sorted(v) for k, v in spec["changers"].items()}
        sr = sorted(spec["rings"]); stg = sorted(spec["targets"])
        ok = (sb == gb and sch == {k: sorted(v) for k, v in gch.items()}
              and sr == gr and stg == gtg)
        print(f"\nL{level}: read_spec {'MATCH' if ok else 'MISMATCH'}")
        print(f"   block    frame={sb} gt={gb}")
        print(f"   changers frame={sch} gt={ {k: sorted(v) for k, v in gch.items()} }")
        print(f"   rings    frame={sr} gt={gr}")
        print(f"   targets  frame={stg} gt={gtg}")
        acts = S.plan(spec)
        if not acts:
            print(f"L{level}: plan=None"); break
        before = obs.levels_completed or 0
        for a in acts:
            obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
            if obs is None or str(obs.state) in END or not obs.frame:
                break
            if (obs.levels_completed or 0) > before:
                break
        done = (obs.levels_completed or 0) if obs else 0
        if done > before:
            print(f"L{level}: SOLVED ✓ ({len(acts)} moves)"); level += 1
        else:
            print(f"L{level}: NOT solved ({len(acts)} moves, state={str(obs.state) if obs else None})"); break
    print(f"\nRESULT: frame-driven plan cleared up to level {level - 1}")


if __name__ == "__main__":
    main()
