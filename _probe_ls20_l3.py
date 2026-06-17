"""Advance to L3 using the PROTOTYPE game-object planner (the SupervisedAgent can't clear
L2), then dump the L3 ground-truth spec + every tile's frame appearance. Answers the open
question: WHERE is the color changer, and how is each attribute drawn in the frame?"""
import importlib.util, io, random, sys
from pathlib import Path
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

import _solve_ls20 as P   # NOTE: this sets sys.stdout to a utf-8 wrapper at import
from games.ls20 import solver as S

ENV = Path(__file__).parent / "environment_files"
ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3, 4: GameAction.ACTION4}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
TAGS = {"ttfwljgohq": "SHAPE-changer", "soyhouuebz": "COLOR-changer",
        "rhsxkxzdjz": "ROT-changer(cross)", "npxgalaybz": "RING", "rjlbuycveu": "TARGET"}


def main():
    target_level = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    random.seed(0); np.random.seed(0)
    g = P.load()()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    level = 1
    while level < target_level:
        f = np.asarray(obs.frame[-1])
        nattr, bc, ba, tg, ch, rings = P.read_spec(g)
        acts = P.plan(P.build_map(f), bc, ba, tg, ch, rings, nattr)
        before = obs.levels_completed or 0
        for a in acts:
            obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
            if obs is None or str(obs.state) in END or not obs.frame:
                break
            if (obs.levels_completed or 0) > before:
                break
        if (obs.levels_completed or 0) <= before:
            print(f"FAILED to clear level {level}"); return
        level += 1

    f = np.asarray(obs.frame[-1])
    print(f"=== L{level} ground truth (levels_completed={obs.levels_completed}) ===")
    b = g.gudziatsk
    print(f"BLOCK pos=({b.x},{b.y}) shape={g.fwckfzsyc} color={g.hiaauhahz} rot_idx={g.cklxociuu}")
    print(f"  #shapes={len(g.ijessuuig)} #colors={len(g.tnkekoeuk)} colors_palette={g.tnkekoeuk}")
    for i, t in enumerate(g.plrpelhym):
        print(f"  target{i}: pos=({t.x},{t.y}) REQ shape={g.ldxlnycps[i]} color={g.yjdexjsoa[i]} rot={g.ehwheiwsk[i]}")
    print("\nTILES by tag (pos x,y):")
    for tag, name in TAGS.items():
        sprs = g.current_level.get_sprites_by_tag(tag)
        if sprs:
            print(f"  {name:20s} ({tag}): " + ", ".join(f"({s.x},{s.y})" for s in sprs))

    print("\n#### FRAME appearance of mover + changers + targets ####")
    def dump(name, x, y, h, w):
        sub = f[y:y+h, x:x+w]
        print(f"\n{name} @px({x},{y}) {h}x{w} cell={S.cell_of_px(y, x)}:\n{np.array2string(sub, max_line_width=200)}")
    p = g.gudziatsk
    dump("MOVER(block)", p.x, p.y, *p.pixels.shape)
    # appearance preview panels
    for nm in ("htkmubhry", "htkmubhry_2"):
        sp = getattr(g, nm, None)
        if sp is not None:
            dump(f"PREVIEW {nm}", sp.x, sp.y, *sp.pixels.shape)
    for tag, name in TAGS.items():
        for s in g.current_level.get_sprites_by_tag(tag):
            dump(f"{name}", s.x, s.y, *s.pixels.shape)
    for i, t in enumerate(g.srgbthxut):
        dump(f"TARGET-APPEARANCE[{i}] REQ sh={g.ldxlnycps[i]} co={g.yjdexjsoa[i]} rot={g.ehwheiwsk[i]}",
             t.x, t.y, *t.pixels.shape)


if __name__ == "__main__":
    main()
