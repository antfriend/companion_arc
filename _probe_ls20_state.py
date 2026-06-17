"""Dump the ls20 L2 internal puzzle spec (the ground-truth transform-and-deliver model):
block (shape,color,rotation), each target's required (shape,color,rotation) + position,
and the positions of every changer/ring/target/wall tile by tag. Definitive — reads the
game object's own state, not the frame."""
import importlib.util, io, random, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from core.dynamics import library  # noqa

ENV = Path(__file__).parent / "environment_files"
ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3, 4: GameAction.ACTION4}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
TAGS = {"ttfwljgohq": "SHAPE-changer", "soyhouuebz": "COLOR-changer",
        "rhsxkxzdjz": "ROT-changer(cross)", "npxgalaybz": "RING(timer)",
        "rjlbuycveu": "TARGET", "ihdgageizm": "WALL", "sfqyzhzkij": "BLOCK"}


def load():
    inst = next(d for d in (ENV / "ls20").iterdir() if d.is_dir() and not d.name.startswith("__"))
    spec = importlib.util.spec_from_file_location("st_ls20", inst / "ls20.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return next(v for v in vars(m).values() if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def to_l2():
    random.seed(0); np.random.seed(0)
    g = load()()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    agent = SupervisedAgent(4, seed=0); prev = 0
    for _ in range(120):
        if obs is None or str(obs.state) in END or not obs.frame:
            break
        a = agent.choose(np.asarray(obs.frame[-1])) % 4
        obs = g.perform_action(ActionInput(id=ACT[a + 1]), raw=True)
        if obs and (obs.levels_completed or 0) > prev:
            return g, obs
    return g, obs


def main():
    g, obs = to_l2()
    print(f"=== ls20 L2 puzzle spec (levels_completed={obs.levels_completed}) ===")
    print(f"action-step grid: gisrhqpee(x-step)={g.gisrhqpee} tbwnoxqgc(y-step)={g.tbwnoxqgc}")
    b = g.gudziatsk
    print(f"\nBLOCK pos=({b.x},{b.y})  state: shape={g.fwckfzsyc} color={g.hiaauhahz} rotation_idx={g.cklxociuu}")
    print(f"  #shapes={len(g.ijessuuig)} #colors={len(g.tnkekoeuk)} rotations={g.dhksvilbb}")
    print(f"\nTARGETS ({len(g.plrpelhym)}):")
    for i, t in enumerate(g.plrpelhym):
        print(f"  target{i}: pos=({t.x},{t.y})  REQUIRE shape={g.ldxlnycps[i]} "
              f"color={g.yjdexjsoa[i]} rotation_idx={g.ehwheiwsk[i]}  satisfied={g.lvrnuajbl[i]}")
    print("\nTILES by tag (pos x,y):")
    for tag, name in TAGS.items():
        sprs = g.current_level.get_sprites_by_tag(tag)
        if sprs:
            print(f"  {name:20s} ({tag}): " + ", ".join(f"({s.x},{s.y})" for s in sprs))
    # what changes are needed
    print("\nDELTA block->target0 (mod cycle):")
    if g.plrpelhym:
        ds = (g.ldxlnycps[0] - g.fwckfzsyc) % len(g.ijessuuig)
        dc = (g.yjdexjsoa[0] - g.hiaauhahz) % len(g.tnkekoeuk)
        dr = (g.ehwheiwsk[0] - g.cklxociuu) % 4
        print(f"  need +{ds} shape-changer, +{dc} color-changer, +{dr} rotation-changer(cross) visits")


if __name__ == "__main__":
    main()
