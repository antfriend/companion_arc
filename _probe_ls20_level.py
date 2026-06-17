"""CONDUCT: advance to level N using the FRAME solver + closed-loop replan (mirrors
games/ls20/dynamic.py), then dump level N's ground-truth spec, every tile's frame
appearance, AND the full sprite roster (to surface any NEW mechanic the dynamics don't model).
Usage: python _probe_ls20_level.py [N]"""
import io, random, sys
from pathlib import Path
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
import _solve_ls20 as P     # sets a utf-8 stdout wrapper at import
from games.ls20 import solver as S

ENV = Path(__file__).parent / "environment_files"
ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3, 4: GameAction.ACTION4}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
TAGS = {"ttfwljgohq": "SHAPE-changer", "soyhouuebz": "COLOR-changer",
        "rhsxkxzdjz": "ROT-changer(cross)", "npxgalaybz": "RING", "rjlbuycveu": "TARGET",
        "gbvqrjtaqo": "PUSHER-bar"}


def advance(g, obs, target):
    """Clear levels via the frame solver with closed-loop replan until at the START of `target`."""
    while (obs.levels_completed or 0) < target - 1:
        f = np.asarray(obs.frame[-1])
        lvl = (obs.levels_completed or 0) + 1
        spec = S.read_spec(f, lvl)
        if spec is None:
            print(f"  read_spec None at level {lvl}"); return obs
        route = S.plan(spec)
        if not route:
            print(f"  plan None at level {lvl}"); return obs
        cell, cells = spec["block"], []
        for a in route:
            dr, dc = S.DELTA[a]; cell = (cell[0]+dr, cell[1]+dc); cells.append(cell)
        before = obs.levels_completed or 0
        i, replans = 0, 0
        while i < len(route):
            obs = g.perform_action(ActionInput(id=ACT[route[i]]), raw=True)
            if obs is None or str(obs.state) in END or (obs.levels_completed or 0) > before:
                break
            f = np.asarray(obs.frame[-1])
            if S.read_block_cell(f) != cells[i]:        # divergence → replan (like the dynamic)
                replans += 1
                if replans > 16:
                    print(f"  too many replans at level {lvl}"); return obs
                spec = S.read_spec(f, lvl); route = S.plan(spec)
                if not route:
                    print(f"  replan plan None at level {lvl}"); return obs
                cell, cells = S.read_block_cell(f), []
                for a in route:
                    dr, dc = S.DELTA[a]; cell = (cell[0]+dr, cell[1]+dc); cells.append(cell)
                i = 0; continue
            i += 1
        if (obs.levels_completed or 0) <= before:
            print(f"  FAILED to clear level {lvl} (state={obs.state})"); return obs
    return obs


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    random.seed(0); np.random.seed(0)
    g = P.load()()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    obs = advance(g, obs, target)
    lvl = (obs.levels_completed or 0) + 1
    if lvl != target:
        print(f"only reached level {lvl}"); return
    f = np.asarray(obs.frame[-1])
    print(f"=== L{lvl} ground truth (levels_completed={obs.levels_completed}) ===")
    b = g.gudziatsk
    print(f"BLOCK pos=({b.x},{b.y}) cell={S.cell_of_px(b.y,b.x)} shape={g.fwckfzsyc} color={g.hiaauhahz} rot_idx={g.cklxociuu}")
    print(f"  #shapes={len(g.ijessuuig)} palette={g.tnkekoeuk} rotations={g.dhksvilbb}")
    for i, t in enumerate(g.plrpelhym):
        print(f"  target{i}: pos=({t.x},{t.y}) cell={S.cell_of_px(t.y,t.x)} REQ shape={g.ldxlnycps[i]} color={g.yjdexjsoa[i]} rot={g.ehwheiwsk[i]}")
    print("\nTILES by tag:")
    for tag, name in TAGS.items():
        sprs = g.current_level.get_sprites_by_tag(tag)
        if sprs:
            print(f"  {name:20s}: " + ", ".join(f"({s.x},{s.y})cell{S.cell_of_px(s.y,s.x)}" for s in sprs))
    # FULL sprite roster (surface unmodeled mechanics): tags not in our known set
    known = set(TAGS) | {"sfqyzhzkij", "ihdgageizm", "xfmluydglp"}
    print("\nUN-MODELED sprites (tag not in {changers,ring,target,pusher,block,wall}):")
    for s in g.current_level._sprites:
        tags = set(s.tags or [])
        if tags and not (tags & known):
            print(f"  name={s.name} tags={list(tags)} pos=({s.x},{s.y}) shape={np.asarray(s.pixels).shape}")
    print(f"\nL{lvl} read_spec:", S.read_spec(f, lvl))


if __name__ == "__main__":
    main()
